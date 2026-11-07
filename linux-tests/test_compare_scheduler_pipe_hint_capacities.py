#!/usr/bin/env python3
"""Test exact-identity comparison of retained pipe-prefix capacities."""

import unittest
from pathlib import Path
from unittest import mock

from compare_scheduler_pipe_hint_capacities import compare


def result(count, nbf, elf, effects):
    return {
        "config": {"loops": 10, "repeats": 2, "warmup": 256,
                   "configured_entries": count, "policy": "preseed"},
        "identity": {"nbf_sha256": nbf, "elf_sha256": elf},
        "pairs": [
            {"saved_cycles_per_roundtrip": cycles,
             "saved_percent": percent}
            for cycles, percent in effects
        ],
    }


class PipeHintCapacityComparatorTests(unittest.TestCase):
    @mock.patch("compare_scheduler_pipe_hint_capacities.analyze")
    def test_reports_large_minus_small(self, analyze):
        analyze.side_effect = [
            result(8, "small", "same", [(10.0, 1.0), (20.0, 2.0)]),
            result(8, "small", "same", [(20.0, 2.0), (30.0, 3.0)]),
            result(16, "large", "same", [(40.0, 4.0), (50.0, 5.0)]),
            result(16, "large", "same", [(50.0, 5.0), (60.0, 6.0)]),
        ]
        output = compare([Path("s1"), Path("s2")],
                         [Path("l1"), Path("l2")], 100)
        self.assertEqual(
            output["large_minus_small"]["saved_cycles_per_roundtrip"],
            30.0,
        )

    @mock.patch("compare_scheduler_pipe_hint_capacities.analyze")
    def test_rejects_other_identity_change(self, analyze):
        analyze.side_effect = [
            result(8, "small", "first", [(10.0, 1.0)]),
            result(8, "small", "first", [(10.0, 1.0)]),
            result(16, "large", "second", [(10.0, 1.0)]),
            result(16, "large", "second", [(10.0, 1.0)]),
        ]
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            compare([Path("s1"), Path("s2")],
                    [Path("l1"), Path("l2")], 10)


if __name__ == "__main__":
    unittest.main()
