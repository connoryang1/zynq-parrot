#!/usr/bin/env python3
"""Check retirement-window boundaries and cycle accounting."""

import io
import unittest

import retirement_window_vcd as analyzer


def trace(commits):
    lines = [
        '$timescale 1 ps $end', '$scope module top $end',
        '$var wire 1 c be.clk_i $end',
        '$var wire 1 v be.calculator.commit_pkt_cast_o.instret $end',
        '$var wire 64 p be.calculator.commit_pkt_cast_o.pc $end',
        '$var wire 8 t be.retire_thread_id_lo $end',
        '$upscope $end', '$enddefinitions $end',
        '#0', '0c', '0v', 'b0 p', 'b0 t',
    ]
    for cycle, item in enumerate(commits):
        valid, pc, thread = item if item is not None else (0, 0, 0)
        lines.extend([
            '#%d' % (cycle * 10 + 1), str(valid) + 'v',
            'b%s p' % format(pc, 'b'), 'b%s t' % format(thread, 'b'),
            '#%d' % (cycle * 10 + 5), '1c',
            '#%d' % (cycle * 10 + 8), '0c',
        ])
    return '\n'.join(lines) + '\n'


class RetirementWindowTests(unittest.TestCase):
    def test_final_window_excludes_boundaries(self):
        commits = [
            (1, 0x10, 0), (1, 0x20, 0), None, (1, 0x30, 0),
            (1, 0x10, 0), (1, 0x21, 1), None, (1, 0x22, 0), (1, 0x30, 0),
        ]
        report = analyzer.analyze(io.StringIO(trace(commits)), 0x10, 0x30,
                                  expected_windows=2)
        measured = report['measured']
        self.assertEqual(measured['core_cycles'], 4)
        self.assertEqual(measured['retired'], 2)
        self.assertEqual(measured['no_retirement_cycles'], 2)
        self.assertEqual(measured['by_thread'], {'0': 1, '1': 1})

    def test_rejects_unpaired_end(self):
        with self.assertRaisesRegex(analyzer.EvidenceError, 'without a begin'):
            analyzer.analyze(io.StringIO(trace([(1, 0x30, 0)])), 0x10, 0x30)


if __name__ == '__main__':
    unittest.main()
