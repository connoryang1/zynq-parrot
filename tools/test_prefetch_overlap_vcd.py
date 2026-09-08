#!/usr/bin/env python3
"""Check transaction ownership and separate UCE/AXI overlap evidence."""

import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

import prefetch_overlap_vcd as analyzer


def idle():
    values = {key: 0 for key in analyzer.signal_names(axi_prefix='axi_mem')}
    values.update(fwd_ready=1, fwd_new=1, fwd_last=1, rev_new=1, rev_last=1,
                  ar_ready=1, r_ready=1)
    return values


def allocate(slot, address):
    return dict(request_v=1, request_yumi=1, request_type=9, request_address=address,
                allocate=1, allocate_slot=slot)


def issue(slot, address):
    return dict(fwd_v=1, fwd_type=0, fwd_prefetch=1, fwd_address=address,
                fwd_size=3, fwd_slot=slot, issue=1, issue_slot=slot)


def response(slot, address):
    return dict(rev_v=1, rev_yumi=1, rev_type=0, rev_prefetch=1, rev_address=address,
                rev_size=3, rev_slot=slot, response=1, rev_new=1, rev_last=1)


def case(axi=False, second_issue=3):
    samples = [idle() for _ in range(23)]
    samples[0].update(allocate(0, 0x80008000))
    samples[1].update(issue(0, 0x80008000))
    samples[2].update(allocate(1, 0x80008040))
    samples[second_issue].update(issue(1, 0x80008040))
    samples[4].update(request_v=1, request_yumi=1, request_type=9,
                      request_address=0x80008007, duplicate=1)
    samples[6].update(response(0, 0x80008000))
    samples[8].update(response(1, 0x80008040))
    # A normal full-line read must retain a separate response identity.
    samples[9].update(request_v=1, request_yumi=1, request_type=0, request_address=0x80008000)
    samples[10].update(fwd_v=1, fwd_size=6, fwd_address=0x80008000, fwd_slot=3)
    for index in range(8):
        samples[12 + index].update(rev_v=1, rev_yumi=1, rev_size=6,
                                   rev_address=0x80008000, rev_slot=3,
                                   rev_new=int(index == 0), rev_last=int(index == 7))
    if axi:
        samples[0].update(ar_v=1, ar_address=0x80008000, ar_len=7)
        samples[2].update(ar_v=1, ar_address=0x80008040, ar_len=7)
        for index in range(16):
            samples[5 + index].update(r_v=1, r_last=int(index % 8 == 7))
    return samples


def trace(samples, axi=False, missing=None, duplicate=None, edge_updates=None):
    names = analyzer.signal_names(axi_prefix='axi_mem' if axi else None)
    names.pop(missing, None)
    codes = {key: 's' + str(index) for index, key in enumerate(names)}
    lines = ['$timescale 1 ps $end', '$scope module top $end']
    for key, name in names.items():
        lines.append('$var wire 64 %s %s $end' % (codes[key], name))
    if duplicate:
        lines.append('$var wire 64 duplicate other.' + names[duplicate] + ' $end')
    lines.extend(['$upscope $end', '$enddefinitions $end', '#0'])
    lines.extend('b0 ' + code for code in codes.values())
    for index, sample in enumerate(samples):
        lines.append('#' + str(index * 20 + 1))
        for key, value in sample.items():
            if key in codes and key not in ('clock', 'axi_clock'):
                lines.append('b%s %s' % ('x' if value is None else format(value, 'b'), codes[key]))
        lines.append('#' + str(index * 20 + 5))
        if edge_updates and index in edge_updates:
            for key, value in edge_updates[index].items():
                lines.append('b%s %s' % (format(value, 'b'), codes[key]))
        lines.extend(['b1 ' + codes.get('clock', 'missing'), '#' + str(index * 20 + 10),
                      'b0 ' + codes.get('clock', 'missing')])
        if axi:
            lines.extend(['#' + str(index * 20 + 15), 'b1 ' + codes['axi_clock'],
                          '#' + str(index * 20 + 20), 'b0 ' + codes['axi_clock']])
    return '\n'.join(lines) + '\n'


