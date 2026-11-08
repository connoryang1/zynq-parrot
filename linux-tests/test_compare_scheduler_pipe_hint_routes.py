#!/usr/bin/env python3
"""Test exact-identity comparison of sustained pipe-prefix FPGA routes."""

import unittest
from pathlib import Path
from unittest import mock

from compare_scheduler_pipe_hint_routes import compare


def result(bitstream, effects, nbf="same-nbf", elf="same-elf"):
    return {
        "config": {"loops": 10, "repeats": 2, "warmup": 256,
                   "configured_entries": 32, "policy": "preseed"},
        "identity": {"nbf_sha256": nbf, "elf_sha256": elf,
                     "bitstream_sha256": bitstream},
        "pairs": [
            {"saved_cycles_per_roundtrip": cycles,
             "saved_percent": percent}
            for cycles, percent in effects
        ],
    }


class PipeHintRouteComparatorTests(unittest.TestCase):
    @mock.patch("compare_scheduler_pipe_hint_routes.analyze")
    def test_reports_candidate_minus_baseline(self, analyze):
        analyze.side_effect = [
            result("flat", [(10.0, 1.0), (20.0, 2.0)]),
            result("flat", [(20.0, 2.0), (30.0, 3.0)]),
            result("banked", [(40.0, 4.0), (50.0, 5.0)]),
            result("banked", [(50.0, 5.0), (60.0, 6.0)]),
        ]
        output = compare(
            [Path("b1"), Path("b2")], [Path("c1"), Path("c2")], 100
        )
        self.assertEqual(
            output["candidate_minus_baseline"]["saved_cycles_per_roundtrip"],
            30.0,
        )
        self.assertEqual(output["baseline"]["bitstream_sha256"], "flat")
        self.assertEqual(output["candidate"]["bitstream_sha256"], "banked")

    @mock.patch("compare_scheduler_pipe_hint_routes.analyze")
    def test_rejects_non_bitstream_identity_change(self, analyze):
        analyze.side_effect = [
            result("flat", [(10.0, 1.0)]),
            result("flat", [(10.0, 1.0)]),
            result("banked", [(10.0, 1.0)], nbf="changed"),
            result("banked", [(10.0, 1.0)], nbf="changed"),
        ]
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            compare([Path("b1"), Path("b2")],
                    [Path("c1"), Path("c2")], 10)

    @mock.patch("compare_scheduler_pipe_hint_routes.analyze")
    def test_rejects_bitstream_change_within_route(self, analyze):
        analyze.side_effect = [
            result("flat", [(10.0, 1.0)]),
            result("flat-other", [(10.0, 1.0)]),
            result("banked", [(10.0, 1.0)]),
            result("banked", [(10.0, 1.0)]),
        ]
        with self.assertRaisesRegex(ValueError, "bitstream mismatch"):
            compare([Path("b1"), Path("b2")],
                    [Path("c1"), Path("c2")], 10)

    @mock.patch("compare_scheduler_pipe_hint_routes.analyze")
    def test_rejects_same_bitstream(self, analyze):
        analyze.side_effect = [
            result("same", [(10.0, 1.0)]),
            result("same", [(10.0, 1.0)]),
            result("same", [(10.0, 1.0)]),
            result("same", [(10.0, 1.0)]),
        ]
        with self.assertRaisesRegex(ValueError, "same bitstream"):
            compare([Path("b1"), Path("b2")],
                    [Path("c1"), Path("c2")], 10)


if __name__ == "__main__":
    unittest.main()
