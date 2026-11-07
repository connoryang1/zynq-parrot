#!/usr/bin/env python3
"""Test exact-identity comparison of retained pipe-prefix capacities."""

import unittest
from pathlib import Path
from unittest import mock

from compare_scheduler_pipe_hint_capacities import compare


def result(count, nbf, elf, effects, bitstream="same-bitstream"):
    return {
        "config": {"loops": 10, "repeats": 2, "warmup": 256,
                   "configured_entries": count, "policy": "preseed"},
        "identity": {"nbf_sha256": nbf, "elf_sha256": elf,
                     "bitstream_sha256": bitstream},
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

    @mock.patch("compare_scheduler_pipe_hint_capacities.analyze")
    def test_allows_one_stable_bitstream_per_capacity_when_explicit(self, analyze):
        analyze.side_effect = [
            result(16, "small-nbf", "same-elf", [(10.0, 1.0)], "flat16"),
            result(16, "small-nbf", "same-elf", [(20.0, 2.0)], "flat16"),
            result(32, "large-nbf", "same-elf", [(40.0, 4.0)], "flat32"),
            result(32, "large-nbf", "same-elf", [(50.0, 5.0)], "flat32"),
        ]
        output = compare(
            [Path("s1"), Path("s2")], [Path("l1"), Path("l2")], 100,
            allow_bitstream_difference=True,
        )
        self.assertEqual(output["small"]["bitstream_sha256"], "flat16")
        self.assertEqual(output["large"]["bitstream_sha256"], "flat32")
        self.assertEqual(
            output["identity_policy"]["allowed_differences"],
            ["bitstream_sha256", "nbf_sha256"],
        )

    @mock.patch("compare_scheduler_pipe_hint_capacities.analyze")
    def test_rejects_bitstream_change_without_explicit_policy(self, analyze):
        analyze.side_effect = [
            result(16, "small", "same", [(10.0, 1.0)], "flat16"),
            result(16, "small", "same", [(10.0, 1.0)], "flat16"),
            result(32, "large", "same", [(10.0, 1.0)], "flat32"),
            result(32, "large", "same", [(10.0, 1.0)], "flat32"),
        ]
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            compare([Path("s1"), Path("s2")],
                    [Path("l1"), Path("l2")], 10)

    @mock.patch("compare_scheduler_pipe_hint_capacities.analyze")
    def test_rejects_bitstream_change_within_capacity(self, analyze):
        analyze.side_effect = [
            result(16, "small", "same", [(10.0, 1.0)], "flat16"),
            result(16, "small", "same", [(10.0, 1.0)], "flat16-different"),
            result(32, "large", "same", [(10.0, 1.0)], "flat32"),
            result(32, "large", "same", [(10.0, 1.0)], "flat32"),
        ]
        with self.assertRaisesRegex(ValueError, "bitstream_sha256 mismatch"):
            compare(
                [Path("s1"), Path("s2")],
                [Path("l1"), Path("l2")], 10,
                allow_bitstream_difference=True,
            )


if __name__ == "__main__":
    unittest.main()
