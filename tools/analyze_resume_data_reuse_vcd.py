#!/usr/bin/env python3
"""Validate complete normal D-cache accesses and conditional victim coverage.

Stream a closed FFC full-core trace through fst2vcd into stdin. Reconstruct the
normal tag SRAM from its actual masked writes, check synchronous tag reads and
accepted demand hit vectors, and match normal fills to accepted misses. Coverage
uses only actual baseline replacement victims, never a miss-only L1 simulation.
This is fixed-execution conditional address coverage, not execution, speedup,
prefetch benefit, FPGA projection, or a correctness proof for stored data.

Source conditions (FFC bp_be_dcache.sv): normal TV excludes snoop/replay/uncached/
prefetch/cache operations; hits require v_o; misses require request valid+yumi
and load_req/store_req. tag_mem_v_li/w_li/addr_li/data_li/mask_li are the actual
SRAM write port (lines 930-990). bp_uce.sv publishes M tags on the first normal
fill beat (lines 1164-1180,1207-1223); data opcode 0 is a normal fill. The cache
engine enum assigns clear/tag/state/inval/read opcodes 0/1/2/3/4, I/E/M=0/2/6.
"""
import argparse
from collections import Counter, OrderedDict
import json
from pathlib import Path
import re
import sys

from cache_overlap_vcd import EvidenceError, rising_edges

D = 'be.calculator.pipe_mem.dcache.'
WATCH = {
    'clock': 'be.clk_i', 'cache_clock': D+'clk_i', 'reset': 'be.reset_i',
    'global_cycle': 'be.calculator.pipe_sys.csr.global_cycle_r',
    'commit_v': 'be.calculator.commit_pkt_cast_o.instret',
    'commit_pc': 'be.calculator.commit_pkt_cast_o.pc',
    'commit_thread': 'be.retire_thread_id_lo',
    'sets': D+'sets_p', 'ways': D+'assoc_p', 'block_bits': D+'block_width_p',
    'num_threads': 'be.num_threads_p', 'num_contexts': 'be.num_contexts_p',
    'v': D+'v_tv_r', 'address': D+'paddr_tv_r', 'thread': D+'thread_id_tv_r',
    'snoop': D+'snoop_tv_r', 'uncached': D+'uncached_tv_r', 'replay': D+'replay_tv_r',
    'load': D+'decode_tv_r.load_op', 'store': D+'decode_tv_r.store_op',
    'prefetch': D+'decode_tv_r.prefetch_op', 'cache_op': D+'decode_tv_r.cache_op',
    'sc_fail': D+'sc_fail_tv', 'ptw': D+'decode_tv_r.ptw_op',
    'cache_hit': D+'cache_load_hit_tv', 'store_hit': D+'store_hit_tv',
    'load_vector': D+'load_hit_v_tv_r', 'store_vector': D+'store_hit_v_tv_r',
    'side_hit': D+'prefetch_buffer_hit_tv', 'result_v': D+'v_o',
    'request_v': D+'cache_req_v_o', 'request_yumi': D+'cache_req_yumi_i',
    'request_address': D+'cache_req_cast_o.addr',
    'load_req': D+'load_req', 'store_req': D+'store_req',
    'prefetch_req': D+'prefetch_req',
    'critical': D+'critical_recv', 'complete': D+'complete_recv',
    'tag_v': D+'tag_mem_v_li', 'tag_w': D+'tag_mem_w_li', 'tag_index': D+'tag_mem_addr_li',
    'tag_fast_write': D+'tag_mem_fast_write',
    'tag_packet_v': D+'tag_mem_pkt_v_i', 'tag_packet_yumi': D+'tag_mem_pkt_yumi_o',
    'tag_opcode': D+'tag_mem_pkt_cast_i.opcode',
    'data_v': D+'data_mem_pkt_v_i', 'data_yumi': D+'data_mem_pkt_yumi_o',
    'data_opcode': D+'data_mem_pkt_cast_i.opcode', 'data_address': D+'data_mem_pkt_cast_i.addr',
    'data_index': D+'data_mem_pkt_cast_i.index', 'data_way': D+'data_mem_pkt_cast_i.way_id',
    'data_mask': D+'data_mem_pkt_cast_i.fill_index',
    'inval_req': D+'inval_req', 'flush_req': D+'flush_req', 'binval_req': D+'binval_req',
}
CAPACITIES = (0, 4, 16, 32, 64, 128)


