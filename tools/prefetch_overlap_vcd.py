#!/usr/bin/env python3
"""Validate configurable-depth UCE prefetch transactions in fst2vcd output.

UCE admission, forward-pump issue, and consumed responses are separate events.
Optional AXI evidence tracks accepted AR transactions through AXI-ID-tagged R
bursts on the AXI clock, independently of the UCE clock. AXI acceptance overlap does
not establish parallel DRAM-bank service. Unknown controls, unmatched replies,
slot reuse, malformed bursts, and incomplete transactions invalidate the trace.
"""

import argparse
from collections import Counter
import json
import re
import sys

from cache_overlap_vcd import EvidenceError, rising_edges


UCE_SIGNALS = {
    'clock': 'clk_i', 'reset': 'reset_i',
    'request_v': 'cache_req_v_i', 'request_yumi': 'cache_req_yumi_o',
    'request_address': 'cache_req_cast_i.addr', 'request_type': 'cache_req_cast_i.msg_type',
    'allocate': 'prefetch_allocate', 'allocate_slot': 'prefetch_free_slot',
    'issue': 'prefetch_issue',
    'issue_slot': 'prefetch_issue_slot', 'response': 'prefetch_response',
    'fwd_v': 'fsm_fwd_v_lo', 'fwd_ready': 'fsm_fwd_ready_then_li',
    'fwd_new': 'fsm_fwd_new_lo', 'fwd_last': 'fsm_fwd_last_lo',
    'rev_v': 'fsm_rev_v_li', 'rev_yumi': 'fsm_rev_yumi_lo',
    'rev_new': 'fsm_rev_new_li', 'rev_last': 'fsm_rev_last_li',
}
OPTIONAL_UCE_SIGNALS = {
    # Older traces expose same-line merging. Current RTL acknowledges and drops
    # hints only when all configured slots are reserved.
    'duplicate': 'prefetch_duplicate',
    'drop': 'prefetch_drop',
}
for _side, _header in (('fwd', 'fsm_fwd_header_lo'), ('rev', 'fsm_rev_header_li')):
    # Verilator traces the BedRock message-type union through its members.
    for _label, _field in (('address', 'addr'), ('type', 'msg_type.' + _side), ('size', 'size'),
                           ('prefetch', 'payload.prefetch'), ('slot', 'payload.way_id'),
                           ('state', 'payload.state')):
        UCE_SIGNALS[_side + '_' + _label] = _header + '.' + _field

AXI_SIGNALS = {
    'axi_clock': 'clk_i', 'axi_reset': 'reset_i',
    'ar_v': 'axi_arvalid_i', 'ar_ready': 'axi_arready_o',
    'ar_address': 'axi_araddr_i', 'ar_id': 'axi_arid_i', 'ar_len': 'axi_arlen_i',
    'r_v': 'axi_rvalid_o', 'r_ready': 'axi_rready_i', 'r_id': 'axi_rid_o',
    'r_last': 'axi_rlast_o', 'r_resp': 'axi_rresp_o',
}

CONSUMER_SIGNALS = {
    'be_clock': 'be.clk_i',
    'commit_v': 'be.calculator.commit_pkt_cast_o.instret',
    'commit_pc': 'be.calculator.commit_pkt_cast_o.pc',
    'commit_thread': 'be.retire_thread_id_lo',
}


def signal_names(uce_prefix='dcache_uce', axi_prefix=None, consumers=False):
    names = {key: uce_prefix.rstrip('.') + '.' + suffix for key, suffix in UCE_SIGNALS.items()}
    names.update({key: uce_prefix.rstrip('.') + '.' + suffix
                  for key, suffix in OPTIONAL_UCE_SIGNALS.items()})
    if axi_prefix is not None:
        names.update({key: axi_prefix.rstrip('.') + '.' + suffix for key, suffix in AXI_SIGNALS.items()})
    if consumers:
        names.update(CONSUMER_SIGNALS)
    return names


def read_header(stream, names, optional=()):
    """Resolve exact suffixes; never silently select one of several cores."""
    scopes, found, timescale = [], {}, []
    in_timescale = False
    for line in stream:
        words = line.split()
        if '$timescale' in line:
            in_timescale = True
        if in_timescale:
            timescale.extend(word for word in words if word not in ('$timescale', '$end'))
            if '$end' in line:
                in_timescale = False
        if words[:1] == ['$scope']:
            scopes.append(words[2])
        elif words[:1] == ['$upscope']:
            scopes.pop()
        elif words[:1] == ['$var']:
            full = '.'.join(scopes + [words[4]])
            for label, suffix in names.items():
                if full == suffix or full.endswith('.' + suffix):
                    found.setdefault(label, []).append((words[3], full))
        elif words[:1] == ['$enddefinitions']:
            break
    else:
        raise EvidenceError('missing VCD enddefinitions')
    for label, suffix in names.items():
        if label not in found:
            if label in optional:
                continue
            raise EvidenceError('missing required signal: ' + suffix)
        if len(found[label]) != 1:
            raise EvidenceError('ambiguous signal: ' + suffix)
    if not timescale:
        raise EvidenceError('missing VCD timescale')
    return {label: matches[0] for label, matches in found.items()}, ''.join(timescale)


