#!/usr/bin/env python3
"""Test exact-identity comparison of retained pipe-prefix tables."""

import unittest
from pathlib import Path
from unittest import mock

from compare_scheduler_pipe_hint_tables import compare


def result(nbf, elf, effects):
    return {
        "config": {"loops": 10, "repeats": 2, "warmup": 256,
                   "configured_entries": 16, "policy": "preseed"},
        "identity": {"nbf_sha256": nbf, "elf_sha256": elf},
        "pairs": [
            {"saved_cycles_per_roundtrip": cycles,
             "saved_percent": percent}
            for cycles, percent in effects
        ],
    }


class PipeHintTableComparatorTests(unittest.TestCase):
    @mock.patch("compare_scheduler_pipe_hint_tables.analyze")
    def test_reports_candidate_minus_baseline(self, analyze):
        analyze.side_effect = [
            result("base", "same", [(10.0, 1.0), (20.0, 2.0)]),
            result("base", "same", [(20.0, 2.0), (30.0, 3.0)]),
            result("candidate", "same", [(40.0, 4.0), (50.0, 5.0)]),
            result("candidate", "same", [(50.0, 5.0), (60.0, 6.0)]),
        ]
        output = compare([Path("b1"), Path("b2")],
                         [Path("c1"), Path("c2")], 100)
        self.assertEqual(
            output["candidate_minus_baseline"]["saved_cycles_per_roundtrip"],
            30.0,
        )

    @mock.patch("compare_scheduler_pipe_hint_tables.analyze")
    def test_rejects_configuration_change(self, analyze):
        changed = result("candidate", "same", [(10.0, 1.0)])
        changed["config"]["configured_entries"] = 8
        analyze.side_effect = [
            result("base", "same", [(10.0, 1.0)]),
            result("base", "same", [(10.0, 1.0)]),
            changed, changed,
        ]
        with self.assertRaisesRegex(ValueError, "configuration mismatch"):
            compare([Path("b1"), Path("b2")],
                    [Path("c1"), Path("c2")], 10)


if __name__ == "__main__":
    unittest.main()
