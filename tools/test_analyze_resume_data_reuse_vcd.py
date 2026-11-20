"""Check complete D-cache extraction and exclusive baseline-victim accounting.

Small independently specified traces test normal hits, actual tag evictions,
fill matching, interference, invalidation, and rejection of partial evidence.
These fixtures do not predict target execution time or FPGA performance.
"""
from copy import deepcopy
import io
import unittest

from analyze_resume_data_reuse_vcd import CAPACITIES, D, WATCH, Extractor, EvidenceError, analyze, normalize_metadata


def widths():
    result = {key: 1 for key in WATCH}
    result.update(context_0=2, context_1=2, data_mask=8)
    for way in range(8):
        for kind in ('data_li', 'data_lo', 'mask_li'):
            result['%s_%d_tag' % (kind, way)] = 20
            result['%s_%d_state' % (kind, way)] = 3
    return result


class Trace:
    def __init__(self, metadata=None):
        self.events = []
        self.extractor = Extractor(widths(), metadata, self.events.append)
        self.cycle = 0
        self.samples = []
        self.read_output = [(0, 0)] * 8
        self.rows = [[(0, 0)] * 8 for _ in range(64)]
        self.push(reset=1)
        for index in range(64):
            update = dict(tag_v=1, tag_w=1, tag_index=index, tag_packet_v=1,
                          tag_packet_yumi=1, tag_opcode=0)
            for way in range(8):
                update['mask_li_%d_state' % way] = 7
                update['mask_li_%d_tag' % way] = (1 << 20)-1
            self.push(**update)

    def push(self, **changes):
        value = {key: 0 for key in widths()}
        value.update(sets=64, ways=8, block_bits=512, num_threads=2, num_contexts=4,
                     context_0=0, context_1=1, global_cycle=self.cycle)
        for way, (state, tag) in enumerate(self.read_output):
            value['data_lo_%d_state' % way] = state
            value['data_lo_%d_tag' % way] = tag
        value.update(changes)
        self.samples.append(deepcopy(value))
        self.extractor.step(self.cycle, self.cycle * 20, value)
        if value['tag_v'] and not value['tag_w']:
            self.read_output = list(self.rows[value['tag_index']])
        if value['tag_v'] and value['tag_w']:
            index = value['tag_index']
            for way, (state, tag) in enumerate(self.rows[index]):
                if value['mask_li_%d_state' % way]:
                    state = value['data_li_%d_state' % way]
                if value['mask_li_%d_tag' % way]:
                    tag = value['data_li_%d_tag' % way]
                self.rows[index][way] = state, tag
        self.cycle += 1

    def miss(self, address, store=False, **extra):
        self.push(v=1, address=address, store=int(store), load=int(not store), request_v=1,
                  request_yumi=1, request_address=address, store_req=int(store), load_req=int(not store), **extra)

    def fill(self, address, way, **extra):
        line = address & ~63
        for beat in range(8):
            changes = dict(data_v=1, data_yumi=1, data_opcode=0, data_address=line + beat*8,
                           data_index=(line >> 6) & 63, data_way=way, data_mask=1 << beat,
                           critical=int(beat == 0), complete=int(beat == 7))
            if beat == 0:
                changes.update(tag_v=1, tag_w=1, tag_index=(line >> 6) & 63,
                               tag_packet_v=1, tag_packet_yumi=1, tag_opcode=1)
                changes['mask_li_%d_state' % way] = 7
                changes['mask_li_%d_tag' % way] = (1 << 20)-1
                changes['data_li_%d_state' % way] = 6
                changes['data_li_%d_tag' % way] = line >> 12
            changes.update(extra)
            self.push(**changes)

    def hit(self, address, way=0, store=False, **extra):
        self.push(tag_v=1, tag_w=0, tag_index=(address >> 6) & 63)
        self.push(v=1, address=address, store=int(store), load=int(not store), result_v=1,
                  cache_hit=1, store_hit=1, load_vector=1 << way, store_vector=1 << way, **extra)

    def report(self):
        return self.extractor.report()


