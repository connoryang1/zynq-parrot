#!/usr/bin/env python3
"""Check that peer dispatch cannot be mistaken for concurrent memory admission."""

import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

import request_overlap_vcd as analyzer
from test_cache_overlap_vcd import case, trace


def pair(second_accept=6):
    samples = case(work_cycle=3, critical=2, complete=5)
    samples.extend(dict(samples[-1]) for _ in range(5))
    for index, sample in enumerate(samples):
        if index >= 6:
            sample.update(address=0x90000040, request_v=int(index == second_accept),
                          request_yumi=int(index == second_accept),
                          blocking_sent=int(index == second_accept),
                          critical_recv=int(index == 8), complete_recv=int(index == 10))
    return samples


class RequestOverlapTests(unittest.TestCase):
    def analyze(self, samples=None, **kwargs):
        return analyzer.analyze(io.StringIO(trace(pair() if samples is None else samples)),
                                0x90000000, 0x80001000, span_lines=2, **kwargs)

    def test_dispatch_during_fill_does_not_prove_admission_overlap(self):
        result = self.analyze(expected_requests=2)
        self.assertEqual(result['verdict'], 'serialized_request_admission')
        self.assertTrue(result['peer_dispatch_before_complete'])
        self.assertFalse(result['peer_dispatch_before_critical'])
        self.assertFalse(result['request_admission_before_previous_complete'])
        self.assertFalse(result['request_admission_before_previous_critical'])
        self.assertEqual(result['requests'][0]['next_request'], dict(
            address=0x90000040, accept_cycle=6, cycles_after_critical=4,
            cycles_after_complete=1))

    def test_peer_dispatch_before_critical_remains_dispatch_only(self):
        samples = pair()
        samples[2]['critical_recv'] = 0
        samples[4]['critical_recv'] = 1
        result = self.analyze(samples)
        self.assertTrue(result['peer_dispatch_before_critical'])
        self.assertFalse(result['request_admission_before_previous_critical'])

    def test_incomplete_conflicting_and_unknown_refills_fail_closed(self):
        with self.assertRaisesRegex(analyzer.EvidenceError, 'ended without'):
            self.analyze(pair()[:9])
        samples = pair()
        samples[4].update(address=0x90000040, request_v=1, request_yumi=1, blocking_sent=1)
        with self.assertRaisesRegex(analyzer.EvidenceError, 'second blocking request'):
            self.analyze(samples)
        samples = pair()
        samples[4]['complete_recv'] = None
        with self.assertRaisesRegex(analyzer.EvidenceError, 'unknown complete_recv'):
            self.analyze(samples)

    def test_unrelated_conflicting_request_cannot_borrow_refill(self):
        samples = pair()
        samples[4].update(address=0x91000000, request_v=1, request_yumi=1, blocking_sent=1)
        with self.assertRaisesRegex(analyzer.EvidenceError, 'second blocking request'):
            self.analyze(samples)

    def test_selected_request_cannot_borrow_an_earlier_unrelated_refill(self):
        samples = pair()
        samples[1]['address'] = 0x91000000
        samples[3].update(address=0x90000000, request_v=1, request_yumi=1, blocking_sent=1)
        with self.assertRaisesRegex(analyzer.EvidenceError, 'second blocking request'):
            self.analyze(samples)

    def test_exact_count_rejects_missing_and_extra_requests(self):
        for expected in (1, 3):
            with self.assertRaisesRegex(analyzer.EvidenceError, 'expected .* observed 2'):
                self.analyze(expected_requests=expected)
        with self.assertRaisesRegex(analyzer.EvidenceError, 'must be positive'):
            self.analyze(expected_requests=0)

    def test_one_request_cannot_demonstrate_serialized_pairs(self):
        result = self.analyze(case())
        self.assertEqual(result['verdict'], 'insufficient_request_pairs')
        self.assertIsNone(result['requests'][0]['next_request'])

    def test_wrong_thread_does_not_count_as_peer_dispatch(self):
        samples = pair()
        samples[3]['dispatch_thread'] = 0
        self.assertFalse(self.analyze(samples)['peer_dispatch_before_complete'])

    def test_no_selected_requests_fails_closed(self):
        samples = case(address=0x91000000)
        with self.assertRaisesRegex(analyzer.EvidenceError, 'no accepted'):
            self.analyze(samples)

    def test_cli_serialization_gate_and_invalid_trace(self):
        command = [sys.executable, str(Path(analyzer.__file__)), '--address', '0x90000000',
                   '--span-lines', '2', '--target-pc', '0x80001000', '--require-serialized']
        for content, expected in ((trace(pair()), 0), (trace(case()), 1),
                                  (trace(pair()[:9]), 2), (trace(pair(), missing='clock'), 2)):
            result = subprocess.run(command, input=content, text=True, capture_output=True)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertIn('verdict', json.loads(result.stdout))


if __name__ == '__main__':
    unittest.main()
