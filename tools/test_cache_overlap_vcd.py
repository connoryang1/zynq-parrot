#!/usr/bin/env python3
"""Exercise overlap evidence boundaries with small, clocked synthetic VCDs."""

import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

import cache_overlap_vcd as analyzer


def trace(samples, missing=None, duplicate=None, edge_updates=None, optional=False):
    signals = dict(analyzer.REQUIRED)
    if optional:
        for group in analyzer.OPTIONAL_GROUPS.values():
            signals.update(group)
    signals.pop(missing, None)
    codes = {label: 'v' + str(i) for i, label in enumerate(signals)}
    out = ['$timescale 1 ps $end', '$scope module top $end']
    for label, name in signals.items():
        out.append('$var wire 64 %s %s $end' % (codes[label], name))
    if duplicate:
        out.append('$var wire 64 duplicate second.' + signals[duplicate] + ' $end')
    out.extend(['$upscope $end', '$enddefinitions $end', '#0', '$dumpvars'])
    for code in codes.values():
        out.append('b0 ' + code)
    out.append('$end')
    for i, sample in enumerate(samples):
        out.extend(['#' + str(i * 10 + 1), 'b0 ' + codes.get('clock', 'undeclared_clock')])
        for label, value in sample.items():
            if label in codes:
                out.append('b%s %s' % ('x' if value is None else format(value, 'b'), codes[label]))
        out.append('#' + str(i * 10 + 5))
        # Place data changes BEFORE clock in this timestamp to catch parsers
        # that mistakenly sample deltas according to VCD textual order.
        if edge_updates and i in edge_updates:
            for label, value in edge_updates[i].items():
                out.append('b%s %s' % (format(value, 'b'), codes[label]))
        out.append('b1 ' + codes.get('clock', 'undeclared_clock'))
    return '\n'.join(out) + '\n'


def case(work_cycle=2, critical=4, complete=5, address=0x90000000, thread=1, retire=True):
    samples = []
    for i in range(7):
        samples.append(dict(request_v=int(i == 1), request_yumi=int(i == 1),
                            address=address, msg_type=0, blocking_sent=int(i == 1),
                            critical_recv=int(i == critical), complete_recv=int(i == complete),
                            dispatch_v=int(i == work_cycle), dispatch_pc=0x80001000,
                            dispatch_thread=thread, commit_v=int(retire and i == work_cycle),
                            commit_pc=0x80001000, commit_thread=thread))
    return samples