def vcd(samples, omit=None, opposite=False):
    names = dict(WATCH)
    for key in widths():
        if key.startswith('context_'):
            names[key] = 'be.physical_thread_context_id_r[%s]' % key.split('_')[1]
        elif key.startswith(('data_li_', 'mask_li_', 'data_lo_')):
            kind, suffix = key.rsplit('_', 1)
            kind, way = kind.rsplit('_', 1)
            names[key] = D+'tag_mem_%s[%s].%s' % (kind, way, suffix)
    fields = [key for key in names if key != omit]
    codes = {key: 'code%d' % index for index, key in enumerate(fields)}
    rows = ['$timescale 1ps $end', '$scope module TOP $end']
    for key in fields:
        # VCD reference identifiers may contain dots; full names still resolve.
        rows.append('$var wire 64 %s %s $end' % (codes[key], names[key]))
    rows += ['$upscope $end', '$enddefinitions $end']
    for index, sample in enumerate(samples):
        rows.append('#%d' % (index * 20))
        for key in fields:
            value = 0 if key in ('clock', 'cache_clock') else sample[key]
            rows.append('b%s %s' % (bin(value)[2:], codes[key]))
        if opposite:
            # Deliberately make the normal-tag write port inactive at BE
            # posedge, then restore it before D-cache posedge on BE negedge.
            rows += ['b0 '+codes['tag_v'], 'b0 '+codes['tag_w'],
                     '#%d' % (index * 20 + 5), 'b1 '+codes['clock'],
                     '#%d' % (index * 20 + 7),
                     'b%s %s' % (sample['tag_v'], codes['tag_v']),
                     'b%s %s' % (sample['tag_w'], codes['tag_w']),
                     '#%d' % (index * 20 + 10), 'b0 '+codes['clock'], 'b1 '+codes['cache_clock']]
        else:
            rows += ['#%d' % (index * 20 + 10), 'b1 '+codes['clock'], 'b1 '+codes['cache_clock']]
    # Return the source field widths required by the typed signal contract.
    declared = '\n'.join(rows)+'\n'
    for key, width in widths().items():
        if key in codes:
            declared = declared.replace('$var wire 64 '+codes[key]+' ', '$var wire %d %s ' % (width, codes[key]))
    return declared