def integer(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def header(stream):
    scopes, found, widths, timescale = [], {}, {}, []
    in_timescale = False
    arrays = re.compile(re.escape(D) + r'tag_mem_(data_li|mask_li|data_lo)\[(\d+)\]\.(state|tag)$')
    maps = re.compile(r'be\.physical_thread_context_id_r\[(\d+)\]$')
    for line in stream:
        words = line.split()
        if '$timescale' in line:
            in_timescale = True
        if in_timescale:
            timescale += [word for word in words if word not in ('$timescale', '$end')]
            if '$end' in line:
                in_timescale = False
        if words[:1] == ['$scope']:
            scopes.append(words[2])
        elif words[:1] == ['$upscope']:
            scopes.pop()
        elif words[:1] == ['$var']:
            full = '.'.join(scopes + [words[4]])
            labels = [key for key, suffix in WATCH.items() if full.endswith('.'+suffix) or full == suffix]
            match = arrays.search(full)
            if match:
                kind, way, field = match.groups()
                labels.append('%s_%s_%s' % (kind, way, field))
            match = maps.search(full)
            if match:
                labels.append('context_'+match.group(1))
            for label in labels:
                found.setdefault(label, []).append((words[3], full))
                widths[label] = int(words[2])
        elif words[:1] == ['$enddefinitions']:
            break
    else:
        raise EvidenceError('missing VCD enddefinitions')
    required = set(WATCH) | {'context_0', 'context_1'}
    required |= {'%s_%d_%s' % (kind, way, field) for kind in ('data_li', 'mask_li', 'data_lo')
                 for way in range(8) for field in ('tag', 'state')}
    for label in required:
        if len(found.get(label, [])) != 1:
            raise EvidenceError('missing/ambiguous signal '+label+': '+repr(found.get(label)))
    if not timescale:
        raise EvidenceError('missing VCD timescale')
    return {key: matches[0] for key, matches in found.items()}, widths, ''.join(timescale)


class Victims:
    """Exclusive FIFO of real baseline evictions; refill/store removes a line."""
    def __init__(self, capacity):
        self.capacity = capacity
        self.lines = OrderedDict()
        self.stats = Counter()
        self.peak = 0

    def insert(self, line):
        if not self.capacity:
            return
        self.lines.pop(line, None)
        self.lines[line] = None
        self.stats['insertions'] += 1
        if len(self.lines) > self.capacity:
            self.lines.popitem(last=False)
            self.stats['replacements'] += 1
        self.peak = max(self.peak, len(self.lines))

    def remove(self, line, reason):
        if line in self.lines:
            del self.lines[line]
            self.stats[reason] += 1

    def clear(self):
        self.stats['invalidated_entries'] += len(self.lines)
        self.lines.clear()


def normalize_metadata(metadata):
    if metadata is None:
        return None
    result = dict(metadata)
    for key in ('begin_pc', 'end_pc', 'warmup_requests', 'timed_requests'):
        result[key] = integer(result[key])
    if result['begin_pc'] == result['end_pc'] or min(result['warmup_requests'], result['timed_requests']) < 1:
        raise EvidenceError('need distinct boundary PCs and positive warm/timed request counts')
    regions = []
    for region in result['regions']:
        item = {key: integer(region[key]) for key in ('context', 'base', 'bytes')}
        # calloc need not align a private corpus to a cache line. Preserve the
        # application's actual byte ranges, including shared boundary lines.
        if item['context'] not in range(4) or item['base'] < 0 or item['bytes'] <= 0:
            raise EvidenceError('target regions need context 0..3 and positive byte ranges')
        regions.append(item)
    if sorted(region['context'] for region in regions) != list(range(4)):
        raise EvidenceError('need exactly one target region per logical context')
    for index, region in enumerate(regions):
        for other in regions[index+1:]:
            if max(region['base'], other['base']) < min(region['base']+region['bytes'], other['base']+other['bytes']):
                raise EvidenceError('private target regions overlap')
    result['regions'] = regions
    if 'expected_loads_per_request' in result:
        result['expected_loads_per_request'] = integer(result['expected_loads_per_request'])
        if result['expected_loads_per_request'] < 1:
            raise EvidenceError('expected target load count must be positive')
    if 'expected_target_loads_by_context' in result:
        counts = result['expected_target_loads_by_context']
        total = result['warmup_requests'] + result['timed_requests']
        if set(counts) != {'0', '1', '2', '3'}:
            raise EvidenceError('expected target loads need all four logical contexts')
        normalized = {context: [integer(count) for count in items] for context, items in counts.items()}
        if any(len(items) != total or min(items) < 1 for items in normalized.values()):
            raise EvidenceError('expected target loads need one positive count per request')
        result['expected_target_loads_by_context'] = normalized
    return result


class Extractor:
    def __init__(self, widths, metadata=None, emit=None):
        self.widths = widths
        self.metadata = normalize_metadata(metadata)
        self.emit = emit or (lambda event: None)
        self.tags = [[None] * 8 for _ in range(64)]
        self.read_expected = None
        self.pending = None
        self.stats = Counter()
        self.ledgers = {capacity: Victims(capacity) for capacity in CAPACITIES}
        self.counts = {capacity: Counter() for capacity in CAPACITIES}
        self.covered_lines = {capacity: set() for capacity in CAPACITIES}
        self.target_covered_lines = {capacity: {'warm': set(), 'timed': set()} for capacity in CAPACITIES}
        self.requests = []
        self.active = {}
        self.epochs = Counter()
        self.target_lines = set()
        self.contexts = Counter()
        self.initialized = False
        self.sample_count = 0
        self.last_global = None
        self.reset_seen = False
        self.boundary_rows = []

    def event(self, kind, cycle, value, domain='dcache', **extra):
        self.emit(dict(event=kind, domain=domain, cycle=cycle, global_cycle=value['global_cycle'], **extra))

    def fail(self, cycle, message):
        raise EvidenceError('sample edge %d: %s' % (cycle, message))

    def line(self, index, tag):
        return ((tag << 6) | index) << 6

    def resident(self):
        return {self.line(index, tag) for index, row in enumerate(self.tags)
                for item in row if item is not None for state, tag in (item,) if state}

    def target(self, address):
        if self.metadata:
            for region in self.metadata['regions']:
                if region['base'] <= address < region['base'] + region['bytes']:
                    return region['context']
        return None

    def commit_edge(self, cycle, timestamp, value):
        if value.get('reset') != 0 or not self.reset_seen:
            return
        # The labels are the CSR instruction PCs themselves; the boundary is
        # retirement of that PC, and the global CSR remains separately recorded.
        if self.metadata and value['commit_v']:
            pc, thread = value['commit_pc'], value['commit_thread']
            context = value['context_%d' % thread]
            if pc == self.metadata['begin_pc']:
                if context in self.active:
                    self.fail(cycle, 'overlapping request boundaries for a logical context')
                epoch = self.epochs[context]
                self.epochs[context] += 1
                phase = 'warm' if epoch < self.metadata['warmup_requests'] else 'timed'
                request = dict(context=context, epoch=epoch, phase=phase, begin_be_edge=cycle,
                               begin_global_cycle=value['global_cycle'], stats=Counter(), coverage=Counter())
                self.active[context] = request
                self.requests.append(request)
                self.event('begin', cycle, value, domain='be', context=context, epoch=epoch, phase=phase, pc=hex(pc))
            elif pc == self.metadata['end_pc']:
                if context not in self.active:
                    self.fail(cycle, 'request end without begin')
                request = self.active.pop(context)
                request['end_be_edge'] = cycle
                request['end_global_cycle'] = value['global_cycle']
                self.event('end', cycle, value, domain='be', context=context, epoch=request['epoch'], phase=request['phase'], pc=hex(pc))


    def step(self, cycle, timestamp, value, process_commit=True):
        if value.get('reset') == 1:
            if self.sample_count:
                self.fail(cycle, 'reset after active trace; split runs explicitly')
            self.reset_seen = True
            return
        if value.get('reset') != 0:
            self.fail(cycle, 'unknown reset')
        # Full-core traces include uninitialized clock/startup traffic before
        # the testbench asserts reset. It is outside the measured execution.
        if not self.reset_seen:
            return
        # All selected observations must be known. A missing/partial waveform
        # cannot silently become an ordinary miss or an empty initial cache.
        for key in self.widths:
            if value.get(key) is None:
                self.fail(cycle, 'unknown '+key)
        self.sample_count += 1
        if (value['sets'], value['ways'], value['block_bits'], value['num_threads'], value['num_contexts']) != (64, 8, 512, 2, 4):
            self.fail(cycle, 'requires FFC 64-set/8-way/64-byte, 2-thread/4-context geometry')
        if self.widths['data_li_0_tag'] != 20 or self.widths['data_li_0_state'] != 3 or self.widths['data_mask'] != 8:
            self.fail(cycle, 'unexpected tag/coherence/fill packing')
        if self.last_global is not None and value['global_cycle'] != self.last_global + 1:
            self.fail(cycle, 'global physical CSR cycle does not increment once per D-cache edge')
        self.last_global = value['global_cycle']
        if self.read_expected is not None:
            for way, expected in enumerate(self.read_expected):
                actual = value['data_lo_%d_state' % way], value['data_lo_%d_tag' % way]
                if actual != expected:
                    self.fail(cycle, 'normal synchronous tag read disagrees with actual write reconstruction')
            self.stats['validated_tag_read_rows'] += 1
            self.read_expected = None
        if value['tag_v'] and not value['tag_w']:
            index = value['tag_index']
            if any(item is None for item in self.tags[index]):
                self.fail(cycle, 'tag read before complete observed initialization of its row')
            self.read_expected = list(self.tags[index])

        if process_commit:
            self.commit_edge(cycle, timestamp, value)

        candidate = value['v'] and not any(value[key] for key in ('snoop', 'uncached', 'replay', 'prefetch', 'cache_op', 'sc_fail'))
        candidate = candidate and (value['load'] or value['store'])
        miss = bool(candidate and value['request_v'] and value['request_yumi'] and (value['load_req'] or value['store_req']))
        hit = bool(candidate and value['result_v'])
        if candidate and not (miss or hit):
            self.stats['unaccepted_tv_attempts'] += 1
        if hit or miss:
            if not self.initialized:
                if any(item is None for row in self.tags for item in row):
                    self.fail(cycle, 'first accepted cached access precedes complete observed tag initialization')
                self.initialized = True
                self.stats['observed_initialization_slots'] = 512
            if hit and miss:
                self.fail(cycle, 'simultaneous demand hit and accepted miss')
            address, thread = value['address'], value['thread']
            context = value['context_%d' % thread]
            if context not in range(4):
                self.fail(cycle, 'invalid logical context map')
            line = address & ~63
            index, tag = (address >> 6) & 63, address >> 12
            row = self.tags[index]
            expected_load = sum(1 << way for way, (state, old_tag) in enumerate(row)
                                if state and old_tag == tag and address < (1 << 32))
            expected_store = sum(1 << way for way, (state, old_tag) in enumerate(row)
                                 if state in (2, 6) and old_tag == tag and address < (1 << 32))
            if (value['load_vector'], value['store_vector']) != (expected_load, expected_store):
                self.fail(cycle, 'accepted demand hit vectors disagree with actual normal L1 tags')
            if bin(expected_load).count('1') > 1 or bin(expected_store).count('1') > 1:
                self.fail(cycle, 'duplicate ordinary L1 line')
            if bool(value['cache_hit']) != bool(expected_load) or bool(value['store_hit']) != bool(expected_store):
                self.fail(cycle, 'scalar normal hit decision differs from one-hot tag vectors')
            if value['side_hit'] or (hit and not (expected_store if value['store'] else expected_load)):
                self.fail(cycle, 'baseline demand served outside the normal resident L1 path')
            kind = 'store' if value['store'] else 'load'
            target_context = self.target(address)
            request = self.active.get(context)
            is_target = target_context is not None
            in_request = bool(is_target and target_context == context and request is not None)
            if is_target and target_context != context:
                # Main initializes every corpus; retain this as interference,
                # but do not misattribute initialization as target request work.
                self.stats['other_context_target_region_accesses'] += 1
            self.contexts[str(context)] += 1
            self.stats['accepted_cached_references'] += 1
            self.stats['accepted_cached_'+kind+'s'] += 1
            self.stats['ordinary_misses' if miss else 'normal_l1_hits'] += 1
            if miss and expected_load:
                self.stats['resident_permission_misses'] += 1
            if value['ptw']:
                self.stats['cached_ptw_references'] += 1
            if in_request:
                request['stats']['target_'+kind+'s'] += 1
                request['stats']['ordinary_misses' if miss else 'normal_l1_hits'] += 1
                self.target_lines.add(line)
            extra = {}
            for capacity, ledger in self.ledgers.items():
                if in_request:
                    self.counts[capacity][request['phase']+'_target_'+kind+'s'] += 1
                    if miss:
                        self.counts[capacity][request['phase']+'_target_ordinary_misses'] += 1
                covered = bool(miss and not expected_load and line in ledger.lines)
                if covered:
                    if line in self.resident():
                        self.fail(cycle, 'victim candidate duplicates actual L1')
                    ledger.stats['covered_ordinary_misses'] += 1
                    self.covered_lines[capacity].add(line)
                    if in_request:
                        request['coverage'][str(capacity)] += 1
                        self.counts[capacity][request['phase']+'_target_misses_covered'] += 1
                        self.target_covered_lines[capacity][request['phase']].add(line)
                extra[str(capacity)] = covered
                # A store invalidates any retained copy, including a covered
                # store miss. It never makes an old victim silently fresh.
                if value['store']:
                    ledger.remove(line, 'store_invalidations')
            self.event('reference', cycle, value, address=hex(address), line=hex(line), context=context,
                       thread=thread, operation=kind, outcome='miss' if miss else 'l1_hit',
                       l1_resident=bool(expected_load), target=in_request,
                       epoch=request['epoch'] if in_request else None,
                       phase=request['phase'] if in_request else None, victim_coverage=extra)
            if miss:
                if self.pending is not None:
                    self.fail(cycle, 'more than one accepted normal miss outstanding')
                if value['request_address'] != address:
                    self.fail(cycle, 'accepted request address differs from TV physical address')
                self.pending = dict(line=line, mask=0, tag_published=False, way=None,
                                    context=context, operation=kind, critical_seen=False)

        if value['request_v'] and value['request_yumi'] and value['prefetch_req']:
            self.fail(cycle, 'baseline contains an accepted prefetch; conditional ordinary-only ledger unsupported')
        if value['request_v'] and value['request_yumi'] and (value['inval_req'] or value['flush_req']):
            for ledger in self.ledgers.values():
                ledger.clear()
            self.stats['global_invalidation_requests'] += 1
            self.event('invalidate_all', cycle, value)

        data_fill = value['data_v'] and value['data_yumi'] and value['data_opcode'] == 0
        if data_fill:
            pending = self.pending
            line = value['data_address'] & ~63
            if pending is None or pending['line'] != line:
                self.fail(cycle, 'normal data fill without matching accepted ordinary miss')
            if value['data_index'] != ((line >> 6) & 63):
                self.fail(cycle, 'normal data fill index differs from physical address')
            mask = value['data_mask']
            if not mask or mask & (mask - 1) or pending['mask'] & mask:
                self.fail(cycle, 'normal data fill has invalid or repeated beat mask')
            if pending['way'] not in (None, value['data_way']):
                self.fail(cycle, 'normal fill changes way within a line')
            pending['way'] = value['data_way']
            pending['mask'] |= mask
            self.stats['matched_normal_fill_beats'] += 1
            self.event('fill_beat', cycle, value, line=hex(line), way=value['data_way'], mask=mask)

        if value['tag_v'] and value['tag_w']:
            index = value['tag_index']
            opcode = value['tag_opcode']
            if not value['tag_fast_write'] and not (value['tag_packet_v'] and value['tag_packet_yumi']):
                self.fail(cycle, 'normal tag write without accepted slow packet or explicit fast invalidation')
            if not value['tag_fast_write'] and opcode not in (0, 1, 2, 3):
                self.fail(cycle, 'unknown normal tag write opcode')
            published = []
            evicted = []
            for way in range(8):
                old = self.tags[index][way]
                state_mask, tag_mask = value['mask_li_%d_state' % way], value['mask_li_%d_tag' % way]
                if state_mask not in (0, 7) or tag_mask not in (0, (1 << 20)-1):
                    self.fail(cycle, 'unsupported partial tag or coherence field write')
                if old is None:
                    if not state_mask or not tag_mask:
                        if state_mask or tag_mask:
                            self.fail(cycle, 'partial normal tag initialization cannot establish prior state')
                        continue
                    old_state, old_tag = 0, 0
                else:
                    old_state, old_tag = old
                state = value['data_li_%d_state' % way] if state_mask else old_state
                tag = value['data_li_%d_tag' % way] if tag_mask else old_tag
                if not state_mask and not tag_mask:
                    continue
                self.tags[index][way] = state, tag
                if state and (not old_state or old_tag != tag):
                    new_line = self.line(index, tag)
                    if value['tag_fast_write'] or opcode != 1 or not data_fill:
                        self.fail(cycle, 'normal tag insertion not paired with ordinary first fill beat')
                    if self.pending is None or self.pending['line'] != new_line or self.pending['tag_published']:
                        self.fail(cycle, 'normal tag publication differs from accepted outstanding miss')
                    if value['data_way'] != way:
                        self.fail(cycle, 'normal tag publication way differs from data fill way')
                    self.pending['tag_published'] = True
                    published.append(new_line)
                    self.stats['matched_normal_tag_publications'] += 1
                    for ledger in self.ledgers.values():
                        ledger.remove(new_line, 'actual_refill_removals')
                if old_state and state and old_tag != tag:
                    old_line = self.line(index, old_tag)
                    evicted.append(old_line)
                    self.stats['actual_replacement_evictions'] += 1
                    self.event('eviction', cycle, value, line=hex(old_line), replacement=hex(self.line(index, tag)),
                               index=index, way=way)
                elif old_state and not state:
                    for ledger in self.ledgers.values():
                        ledger.remove(self.line(index, old_tag), 'tag_invalidations')
                    self.stats['normal_l1_invalidations'] += 1
            resident = self.resident()
            for line in evicted:
                if line in resident:
                    self.fail(cycle, 'actual replacement victim remains present in another ordinary L1 way')
                for ledger in self.ledgers.values():
                    ledger.insert(line)
            for ledger in self.ledgers.values():
                if resident.intersection(ledger.lines):
                    self.fail(cycle, 'exclusive victim ledger overlaps actual L1 after tag write')

        if data_fill:
            if not self.pending['tag_published']:
                self.fail(cycle, 'normal fill beat precedes its actual tag publication')
            if value['critical']:
                if self.pending['critical_seen']:
                    self.fail(cycle, 'repeated critical completion of one normal miss')
                self.pending['critical_seen'] = True
            if value['complete']:
                if self.pending['mask'] != 255 or not self.pending['critical_seen']:
                    self.fail(cycle, 'normal completion without all eight unique beats and critical completion')
                self.stats['matched_complete_normal_refills'] += 1
                self.event('fill_complete', cycle, value, line=hex(self.pending['line']), way=self.pending['way'])
                self.pending = None
            elif self.pending['mask'] == 255:
                self.fail(cycle, 'all normal fill beats observed without complete_recv')

    def report(self):
        if not self.initialized or not self.stats['validated_tag_read_rows']:
            raise EvidenceError('trace did not establish initialized normal L1 reads and accepted cached references')
        if self.pending is not None:
            raise EvidenceError('trace ends with unmatched accepted ordinary miss')
        if self.active:
            raise EvidenceError('trace ends with open request boundaries')
        if self.stats['ordinary_misses'] != self.stats['matched_complete_normal_refills']:
            raise EvidenceError('ordinary miss count differs from complete matched normal refills')
        if self.stats['ordinary_misses'] != self.stats['matched_normal_tag_publications']:
            raise EvidenceError('ordinary miss count differs from actual normal tag publications')
        if self.metadata:
            total = self.metadata['warmup_requests'] + self.metadata['timed_requests']
            if dict(self.epochs) != {context: total for context in range(4)}:
                raise EvidenceError('request-boundary counts differ from all four expected contexts')
            expected_loads = self.metadata.get('expected_loads_per_request')
            for request in self.requests:
                counts = self.metadata.get('expected_target_loads_by_context')
                expected = (counts[str(request['context'])][request['epoch']] if counts is not None else expected_loads)
                if expected is not None and request['stats']['target_loads'] != expected:
                    raise EvidenceError('target-load count does not match the independently declared workload count')
        return dict(
            scope='fixed-execution conditional address coverage only',
            exclusions=['no rescheduled execution', 'no measured speedup', 'no prefetch benefit', 'no FPGA projection',
                        'no retained-data correctness claim'],
            sampling='stable pre-edge D-cache rising values; CSR-label commits on separate BE rising edges; physical CSR joins domains',
            l1='actual 64-set 8-way 64-byte normal L1 tag SRAM, reconstructed only from observed masked writes',
            victim_policy='exclusive FIFO of actual baseline replacement evictions; remove on actual refill; invalidate on stores and invalidation',
            stats=dict(self.stats), accepted_references_by_context=dict(self.contexts),
            target_unique_lines=len(self.target_lines), requests=self.requests,
            coverage={str(capacity): dict(self.counts[capacity], **self.ledgers[capacity].stats,
                                          unique_covered_lines=len(self.covered_lines[capacity]),
                                          warm_target_unique_lines_covered=len(self.target_covered_lines[capacity]['warm']),
                                          timed_target_unique_lines_covered=len(self.target_covered_lines[capacity]['timed']),
                                          peak_entries=self.ledgers[capacity].peak,
                                          final_entries=len(self.ledgers[capacity].lines)) for capacity in CAPACITIES},
            metadata=self.metadata, active_dcache_edges=self.sample_count, reset_observed=self.reset_seen,
            validation='passed')


def analyze(stream, metadata=None, emit=None):
    selected, widths, timescale = header(stream)
    extractor = Extractor(widths, metadata, emit)
    be_cycle = cache_cycle = 0
    for _, timestamp, value in rising_edges(stream, selected, clock_labels=('clock', 'cache_clock')):
        if 'clock' in value['_rising_clocks']:
            extractor.commit_edge(be_cycle, timestamp, value)
            be_cycle += 1
        if 'cache_clock' in value['_rising_clocks']:
            extractor.step(cache_cycle, timestamp, value, process_commit=False)
            cache_cycle += 1
    report = extractor.report()
    report.update(timescale=timescale, signals={key: item[1] for key, item in selected.items()})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--metadata', type=Path)
    parser.add_argument('--events', type=Path, help='optional complete accepted-reference/fill/eviction JSONL stream')
    args = parser.parse_args()
    metadata = json.loads(args.metadata.read_text()) if args.metadata else None
    events = args.events.open('w') if args.events else None
    try:
        emit = (lambda event: events.write(json.dumps(event, separators=(',', ':'))+'\n')) if events else None
        report = analyze(sys.stdin, metadata, emit)
    except (EvidenceError, KeyError, ValueError) as error:
        args.output.write_text(json.dumps(dict(validation='failed', error=str(error), coverage=None), indent=2)+'\n')
        print('D-cache evidence rejected: '+str(error), file=sys.stderr)
        return 1
    finally:
        if events:
            events.close()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report[key] for key in ('validation', 'stats', 'target_unique_lines', 'coverage')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
