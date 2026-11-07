#!/usr/bin/env python3
"""Test exact-identity comparison of sustained pipe-hint policies."""

import unittest
from pathlib import Path
from unittest import mock

from compare_scheduler_pipe_hint_policies import compare


def result(policy, identity, effects):
    return {
        "config": {"loops": 10, "repeats": 2, "warmup": 32,
                   "configured_entries": 16, "policy": policy},
        "identity": {"elf_sha256": identity},
        "pairs": [
            {"saved_cycles_per_roundtrip": cycles,
             "saved_percent": percent}
            for cycles, percent in effects
        ],
    }


class PipeHintPolicyComparatorTests(unittest.TestCase):
    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_reports_continuous_minus_seed(self, analyze):
        analyze.side_effect = [
            result("seed", "same", [(10.0, 1.0), (20.0, 2.0)]),
            result("seed", "same", [(20.0, 2.0), (30.0, 3.0)]),
            result("continuous", "same", [(40.0, 4.0), (50.0, 5.0)]),
            result("continuous", "same", [(50.0, 5.0), (60.0, 6.0)]),
        ]
        output = compare([Path("s1"), Path("s2")],
                         [Path("c1"), Path("c2")], 100)
        self.assertEqual(
            output["continuous_minus_seed"]["saved_cycles_per_roundtrip"],
            30.0,
        )

    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_rejects_nonmatching_elf(self, analyze):
        analyze.side_effect = [
            result("seed", "first", [(10.0, 1.0)]),
            result("seed", "first", [(10.0, 1.0)]),
            result("continuous", "second", [(10.0, 1.0)]),
            result("continuous", "second", [(10.0, 1.0)]),
        ]
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            compare([Path("s1"), Path("s2")],
                    [Path("c1"), Path("c2")], 10)


if __name__ == "__main__":
    unittest.main()