class PrefetchTests(unittest.TestCase):
    def analyze(self, samples=None, axi=False, **kwargs):
        return analyzer.analyze(io.StringIO(trace(case(axi) if samples is None else samples,
                                                  axi=axi, **kwargs)),
                                axi_prefix='axi_mem' if axi else None)

    def test_slots_duplicate_hint_and_normal_fill_are_distinct(self):
        report = self.analyze()
        self.assertEqual(report['prefetch_summary']['max_outstanding'], 2)
        self.assertTrue(report['prefetch_summary']['issue_before_prior_first_response'])
        self.assertEqual(report['prefetch_summary']['before_first_response_pairs'], [[0, 1]])
        self.assertEqual(len(report['accepted_hints']), 3)
        self.assertEqual(len(report['prefetches']), 2)
        self.assertEqual(report['normal_reads'][0]['beats'], 8)
        self.assertIsNone(report['axi_summary'])
        self.assertIn('not observable', report['backing_service_overlap'])

    def test_different_clock_phases_sample_their_own_edges(self):
        report = self.analyze(axi=True)
        self.assertEqual(report['prefetches'][0]['issue'], dict(cycle=1, timestamp=25))
        self.assertEqual(report['axi_reads'][0]['issue'], dict(cycle=0, timestamp=15))
        self.assertEqual(report['axi_reads'][0]['complete'], dict(cycle=12, timestamp=255))
        self.assertEqual(report['axi_summary']['max_outstanding'], 2)
        self.assertEqual(report['cycles'], dict(clock=23, axi_clock=23))
        self.assertEqual(report['signals']['axi_clock'], 'top.axi_mem.clk_i')

    def test_uce_overlap_does_not_require_axi_overlap(self):
        samples = case(True)
        samples[2]['ar_v'] = 0
        samples[12].update(ar_v=1, ar_address=0x80008040, ar_len=7)
        report = self.analyze(samples, axi=True)
        self.assertTrue(report['prefetch_summary']['issue_before_prior_first_response'])
        self.assertFalse(report['axi_summary']['issue_before_prior_completion'])
        self.assertEqual(report['axi_summary']['max_outstanding'], 1)

    def test_response_service_tail_is_separate_from_first_response_latency(self):
        samples = case(True)
        samples[2]['ar_v'] = 0
        samples[8].update(ar_v=1, ar_address=0x80008040, ar_len=7)
        report = self.analyze(samples, axi=True)
        self.assertFalse(report['axi_summary']['issue_before_prior_first_response'])
        self.assertTrue(report['axi_summary']['issue_before_prior_completion'])

    def test_same_edge_completion_and_issue_is_not_overlap(self):
        report = self.analyze(case(second_issue=6))
        self.assertEqual(report['prefetch_summary']['max_outstanding'], 1)
        self.assertFalse(report['prefetch_summary']['issue_before_prior_completion'])

    def test_reuse_only_after_previous_completion(self):
        samples = case()
        samples[7].update(allocate(0, 0x80008080))
        samples[9].update(issue(0, 0x80008080))
        samples[11].update(response(0, 0x80008080))
        self.assertEqual(len(self.analyze(samples)['prefetches']), 3)
        samples = case()
        samples[6].update(allocate(0, 0x80008080))
        with self.assertRaisesRegex(analyzer.EvidenceError, 'slot allocation'):
            self.analyze(samples)

    def test_duplicate_line_without_merge_rejected(self):
        samples = case()
        samples[2].update(allocate(1, 0x80008008))
        with self.assertRaisesRegex(analyzer.EvidenceError, 'unique line'):
            self.analyze(samples)

    def test_same_line_demand_cannot_overtake_prefetch(self):
        samples = case()
        samples[5].update(fwd_v=1, fwd_size=6, fwd_address=0x80008000)
        with self.assertRaisesRegex(analyzer.EvidenceError, 'same-line prefetch completion'):
            self.analyze(samples)

    def test_unmatched_and_wrong_identity_responses_rejected(self):
        for field, value, message in (('rev_slot', 2, 'unmatched'),
                                       ('rev_address', 0x80008008, 'address/size'),
                                       ('rev_size', 6, 'address/size'),
                                       ('rev_last', 0, 'boundary'),
                                       ('rev_prefetch', 0, 'unmatched normal')):
            samples = case()
            samples[6][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(analyzer.EvidenceError, message):
                self.analyze(samples)

    def test_unknown_controls_and_reset_pending_rejected(self):
        for field in ('request_v', 'issue', 'rev_yumi', 'reset'):
            samples = case()
            samples[5][field] = None
            with self.subTest(field=field), self.assertRaisesRegex(analyzer.EvidenceError, 'unknown ' + field):
                self.analyze(samples)
        samples = case()
        samples[5]['reset'] = 1
        with self.assertRaisesRegex(analyzer.EvidenceError, 'reset with incomplete'):
            self.analyze(samples)

    def test_axi_backpressure_does_not_count_unaccepted_addresses_or_beats(self):
        samples = case(True)
        samples[1].update(ar_v=1, ar_ready=0, ar_address=0x90000000)
        samples[4].update(r_v=1, r_ready=0, r_last=1)
        report = self.analyze(samples, axi=True)
        self.assertEqual(report['axi_summary']['transactions'], 2)
        self.assertEqual(report['axi_reads'][0]['beats'], 8)

    def test_axi_unmatched_id_error_and_burst_boundaries_fail_closed(self):
        for index, field, value, message in ((1, 'r_v', 1, 'RLAST/count'),
                                            (5, 'r_id', 1, 'ID mismatch'),
                                            (5, 'r_resp', 2, 'non-OKAY'),
                                            (5, 'r_last', 1, 'RLAST/count'),
                                            (12, 'r_last', 0, 'RLAST/count'),
                                            (2, 'ar_id', 1, 'multiple AXI IDs'),
                                            (3, 'ar_ready', None, 'unknown ar_ready')):
            samples = case(True)
            samples[index][field] = value
            with self.subTest(field=field, index=index), self.assertRaisesRegex(analyzer.EvidenceError, message):
                self.analyze(samples, axi=True)
        samples = case(True)
        samples[21]['r_v'] = 1
        with self.assertRaisesRegex(analyzer.EvidenceError, 'unmatched AXI'):
            self.analyze(samples, axi=True)

    def test_incomplete_and_missing_signals_rejected(self):
        for end in (3, 7, 18):
            with self.subTest(end=end), self.assertRaisesRegex(analyzer.EvidenceError, 'incomplete'):
                self.analyze(case()[:end])
        with self.assertRaisesRegex(analyzer.EvidenceError, 'missing required signal'):
            self.analyze(missing='issue')
        with self.assertRaisesRegex(analyzer.EvidenceError, 'ambiguous signal'):
            self.analyze(duplicate='issue')

    def test_pre_edge_values_ignore_textual_delta_order(self):
        report = self.analyze(edge_updates={1: dict(issue=0, fwd_v=0),
                                           6: dict(response=0, rev_v=0)})
        self.assertEqual(report['prefetch_summary']['max_outstanding'], 2)

    def test_region_mapping_excludes_loader_and_nonmatching_traffic(self):
        samples = case(True)
        for sample in samples:
            sample.update(rev_v=0, rev_yumi=0, response=0)
        samples[10]['fwd_v'] = 0
        samples[14].update(response(0, 0x80008000))
        samples[22].update(response(1, 0x80008040))
        samples[0]['ar_v'] = samples[2]['ar_v'] = 0
        samples[1].update(ar_v=1, ar_address=0x8000, ar_len=7)
        samples[3].update(ar_v=1, ar_address=0x8040, ar_len=7)
        report = self.analyze(samples, axi=True)
        # Add completed pre-workload traffic with the same physical address.
        loader = dict(report['axi_reads'][0], id=99,
                      issue=dict(cycle=0, timestamp=1),
                      first_response=dict(cycle=0, timestamp=2),
                      complete=dict(cycle=0, timestamp=3))
        report['axi_reads'].insert(0, loader)
        result = analyzer.region_summary(report, 0x80008000, 128, 0x80000000)
        self.assertEqual(len(result['axi_region_reads']), 3)
        self.assertEqual(len(result['axi_correlated_reads']), 2)
        self.assertEqual(result['axi_correlated_reads'][0]['matching_prefetch_ids'], [0])
        self.assertTrue(result['axi_summary']['issue_before_prior_first_response'])
        result = analyzer.region_summary(report, 0x80008000, 64, 0x80000000)
        self.assertEqual(result['axi_summary']['transactions'], 1)
        self.assertFalse(result['axi_summary']['issue_before_prior_completion'])
        result = analyzer.region_summary(report, 0x80008000, 128)
        self.assertEqual(result['axi_summary']['transactions'], 0)

    def test_region_rejects_missing_workload_and_incomplete_selection(self):
        with self.assertRaisesRegex(analyzer.EvidenceError, 'no prefetch transactions'):
            analyzer.region_summary(self.analyze(), 0x90000000, 64)
        with self.assertRaisesRegex(analyzer.EvidenceError, 'invalid address region'):
            analyzer.region_summary(self.analyze(), 0x80008000, 0)

    def test_cli_separate_overlap_gates_and_invalid_evidence(self):
        command = [sys.executable, str(Path(analyzer.__file__))]
        for content, flags, expected in ((trace(case()), ['--require-uce-overlap'], 0),
                                          (trace(case()), ['--require-axi-overlap'], 1),
                                          (trace(case(True), axi=True), ['--axi-prefix', 'axi_mem', '--require-axi-overlap'], 0),
                                          (trace(case()[:4]), [], 2)):
            result = subprocess.run(command + flags, input=content, text=True, capture_output=True)
            self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
            self.assertIn('verdict', json.loads(result.stdout))


if __name__ == '__main__':
    unittest.main()