def known(values, label):
    value = values.get(label)
    if value is None:
        raise EvidenceError('unknown ' + label)
    return value


def bit(values, label):
    value = known(values, label)
    if value not in (0, 1):
        raise EvidenceError('nonbinary control ' + label)
    return value


def boundary(cycle, timestamp):
    return dict(cycle=cycle, timestamp=timestamp)


def overlap_summary(records):
    """Strict open intervals exclude a response and new issue on one edge."""
    before_first, before_complete = [], []
    events = []
    for record in records:
        issue = record['issue']['timestamp']
        complete = record['complete']['timestamp']
        # Complete events sort before new issues at a shared edge.
        if complete > issue:
            events.extend(((issue, 1), (complete, -1)))
        for previous in record.pop('_prior', []):
            if previous['issue']['timestamp'] < issue < previous['first_response']['timestamp']:
                before_first.append([previous['id'], record['id']])
            if previous['issue']['timestamp'] < issue < previous['complete']['timestamp']:
                before_complete.append([previous['id'], record['id']])
    outstanding = maximum = 0
    for _, delta in sorted(events):
        outstanding += delta
        maximum = max(maximum, outstanding)
    issues = [record['issue'] for record in records]
    first_responses = [record['first_response'] for record in records]
    completions = [record['complete'] for record in records]
    first_issue = min(issues, key=lambda event: event['timestamp']) if issues else None
    last_issue = max(issues, key=lambda event: event['timestamp']) if issues else None
    first_response = (min(first_responses, key=lambda event: event['timestamp'])
                      if first_responses else None)
    last_response = (max(completions, key=lambda event: event['timestamp'])
                     if completions else None)
    return dict(transactions=len(records), max_outstanding=maximum,
                first_issue=first_issue, last_issue=last_issue,
                issue_span=(last_issue['timestamp'] - first_issue['timestamp']) if issues else None,
                first_response=first_response, last_response=last_response,
                all_issued_before_first_response=bool(
                    issues and first_responses
                    and last_issue['timestamp'] < first_response['timestamp']),
                issue_before_prior_first_response=bool(before_first),
                issue_before_prior_completion=bool(before_complete),
                before_first_response_pairs=before_first, before_completion_pairs=before_complete)


def request_summary(records):
    """Summarize accepted non-prefetch UCE requests by type and 4 KiB page."""
    by_type = Counter(record['msg_type'] for record in records)
    by_page = Counter(record['address'] >> 12 for record in records)
    return dict(count=len(records),
                by_msg_type={str(key): value for key, value in sorted(by_type.items())},
                by_4k_page={hex(key << 12): value for key, value in sorted(by_page.items())})


def prefetch_demand_matches(prefetches, demands, line_bytes=64):
    """Correlate accepted hints with later normal L1 miss requests by line."""
    result = []
    for hint in prefetches:
        matches = [request for request in demands
                   if request['msg_type'] == 0
                   and request['address'] // line_bytes == hint['address'] // line_bytes
                   and request['timestamp'] > hint['issue']['timestamp']]
        result.append(dict(prefetch_id=hint['id'], address=hint['address'],
                           normal_miss_count=len(matches),
                           normal_miss_cycles=[request['cycle'] for request in matches]))
    return result