class DataReuseTests(unittest.TestCase):
    def baseline(self):
        trace = Trace()
        trace.miss(0x80000000)
        trace.fill(0x80000000, 0)
        trace.hit(0x80000008)
        return trace

    def test_exact_normal_hits_complete_refills_and_actual_victim_coverage(self):
        trace = self.baseline()
        # Real writes choose way 0; no software replacement policy infers it.
        trace.miss(0x80001000)
        trace.fill(0x80001000, 0)
        trace.miss(0x80000000)
        trace.fill(0x80000000, 0)
        report = trace.report()
        self.assertEqual(report['stats']['accepted_cached_references'], 4)
        self.assertEqual(report['stats']['normal_l1_hits'], 1)
        self.assertEqual(report['stats']['ordinary_misses'], 3)
        self.assertEqual(report['stats']['matched_complete_normal_refills'], 3)
        self.assertEqual(report['stats']['matched_normal_fill_beats'], 24)
        self.assertEqual(report['stats']['actual_replacement_evictions'], 2)
        for capacity in CAPACITIES:
            self.assertEqual(report['coverage'][str(capacity)].get('covered_ordinary_misses', 0), bool(capacity))
            self.assertEqual(report['coverage'][str(capacity)]['unique_covered_lines'], bool(capacity))
            self.assertLessEqual(report['coverage'][str(capacity)]['peak_entries'], capacity)
        self.assertNotIn(0x80000000, trace.extractor.ledgers[4].lines)
        self.assertIn(0x80001000, trace.extractor.ledgers[4].lines)

    def test_existing_l1_hits_are_never_extra_capacity(self):
        trace = self.baseline()
        trace.hit(0x80000010)
        report = trace.report()
        for ledger in report['coverage'].values():
            self.assertEqual(ledger.get('covered_ordinary_misses', 0), 0)
            self.assertEqual(ledger['peak_entries'], 0)

    def test_store_invalidates_retained_copy_and_all_interference_counts(self):
        trace = self.baseline()
        trace.miss(0x80001000)
        trace.fill(0x80001000, 0)
        trace.miss(0x80000000, store=True, thread=1)
        trace.fill(0x80000000, 0)
        report = trace.report()
        self.assertEqual(report['stats']['accepted_cached_stores'], 1)
        self.assertEqual(report['accepted_references_by_context']['1'], 1)
        self.assertEqual(report['coverage']['4']['store_invalidations'], 1)
        self.assertNotIn(0x80000000, trace.extractor.ledgers[4].lines)
        self.assertEqual(report['target_unique_lines'], 0)

    def test_fence_invalidation_clears_victims_without_publishing_invalid_lines(self):
        trace = self.baseline()
        trace.miss(0x80001000)
        trace.fill(0x80001000, 0)
        trace.push(request_v=1, request_yumi=1, inval_req=1)
        trace.miss(0x80000000)
        trace.fill(0x80000000, 0)
        report = trace.report()
        self.assertEqual(report['stats']['global_invalidation_requests'], 1)
        self.assertEqual(report['coverage']['4'].get('covered_ordinary_misses', 0), 0)

    def test_uncached_snoop_replay_and_unaccepted_attempts_are_not_new_references(self):
        trace = self.baseline()
        for flag in ('uncached', 'snoop', 'replay', 'prefetch', 'cache_op', 'sc_fail'):
            trace.push(v=1, load=1, address=0xdeadbeef, result_v=1, **{flag: 1})
        trace.push(v=1, load=1, address=0x80001000)  # Rejected/stalled attempt.
        self.assertEqual(trace.report()['stats']['accepted_cached_references'], 2)
        self.assertEqual(trace.report()['stats']['unaccepted_tv_attempts'], 1)

    def test_sync_read_divergence_and_hit_vector_divergence_fail_closed(self):
        trace = self.baseline()
        trace.push(tag_v=1, tag_index=0)
        with self.assertRaisesRegex(EvidenceError, 'synchronous tag read'):
            trace.push(data_lo_0_tag=0)
        trace = self.baseline()
        with self.assertRaisesRegex(EvidenceError, 'hit vectors'):
            trace.push(v=1, load=1, address=0x80000000, result_v=1)

    def test_unmatched_missing_duplicate_and_incomplete_refill_evidence_rejected(self):
        trace = self.baseline()
        with self.assertRaisesRegex(EvidenceError, 'without matching'):
            trace.push(data_v=1, data_yumi=1, data_address=0x80001000, data_mask=1)
        trace = self.baseline()
        trace.miss(0x80001000)
        with self.assertRaisesRegex(EvidenceError, 'unmatched'):
            trace.report()
        with self.assertRaisesRegex(EvidenceError, 'invalid or repeated beat'):
            trace.fill(0x80001000, 0, data_mask=1)
        trace = self.baseline()
        trace.miss(0x80001000)
        with self.assertRaisesRegex(EvidenceError, 'all eight unique beats'):
            trace.fill(0x80001000, 0, complete=1)

    def test_incomplete_initialization_unknowns_and_prefetch_abort_evidence(self):
        extractor = Extractor(widths())
        extractor.step(0, 0, {'reset': 1})
        value = {key: 0 for key in widths()}
        value.update(sets=64, ways=8, block_bits=512, num_threads=2, num_contexts=4,
                     v=1, load=1, request_v=1, request_yumi=1, load_req=1)
        with self.assertRaisesRegex(EvidenceError, 'initialization'):
            extractor.step(1, 20, value)
        trace = self.baseline()
        with self.assertRaisesRegex(EvidenceError, 'unknown address'):
            trace.push(address=None)
        trace = self.baseline()
        with self.assertRaisesRegex(EvidenceError, 'accepted prefetch'):
            trace.push(request_v=1, request_yumi=1, prefetch_req=1)

    def test_phases_logical_mapping_and_independent_target_load_counts(self):
        metadata = dict(begin_pc='0x1000', end_pc='0x1004', warmup_requests=1, timed_requests=1,
                        expected_target_loads_by_context={str(context): [1, 1] for context in range(4)},
                        regions=[dict(context=context, base=0x80000000 + context*64, bytes=64) for context in range(4)])
        trace = Trace(metadata)
        for context in range(4):
            trace.miss(0x80000000 + context*64)
            trace.fill(0x80000000 + context*64, 0)
        for epoch in range(2):
            for context in range(4):
                # Deliberately remap physical slot 1 on each request.
                shared = dict(context_1=context, commit_thread=1, thread=1)
                trace.push(commit_v=1, commit_pc=0x1000, **shared)
                trace.hit(0x80000000 + context*64, **shared)
                trace.push(commit_v=1, commit_pc=0x1004, **shared)
        report = trace.report()
        self.assertEqual(len(report['requests']), 8)
        self.assertEqual(report['target_unique_lines'], 4)
        self.assertEqual([request['phase'] for request in report['requests']], ['warm']*4 + ['timed']*4)
        self.assertTrue(all(request['stats']['target_loads'] == 1 for request in report['requests']))
        streamed = analyze(io.StringIO(vcd(trace.samples, opposite=True)), metadata)
        self.assertEqual(len(streamed['requests']), 8)
        self.assertTrue(all(request['stats']['target_loads'] == 1 for request in streamed['requests']))
        trace.extractor.requests[0]['stats']['target_loads'] = 0
        with self.assertRaisesRegex(EvidenceError, 'target-load count'):
            trace.report()

    def test_streamed_vcd_edges_resolve_full_signal_contract_and_missing_signal_fails(self):
        trace = self.baseline()
        report = analyze(io.StringIO(vcd(trace.samples)))
        self.assertEqual(report['validation'], 'passed')
        self.assertEqual(report['stats']['normal_l1_hits'], 1)
        with self.assertRaisesRegex(EvidenceError, 'missing/ambiguous signal tag_w'):
            analyze(io.StringIO(vcd(trace.samples, omit='tag_w')))

    def test_actual_dcache_rising_edges_can_differ_from_be_rising_decisions(self):
        trace = self.baseline()
        report = analyze(io.StringIO(vcd(trace.samples, opposite=True)))
        self.assertEqual(report['validation'], 'passed')
        self.assertEqual(report['stats']['matched_complete_normal_refills'], 1)
        self.assertEqual(report['stats']['normal_l1_hits'], 1)

    def test_fifo_capacity_counts_are_based_on_evictions_only(self):
        trace = self.baseline()
        for index in range(1, 7):
            trace.miss(0x80000000 + index*4096)
            trace.fill(0x80000000 + index*4096, 0)
        trace.miss(0x80000000)
        trace.fill(0x80000000, 0)
        report = trace.report()
        self.assertEqual(report['coverage']['4'].get('covered_ordinary_misses', 0), 0)
        self.assertEqual(report['coverage']['16']['covered_ordinary_misses'], 1)
        self.assertEqual(report['coverage']['4']['peak_entries'], 4)

    def test_metadata_rejects_overlapping_private_regions(self):
        with self.assertRaisesRegex(EvidenceError, 'overlap'):
            normalize_metadata(dict(begin_pc=1, end_pc=2, warmup_requests=1, timed_requests=1,
                                    regions=[dict(context=context, base=0x80000000, bytes=64) for context in range(4)]))

    def test_private_regions_preserve_actual_calloc_alignment_and_byte_bounds(self):
        metadata = dict(begin_pc=1, end_pc=2, warmup_requests=1, timed_requests=1,
                        regions=[dict(context=context, base=0x80000010+context*0x500, bytes=1024)
                                 for context in range(4)])
        extractor = Extractor(widths(), metadata)
        self.assertIsNone(extractor.target(0x80000008))
        self.assertEqual(extractor.target(0x80000010), 0)
        self.assertEqual(extractor.target(0x80000408), 0)
        self.assertIsNone(extractor.target(0x80000410))
        self.assertEqual(extractor.metadata['regions'][0]['base'], 0x80000010)


if __name__ == '__main__':
    unittest.main()
