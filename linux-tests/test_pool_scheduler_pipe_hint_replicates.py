#!/usr/bin/env python3
"""Test hierarchical pooling of sustained pipe-hint board replications."""

import unittest
from pathlib import Path
from unittest import mock

from pool_scheduler_pipe_hint_replicates import pool


def result(identity, effects, config=None):
    return {
        "config": config or {"loops": 10, "repeats": 2, "warmup": 32,
                             "configured_entries": 16},
        "identity": {"elf_sha256": identity},
        "pairs": [
            {"saved_cycles_per_roundtrip": cycles,
             "saved_percent": percent}
            for cycles, percent in effects
        ],
    }


class PipeHintPoolTests(unittest.TestCase):
    @mock.patch("pool_scheduler_pipe_hint_replicates.analyze")
    def test_hierarchical_pool_reports_boot_and_pooled_effects(self, analyze):
        analyze.side_effect = [
            result("same", [(10.0, 1.0), (20.0, 2.0)]),
            result("same", [(30.0, 3.0), (40.0, 4.0)]),
            result("same", [(50.0, 5.0), (60.0, 6.0)]),
        ]
        pooled = pool([Path("a"), Path("b"), Path("c")], 100)
        self.assertEqual(
            pooled["replicate_saved_cycles_per_roundtrip"],
            [15.0, 35.0, 55.0],
        )
        self.assertEqual(
            pooled["pooled"]["paired_median_saved_cycles_per_roundtrip"],
            35.0,
        )
        self.assertEqual(analyze.call_count, 3)

    @mock.patch("pool_scheduler_pipe_hint_replicates.analyze")
    def test_rejects_identity_mismatch(self, analyze):
        analyze.side_effect = [
            result("first", [(10.0, 1.0)]),
            result("second", [(10.0, 1.0)]),
        ]
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            pool([Path("a"), Path("b")], 10)

    def test_requires_independent_replications(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            pool([Path("a")], 10)


if __name__ == "__main__":
    unittest.main()