class Transactions:
    def __init__(self, line_bytes=64, fill_bytes=8, axi=False, prefetch_slots=2,
                 admission_mode='drop', consume_pcs=()):
        for name, value in (('line-bytes', line_bytes), ('fill-bytes', fill_bytes)):
            if value <= 0 or value & (value - 1):
                raise EvidenceError(name + ' must be a positive power of two')
        if prefetch_slots <= 0:
            raise EvidenceError('prefetch-slots must be positive')
        self.line_bytes, self.fill_bytes, self.axi = line_bytes, fill_bytes, axi
        self.line_size = line_bytes.bit_length() - 1
        self.fill_size = fill_bytes.bit_length() - 1
        self.prefetch_slots = prefetch_slots
        self.admission_mode = admission_mode
        self.slots, self.normal_pending, self.axi_pending = {}, [], []
        self.prefetches, self.normal_reads, self.hints, self.demands, self.axi_reads = [], [], [], [], []
        self.consume_pcs = set(consume_pcs)
        self.consuming_loads = []
        self.cycles = dict(clock=0)
        if axi:
            self.cycles['axi_clock'] = 0
        if consume_pcs:
            self.cycles['be_clock'] = 0

    def uce(self, v, cycle, timestamp):
        event = boundary(cycle, timestamp)
        if bit(v, 'reset'):
            if self.slots or self.normal_pending:
                raise EvidenceError('UCE reset with incomplete transactions')
            return
        admission = 'drop' if self.admission_mode == 'drop' else 'duplicate'
        for label in ('request_v', 'request_yumi', 'allocate', admission, 'issue',
                      'response', 'fwd_v', 'fwd_ready', 'rev_v', 'rev_yumi'):
            bit(v, label)
        accepted = v['request_v'] and v['request_yumi']
        if v['request_yumi'] and not v['request_v']:
            raise EvidenceError('request consumed without valid')
        hint = accepted and known(v, 'request_type') == 9
        if v['allocate'] and not hint:
            raise EvidenceError('prefetch allocation without accepted hint')
        if v[admission] and not hint:
            raise EvidenceError('prefetch %s without accepted hint' % admission)
        if hint:
            address = known(v, 'request_address')
            matching = [record for record in self.slots.values()
                        if record['address'] // self.line_bytes == address // self.line_bytes]
            self.hints.append(dict(event, address=address,
                                   **{admission: bool(v[admission])}))
            if self.admission_mode == 'duplicate' and v['duplicate']:
                if v['allocate'] or not matching:
                    raise EvidenceError('duplicate hint has no matching reserved line')
            elif self.admission_mode == 'drop' and v['drop']:
                if v['allocate'] or len(self.slots) != self.prefetch_slots:
                    raise EvidenceError('dropped hint without a full prefetch queue')
            else:
                if not v['allocate']:
                    raise EvidenceError('accepted hint was neither allocated nor advisory-dropped')
                if self.admission_mode == 'duplicate' and matching:
                    raise EvidenceError('new hint did not allocate a unique line')
                slot = known(v, 'allocate_slot')
                if not 0 <= slot < self.prefetch_slots or slot in self.slots:
                    raise EvidenceError('duplicate or invalid prefetch slot allocation')
                record = dict(id=len(self.prefetches), slot=slot, address=address & ~7,
                              accept=event, issue=None, first_response=None, complete=None,
                              beats=0, expected_beats=None, size=None)
                self.slots[slot] = record
                self.prefetches.append(record)
        elif accepted:
            self.demands.append(dict(event, address=known(v, 'request_address'),
                                     msg_type=known(v, 'request_type')))

        fwd = v['fwd_v'] and v['fwd_ready']
        issued_prefetch = False
        if fwd:
            msg_type = known(v, 'fwd_type')
            prefetch = bit(v, 'fwd_prefetch')
            if prefetch and msg_type != 0:
                raise EvidenceError('prefetch forward is not mem_rd')
            if msg_type in (0, 2):
                if not bit(v, 'fwd_new') or not bit(v, 'fwd_last'):
                    raise EvidenceError('unsupported multibeat forward read/AMO')
                address, size, wire_tag, wire_state = (
                    known(v, 'fwd_' + key) for key in ('address', 'size', 'slot', 'state'))
                if size > 6:
                    raise EvidenceError('unsupported BedRock read size')
                if prefetch:
                    slot = known(v, 'issue_slot')
                    record = self.slots.get(slot)
                    if (record is None or record['issue'] is not None
                            or record['accept']['timestamp'] >= timestamp):
                        raise EvidenceError('prefetch issue has no earlier unissued slot allocation')
                    if size not in (3, self.line_size) or address != record['address']:
                        raise EvidenceError('prefetch issue address/size mismatch')
                    if not v['issue']:
                        raise EvidenceError('prefetch issue pulse/slot mismatch')
                    record['_prior'] = [other for other in self.slots.values()
                                        if other['issue'] is not None]
                    record['wire_tag'] = wire_tag
                    record['wire_state'] = wire_state
                    record['size'] = size
                    record['expected_beats'] = max(1, (1 << size) // self.fill_bytes)
                    record['issue'] = event
                    issued_prefetch = True
                else:
                    if self.normal_pending:
                        raise EvidenceError('multiple normal UCE reads are unsupported')
                    if any(other['address'] // self.line_bytes == address // self.line_bytes
                           for other in self.slots.values()):
                        raise EvidenceError('normal read issued before same-line prefetch completion')
                    record = dict(id=len(self.normal_reads), address=address, slot=wire_tag,
                                  msg_type=msg_type, size=size, issue=event,
                                  first_response=None, complete=None, beats=0)
                    self.normal_reads.append(record)
                    self.normal_pending.append(record)
        if bool(v['issue']) != issued_prefetch:
            raise EvidenceError('prefetch issue without accepted forward read')

        response = v['rev_v'] and v['rev_yumi']
        consumed_prefetch = False
        if response:
            msg_type, prefetch = known(v, 'rev_type'), bit(v, 'rev_prefetch')
            if prefetch and msg_type != 0:
                raise EvidenceError('prefetch response is not mem_rd')
            if msg_type in (0, 2):
                address, size, wire_tag, wire_state = (
                    known(v, 'rev_' + key) for key in ('address', 'size', 'slot', 'state'))
                first, last = bit(v, 'rev_new'), bit(v, 'rev_last')
                if prefetch:
                    matching = [record for record in self.slots.values()
                                if record['issue'] is not None
                                and (address == record['address'] + record['beats'] * self.fill_bytes
                                     or (record['beats'] > 0 and address == record['address']))]
                    if len(matching) != 1:
                        pending = [(record['id'], hex(record['address']), record['beats'],
                                    record['expected_beats'])
                                   for record in self.slots.values()
                                   if record['issue'] is not None]
                        raise EvidenceError('unmatched prefetch response address=%s size=%d pending=%s'
                                            % (hex(address), size, pending))
                    record = matching[0]
                    if (size not in (record['size'], self.fill_size)
                            or first != (record['beats'] == 0)
                            or last != (record['beats'] + 1 == record['expected_beats'])):
                        raise EvidenceError('prefetch response address/size/boundary mismatch')
                    record['beats'] += 1
                    if first:
                        record['first_response'] = event
                    if last:
                        record['complete'] = event
                        del self.slots[record['slot']]
                    consumed_prefetch = True
                else:
                    if not self.normal_pending:
                        raise EvidenceError('unmatched normal read response')
                    record = self.normal_pending[0]
                    if (address, size, wire_tag, msg_type) != tuple(record[key] for key in ('address', 'size', 'slot', 'msg_type')):
                        raise EvidenceError('normal read response identity mismatch')
                    expected = max(1, (1 << size) // self.fill_bytes)
                    if first != (record['beats'] == 0) or last != (record['beats'] + 1 == expected):
                        raise EvidenceError('normal read response boundary/count mismatch')
                    record['beats'] += 1
                    if first:
                        record['first_response'] = event
                    if last:
                        record['complete'] = event
                        self.normal_pending.pop(0)
        if bool(v['response']) != consumed_prefetch:
            raise EvidenceError('prefetch response pulse without consumed response')

    def axi_edge(self, v, cycle, timestamp):
        event = boundary(cycle, timestamp)
        if bit(v, 'axi_reset'):
            if self.axi_pending:
                raise EvidenceError('AXI reset with incomplete transactions')
            return
        for label in ('ar_v', 'ar_ready', 'r_v', 'r_ready'):
            bit(v, label)
        if v['ar_v'] and v['ar_ready']:
            txn_id = known(v, 'ar_id')
            length = known(v, 'ar_len')
            if not 0 <= length <= 255:
                raise EvidenceError('invalid AXI ARLEN')
            record = dict(id=len(self.axi_reads), axi_id=txn_id,
                          address=known(v, 'ar_address'), expected_beats=length + 1, beats=0,
                          issue=event, first_response=None, complete=None,
                          _prior=list(self.axi_pending))
            self.axi_reads.append(record)
            self.axi_pending.append(record)
        if v['r_v'] and v['r_ready']:
            if not self.axi_pending:
                raise EvidenceError('unmatched AXI response')
            response_id = known(v, 'r_id')
            if known(v, 'r_resp') != 0:
                raise EvidenceError('AXI non-OKAY response')
            matches = [record for record in self.axi_pending
                       if record['axi_id'] == response_id]
            if not matches:
                raise EvidenceError('unmatched AXI response ID')
            record = matches[0]
            record['beats'] += 1
            last = bit(v, 'r_last')
            if last != (record['beats'] == record['expected_beats']):
                raise EvidenceError('AXI RLAST/count mismatch')
            if record['first_response'] is None:
                record['first_response'] = event
            if last:
                record['complete'] = event
                self.axi_pending.remove(record)

    def be_edge(self, v, cycle, timestamp):
        commit_v = known(v, 'commit_v')
        if commit_v not in (0, 1):
            raise EvidenceError('nonbinary control commit_v')
        if commit_v != 1:
            return
        pc = known(v, 'commit_pc')
        if pc in self.consume_pcs:
            self.consuming_loads.append(dict(cycle=cycle, timestamp=timestamp, pc=pc,
                                             thread=known(v, 'commit_thread')))

    def finish(self, allow_no_prefetch=False):
        if self.slots or self.normal_pending or self.axi_pending:
            raise EvidenceError('trace ended with incomplete transactions')
        if not self.prefetches and not allow_no_prefetch:
            raise EvidenceError('no allocated prefetch transactions')
        uce = overlap_summary(self.prefetches)
        uce['max_reserved_slots'] = max_reserved_slots(self.prefetches)
        axi = overlap_summary(self.axi_reads) if self.axi else None
        return dict(verdict='valid_transactions', prefetch_summary=uce, axi_summary=axi,
                    prefetches=self.prefetches, accepted_hints=self.hints,
                    normal_requests=self.demands, normal_reads=self.normal_reads,
                    normal_request_summary=request_summary(self.demands),
                    consuming_loads=self.consuming_loads,
                    axi_reads=self.axi_reads if self.axi else None,
                    backing_service_overlap='not observable from AXI handshakes',
                    axi_prefetch_attribution='not inferred; AXI also carries other cache traffic')


def analyze(stream, uce_prefix='dcache_uce', axi_prefix=None, line_bytes=64, fill_bytes=8,
            prefetch_slots=2, allow_no_prefetch=False, consume_pcs=()):
    selected, timescale = read_header(stream, signal_names(uce_prefix, axi_prefix, consume_pcs),
                                      optional=OPTIONAL_UCE_SIGNALS)
    admission_modes = [label for label in OPTIONAL_UCE_SIGNALS if label in selected]
    if len(admission_modes) != 1:
        raise EvidenceError('trace must contain exactly one prefetch admission policy signal')
    tracker = Transactions(line_bytes, fill_bytes, axi_prefix is not None, prefetch_slots,
                           admission_modes[0], consume_pcs)
    clocks = ['clock']
    if axi_prefix is not None:
        clocks.append('axi_clock')
    if consume_pcs:
        clocks.append('be_clock')
    clocks = tuple(clocks)
    for _, timestamp, values in rising_edges(stream, selected, clocks):
        for clock in values.get('_rising_clocks', ['clock']):
            cycle = tracker.cycles[clock]
            tracker.cycles[clock] += 1
            try:
                if clock == 'clock':
                    tracker.uce(values, cycle, timestamp)
                elif clock == 'axi_clock':
                    tracker.axi_edge(values, cycle, timestamp)
                else:
                    tracker.be_edge(values, cycle, timestamp)
            except EvidenceError as error:
                raise EvidenceError('%s cycle %d timestamp %d: %s' % (clock, cycle, timestamp, error)) from error
    for clock in clocks:
        if tracker.cycles[clock] == 0:
            raise EvidenceError('no observed rising edges for ' + clock)
    report = tracker.finish(allow_no_prefetch=allow_no_prefetch)
    report['prefetch_demand_matches'] = prefetch_demand_matches(
        report['prefetches'], report['normal_requests'], line_bytes)
    report.update(timescale=timescale, line_bytes=line_bytes, fill_bytes=fill_bytes,
                  configured_prefetch_slots=prefetch_slots,
                  prefetch_admission_mode=admission_modes[0],
                  signals={key: value[1] for key, value in selected.items()},
                  cycles=tracker.cycles,
                  sampling='stable values before each domain rising edge; independent cycle counters',
                  uce_issue_boundary='accepted UCE forward-pump read, not AXI acceptance')
    return report


def marker_window(stream, begin_id, end_id):
    pattern = re.compile(r'CTXTSW_GLOBAL_MARKER id=(\d+) time_ps=(\d+) cycle=(\d+)')
    found = {}
    for line in stream:
        match = pattern.search(line)
        if match:
            marker_id, timestamp, cycle = map(int, match.groups())
            if marker_id in (begin_id, end_id):
                if marker_id in found:
                    raise EvidenceError('duplicate global marker id %d' % marker_id)
                found[marker_id] = dict(timestamp=timestamp, cycle=cycle)
    missing = [marker_id for marker_id in (begin_id, end_id) if marker_id not in found]
    if missing:
        raise EvidenceError('missing global marker id(s): ' + ', '.join(map(str, missing)))
    if found[begin_id]['timestamp'] >= found[end_id]['timestamp']:
        raise EvidenceError('global marker window is empty or reversed')
    return dict(begin=found[begin_id], end=found[end_id],
                begin_id=begin_id, end_id=end_id)


def commit_window(events, begin_pc, end_pc, expected_windows=None):
    """Validate complete ordered pairs, then select the final measured pair."""
    if begin_pc == end_pc:
        raise EvidenceError('committed begin/end PCs must differ')
    if expected_windows is not None and expected_windows <= 0:
        raise EvidenceError('expected-windows must be positive')
    pending, pairs, previous_timestamp = None, [], None
    for event in events:
        if event['pc'] not in (begin_pc, end_pc):
            continue
        timestamp = event['timestamp']
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise EvidenceError('committed window boundaries are not strictly ordered')
        previous_timestamp = timestamp
        if event['pc'] == begin_pc:
            if pending is not None:
                raise EvidenceError('committed begin PC before previous window ended')
            pending = event
        else:
            if pending is None:
                raise EvidenceError('committed end PC without preceding begin PC')
            # retire_thread_id identifies a physical resident bank. A logical
            # context may resume in another bank during a nonresident ring.
            pairs.append((pending, event))
            pending = None
    if pending is not None:
        raise EvidenceError('incomplete final committed window')
    if not pairs:
        raise EvidenceError('missing committed begin/end PC')
    if expected_windows is not None and len(pairs) != expected_windows:
        raise EvidenceError('expected %d committed windows, observed %d'
                            % (expected_windows, len(pairs)))
    begin, end = pairs[-1]
    return dict(begin=begin, end=end, begin_pc=begin_pc, end_pc=end_pc,
                window_count=len(pairs))


def matched_window_summary(report, window, address, span_bytes, axi_address_xor=0,
                           axi_address_offset=0, consumer_pcs=()):
    """Summarize measured-region events strictly inside the selected window."""
    begin, end = window['begin']['timestamp'], window['end']['timestamp']
    region_end = address + span_bytes

    def in_window(event):
        return begin < event['timestamp'] < end

    def in_region(value):
        return address <= value < region_end

    prefetches = [record for record in report['prefetches']
                  if in_region(record['address']) and in_window(record['accept'])]
    normal_reads = [record for record in report['normal_reads']
                    if in_region(record['address']) and in_window(record['issue'])]
    requests = prefetches if prefetches else normal_reads
    axi_reads = [record for record in report['axi_reads'] or []
                 if in_region((record['address'] - axi_address_offset) ^ axi_address_xor)
                 and in_window(record['issue'])]
    axi_prefetch_reads = [record for record in axi_reads if record['axi_id'] != 0]
    axi_ordinary_reads = [record for record in axi_reads if record['axi_id'] == 0]
    hints = [record for record in report['accepted_hints']
             if in_region(record['address']) and in_window(record)]
    consumers = [event for event in report['consuming_loads']
                 if in_window(event) and (not consumer_pcs or event['pc'] in consumer_pcs)]

    def event_extent(events):
        if not events:
            return dict(count=0, first=None, last=None, span=None)
        first = min(events, key=lambda event: event['timestamp'])
        last = max(events, key=lambda event: event['timestamp'])
        return dict(count=len(events), first=first, last=last,
                    span=last['timestamp'] - first['timestamp'])

    def crossing_begin(records):
        return [dict(address=record['address'],
                     transaction_id=record.get('axi_id'),
                     issue=record['issue'], complete=record['complete'])
                for record in records
                if record['issue']['timestamp'] < begin < record['complete']['timestamp']]

    def summarize(records):
        # The full-trace summary consumed its _prior lists. Rebuild them only
        # from selected transactions so warmup cannot supply overlap evidence.
        copies, pending = [], []
        for original in sorted(records, key=lambda record: record['issue']['timestamp']):
            record = dict(original)
            pending = [prior for prior in pending
                       if prior['complete']['timestamp'] > record['issue']['timestamp']]
            record['_prior'] = list(pending)
            copies.append(record)
            pending.append(record)
        return overlap_summary(copies)

    crossing_uce = crossing_begin(report['prefetches'] + report['normal_reads'])
    crossing_axi = crossing_begin(report['axi_reads'] or [])

    return dict(window=window, address_range=[address, region_end],
                outstanding_at_begin=dict(
                    uce=len(crossing_uce), axi=len(crossing_axi),
                    uce_transactions=crossing_uce, axi_transactions=crossing_axi),
                hint_acceptance=event_extent(hints),
                prefetch_max_reserved_slots=max_reserved_slots(prefetches),
                uce=summarize(requests), axi=summarize(axi_reads),
                axi_prefetch=summarize(axi_prefetch_reads),
                axi_ordinary=summarize(axi_ordinary_reads),
                consuming_loads=event_extent(consumers),
                request_kind='prefetch' if prefetches else 'demand' if normal_reads else 'none',
                timestamps='VCD timescale; compare timestamps, not independent domain cycle counters')


def max_reserved_slots(records):
    """Return peak accepted/issued-but-incomplete transactions in *records*."""
    events = [((record.get('accept') or record['issue'])['timestamp'], 1)
              for record in records]
    events += [(record['complete']['timestamp'], -1) for record in records]
    reserved = maximum = 0
    for _, delta in sorted(events):
        reserved += delta
        maximum = max(maximum, reserved)
    return maximum


def region_summary(report, address, span_bytes, axi_address_xor=0, axi_address_offset=0):
    """Qualify AXI evidence by a physical data region and an outstanding hint.

    The AXI protocol carries no UCE slot ID. A matching line and time interval
    are recorded as correlation, not as a traced end-to-end transaction ID.
    Earlier loader reads and later demand reads cannot satisfy that interval.
    """
    if report.get('verdict') != 'valid_transactions':
        raise EvidenceError('region selection requires validated transactions')
    if address < 0 or span_bytes <= 0 or axi_address_xor < 0 or axi_address_offset < 0:
        raise EvidenceError('invalid address region or AXI address mapping')
    end = address + span_bytes
    line_bytes = report['line_bytes']

    def in_region(value):
        return address <= value < end

    def summarize(records):
        copies, pending = [], []
        for original in records:
            record = dict(original)
            pending = [prior for prior in pending
                       if prior['complete']['timestamp'] >= record['issue']['timestamp']]
            record['_prior'] = list(pending)
            copies.append(record)
            pending.append(record)
        summary = overlap_summary(copies)
        summary['max_reserved_slots'] = max_reserved_slots(records)
        return summary

    prefetches = [record for record in report['prefetches'] if in_region(record['address'])]
    if not prefetches:
        raise EvidenceError('no prefetch transactions in selected region')
    candidates, correlated = [], []
    for record in report['axi_reads'] or []:
        physical = (record['address'] - axi_address_offset) ^ axi_address_xor
        if not in_region(physical):
            continue
        timestamp = record['issue']['timestamp']
        matches = [hint['id'] for hint in prefetches
                   if hint['address'] // line_bytes == physical // line_bytes
                   and hint['issue']['timestamp'] < timestamp < hint['complete']['timestamp']
                   and record['complete']['timestamp'] <= hint['complete']['timestamp']]
        if len(matches) > 1:
            raise EvidenceError('ambiguous prefetch/AXI line and time correlation')
        item = dict(record, physical_address=physical, matching_prefetch_ids=matches)
        candidates.append(item)
        if matches:
            correlated.append(item)
    return dict(address_range=[address, end], axi_address_xor=axi_address_xor,
                axi_address_offset=axi_address_offset,
                prefetches=prefetches, prefetch_summary=summarize(prefetches),
                axi_region_reads=candidates, axi_correlated_reads=correlated,
                axi_summary=summarize(correlated) if report['axi_reads'] is not None else None,
                attribution='same physical line, AXI acceptance after prefetch issue, and AXI completion no later than prefetch response; correlation, not an AXI transaction source ID')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uce-prefix', default='dcache_uce')
    parser.add_argument('--axi-prefix', help='optional AXI memory module prefix, typically axi_mem')
    parser.add_argument('--line-bytes', type=int, default=64)
    parser.add_argument('--fill-bytes', type=int, default=8)
    parser.add_argument('--prefetch-slots', type=int, default=2)
    parser.add_argument('--address', type=lambda value: int(value, 0), help='optional physical data-region start')
    parser.add_argument('--span-bytes', type=lambda value: int(value, 0))
    parser.add_argument('--axi-address-xor', type=lambda value: int(value, 0), default=0,
                        help='map AXI addresses to physical addresses for region correlation')
    parser.add_argument('--axi-address-offset', type=lambda value: int(value, 0), default=0,
                        help='subtract the host DRAM base before applying axi-address-xor')
    parser.add_argument('--require-uce-overlap', action='store_true')
    parser.add_argument('--require-axi-overlap', action='store_true')
    parser.add_argument('--require-reserved-slots', type=int, default=0,
                        help='fail unless at least this many UCE slots coexist')
    parser.add_argument('--allow-no-prefetch', action='store_true',
                        help='accept a demand-only trace and still report cache traffic')
    parser.add_argument('--consume-pc', action='append', type=lambda value: int(value, 0), default=[],
                        help='exact retired consuming-load PC; may be repeated')
    parser.add_argument('--run-log', help='simulator log containing begin/end global markers')
    parser.add_argument('--begin-marker', type=lambda value: int(value, 0))
    parser.add_argument('--end-marker', type=lambda value: int(value, 0))
    parser.add_argument('--begin-pc', type=lambda value: int(value, 0),
                        help='exact committed start-counter PC for the measured window')
    parser.add_argument('--end-pc', type=lambda value: int(value, 0),
                        help='exact committed end-counter PC for the measured window')
    parser.add_argument('--expected-windows', type=int,
                        help='required number of complete committed-PC windows, including warmup')
    parser.add_argument('--matched-only', action='store_true',
                        help='print only the BEGIN/END-filtered matched-window summary')
    args = parser.parse_args()
    try:
        if (args.address is None) != (args.span_bytes is None):
            raise EvidenceError('address and span-bytes must be supplied together')
        pc_args = (args.begin_pc, args.end_pc)
        if any(value is not None for value in pc_args) and not all(
                value is not None for value in pc_args):
            raise EvidenceError('begin-pc and end-pc must be supplied together')
        if args.expected_windows is not None:
            if args.begin_pc is None:
                raise EvidenceError('expected-windows requires begin-pc and end-pc')
            if args.expected_windows <= 0:
                raise EvidenceError('expected-windows must be positive')
        tracked_pcs = list(args.consume_pc)
        if args.begin_pc is not None:
            tracked_pcs.extend(pc_args)
        report = analyze(sys.stdin, args.uce_prefix, args.axi_prefix, args.line_bytes,
                         args.fill_bytes, args.prefetch_slots, args.allow_no_prefetch,
                         tracked_pcs)
        if args.address is not None and not args.matched_only:
            report['region'] = region_summary(report, args.address, args.span_bytes,
                                              args.axi_address_xor, args.axi_address_offset)
        marker_args = (args.run_log, args.begin_marker, args.end_marker)
        if any(value is not None for value in marker_args) and args.begin_pc is not None:
            raise EvidenceError('select either host-marker or committed-PC windowing')
        if args.begin_pc is not None:
            if args.address is None:
                raise EvidenceError('committed-PC windowing requires address and span-bytes')
            window = commit_window(report['consuming_loads'], args.begin_pc, args.end_pc,
                                   args.expected_windows)
            report['matched_window'] = matched_window_summary(
                report, window, args.address, args.span_bytes, args.axi_address_xor,
                args.axi_address_offset, set(args.consume_pc))
        elif any(value is not None for value in marker_args):
            if (args.address is None or args.run_log is None
                    or args.begin_marker is None or args.end_marker is None):
                raise EvidenceError('run-log, begin/end markers, address and span-bytes are required together')
            with open(args.run_log) as log:
                window = marker_window(log, args.begin_marker, args.end_marker)
            report['matched_window'] = matched_window_summary(
                report, window, args.address, args.span_bytes, args.axi_address_xor,
                args.axi_address_offset, set(args.consume_pc))
    except (EvidenceError, ValueError) as error:
        print(json.dumps(dict(verdict='invalid_trace', error=str(error))))
        return 2
    if args.matched_only:
        if 'matched_window' not in report:
            print(json.dumps(dict(verdict='invalid_trace',
                                  error='matched-only requires a marker or committed-PC window')))
            return 2
        print(json.dumps(report['matched_window'], indent=2))
    else:
        print(json.dumps(report, indent=2))
    if 'matched_window' in report:
        gate = report['matched_window']
        uce_overlap = (gate['request_kind'] == 'prefetch'
                       and gate['uce']['issue_before_prior_first_response'])
        axi_overlap = gate['axi_prefetch']['issue_before_prior_first_response']
        reserved_slots = gate['prefetch_max_reserved_slots']
    else:
        gate = report.get('region', report)
        uce_overlap = gate['prefetch_summary']['issue_before_prior_first_response']
        axi_overlap = bool(gate['axi_summary']
                           and gate['axi_summary']['issue_before_prior_first_response'])
        reserved_slots = gate['prefetch_summary']['max_reserved_slots']
    return int((args.require_uce_overlap and not uce_overlap)
               or (args.require_axi_overlap and not axi_overlap)
               or reserved_slots < args.require_reserved_slots)


if __name__ == '__main__':
    sys.exit(main())