class OverlapTests(unittest.TestCase):
    def analyze(self, samples=None, **kwargs):
        return analyzer.analyze(io.StringIO(trace(samples or case(), **kwargs)), 0x90000000, 0x80001000)

    def test_retirement_requires_both_clocked_refill_boundaries(self):
        result = self.analyze()
        self.assertTrue(result['retirement_overlap'])
        self.assertEqual(result['requests'][0]['accept']['timestamp'], 15)
        self.assertEqual(result['requests'][0]['critical']['cycle'], 4)
        self.assertEqual(result['verdict'], 'architectural_retirement_overlap')

    def test_work_after_critical_is_not_overlap(self):
        self.assertFalse(self.analyze(case(work_cycle=5))['retirement_overlap'])

    def test_after_critical_before_complete_proves_only_full_refill_overlap(self):
        result = self.analyze(case(work_cycle=3, critical=2, complete=5))
        self.assertFalse(result['retirement_overlap'])
        self.assertTrue(result['full_refill_retirement_overlap'])
        self.assertTrue(result['requests'][0]['full_refill_retirement_overlap'])
        self.assertEqual(result['verdict'], 'full_refill_retirement_overlap_only')

    def test_full_refill_overlap_excludes_both_boundary_cycles(self):
        for cycle in (1, 5):
            result = self.analyze(case(work_cycle=cycle))
            self.assertFalse(result['full_refill_retirement_overlap'])
            self.assertFalse(result['requests'][0]['full_refill_retirement_overlap'])

    def test_same_cycle_boundaries_do_not_count(self):
        for cycle in (1, 4, 5):
            with self.subTest(cycle=cycle):
                self.assertFalse(self.analyze(case(work_cycle=cycle))['retirement_overlap'])

    def test_wrong_address_or_owner_cannot_pass(self):
        self.assertEqual(self.analyze(case(address=0x90000040))['requests'], [])
        self.assertFalse(self.analyze(case(thread=0))['retirement_overlap'])
        sample = case()
        sample[2]['commit_thread'] = 0
        self.assertEqual(self.analyze(sample)['verdict'], 'dispatch_only')

    def test_same_line_address_matches(self):
        self.assertTrue(self.analyze(case(address=0x90000038))['retirement_overlap'])

    def test_contiguous_line_range(self):
        for address, expected in ((0x90000040, True), (0x90000080, False), (0x8fffffc0, False)):
            result = analyzer.analyze(io.StringIO(trace(case(address=address))),
                                      0x90000000, 0x80001000, span_lines=2)
            self.assertEqual(result['retirement_overlap'], expected)
            self.assertEqual(result['address_range'], [0x90000000, 0x90000080])
        with self.assertRaisesRegex(analyzer.EvidenceError, 'span-lines'):
            analyzer.analyze(io.StringIO(''), 0x90000000, 0x80001000, span_lines=0)

    def test_repeated_timestamp_does_not_create_delta_sampling(self):
        content = trace(case(), edge_updates={2: {'commit_v': 0}})
        content = content.replace('#25\nb0 v12', '#25\nb0 v12\n#25')
        result = analyzer.analyze(io.StringIO(content), 0x90000000, 0x80001000)
        self.assertTrue(result['retirement_overlap'])

    def test_uncached_or_unaccepted_request_is_not_cold_miss(self):
        for field, value in (('request_yumi', 0), ('blocking_sent', 0), ('msg_type', 3)):
            sample = case()
            sample[1][field] = value
            self.assertEqual(self.analyze(sample)['requests'], [])

    def test_missing_and_ambiguous_signals_fail_closed(self):
        with self.assertRaisesRegex(analyzer.EvidenceError, 'missing required'):
            self.analyze(missing='commit_thread')
        with self.assertRaisesRegex(analyzer.EvidenceError, 'ambiguous'):
            self.analyze(duplicate='clock')

    def test_unknown_refill_or_owner_cannot_prove_overlap(self):
        for field, cycle in (('critical_recv', 3), ('complete_recv', 3), ('commit_thread', 2)):
            sample = case()
            sample[cycle][field] = None
            result = self.analyze(sample)
            self.assertFalse(result['retirement_overlap'])
            self.assertFalse(result['full_refill_retirement_overlap'])

    def test_incomplete_trace_and_reset_fail_closed(self):
        self.assertFalse(self.analyze(case()[:4])['retirement_overlap'])
        sample = case()
        sample[3]['reset'] = 1
        self.assertFalse(self.analyze(sample)['retirement_overlap'])

    def test_preedge_values_ignore_rising_timestamp_delta_order(self):
        result = self.analyze(edge_updates={2: {'commit_v': 0, 'dispatch_v': 0, 'critical_recv': 1}})
        self.assertTrue(result['retirement_overlap'])
        sample = case(retire=False)
        result = self.analyze(sample, edge_updates={2: {'commit_v': 1}})
        self.assertFalse(result['retirement_overlap'])

    def test_divider_acceptance_is_distinct_from_retirement(self):
        sample = case(retire=False)
        sample[2].update(long_v=1, long_ready=1, long_reset=0,
                         long_pc=0x80001000, long_thread=1)
        sample[3]['long_v'] = 0
        result = self.analyze(sample, optional=True)
        self.assertTrue(result['integer_divider_overlap'])
        self.assertFalse(result['retirement_overlap'])
        self.assertEqual(result['verdict'], 'integer_divider_acceptance_only')

    def test_unknown_clock_cannot_skip_a_refill_boundary(self):
        content = trace(case()).replace('#31\nb0 v0', '#31\nbx v0')
        with self.assertRaisesRegex(analyzer.EvidenceError, 'unknown BE clock'):
            analyzer.analyze(io.StringIO(content), 0x90000000, 0x80001000)

    def test_conflicting_blocking_request_is_not_misattributed(self):
        sample = case()
        sample[3].update(request_v=1, request_yumi=1, blocking_sent=1, address=0x90000080)
        self.assertFalse(self.analyze(sample)['retirement_overlap'])

    def test_cli_full_refill_gate_is_independent_of_critical_gate(self):
        command = [sys.executable, str(Path(analyzer.__file__)), '--address', '0x90000000',
                   '--target-pc', '0x80001000']
        content = trace(case(work_cycle=3, critical=2, complete=5))
        for flags, expected in ((['--require-full-refill-overlap'], 0),
                                (['--require-overlap'], 1),
                                (['--require-overlap', '--require-full-refill-overlap'], 1)):
            result = subprocess.run(command + flags, input=content, text=True, capture_output=True)
            self.assertEqual(result.returncode, expected, result.stderr)
        result = subprocess.run(command + ['--require-full-refill-overlap'],
                                input=trace(case(work_cycle=5)), text=True, capture_output=True)
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_cli_require_overlap_and_invalid_trace_exit_status(self):
        command = [sys.executable, str(Path(analyzer.__file__)), '--address', '0x90000000',
                   '--target-pc', '0x80001000', '--require-overlap']
        for content, expected in ((trace(case()), 0), (trace(case(retire=False)), 1),
                                   (trace(case(), missing='clock'), 2)):
            result = subprocess.run(command, input=content, text=True, capture_output=True)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertIn('verdict', json.loads(result.stdout))


if __name__ == '__main__':
    unittest.main()
