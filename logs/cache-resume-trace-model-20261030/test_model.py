#!/usr/bin/env python3
"""Unit checks for the cache-resume trace timing model."""

import importlib.util
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cache_resume_model", HERE / "model.py")
MODEL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODEL
SPEC.loader.exec_module(MODEL)


class ModelTest(unittest.TestCase):
    def test_parser_reproduces_current_physical_sliced_counts(self):
        forward = MODEL.parse_trace(HERE / "raw/cache-miss-trace-to-peer.log.xz")
        reverse = MODEL.parse_trace(HERE / "raw/cache-miss-trace-from-peer.log.xz")
        self.assertEqual((forward.header["i_count"], forward.header["d_count"]), (102, 3))
        self.assertEqual((reverse.header["i_count"], reverse.header["d_count"]), (55, 5))
        self.assertEqual(forward.outcome, "TRACE_PASS")
        self.assertEqual(reverse.outcome, "TRACE_PASS")

    def test_scheduler_serializes_responses_and_installs(self):
        timing = MODEL.Timing(slots=2, first_beat_latency=10, beats_per_line=8, install_cycles=19)
        events = MODEL.schedule_replay([0x1000, 0x2000, 0x3000], 0, timing)
        self.assertEqual(events[0x1000]["issue"], 0)
        self.assertEqual(events[0x2000]["issue"], 1)
        self.assertEqual(events[0x1000]["first_beat"], 10)
        self.assertEqual(events[0x2000]["first_beat"], 18)
        self.assertEqual(events[0x3000]["issue"], 18)
        self.assertEqual(events[0x1000]["ready"], 37)
        self.assertEqual(events[0x2000]["ready"], 56)

    def test_default_model_reproduces_privileged_count_and_rows(self):
        result = MODEL.build_result(HERE / "raw")
        self.assertEqual(result["measured_inputs"]["instruction_demand_records"], 157)
        self.assertEqual(result["measured_inputs"]["privileged_instruction_records"], 153)
        names = {row["mechanism"] for row in result["primary_table"]}
        self.assertEqual(
            names,
            {
                "dispatch_replay_oracle_order",
                "syscall_shared_prefix",
                "syscall_fixed_shared_prefix",
                "trained_retention_1",
                "trained_retention_2",
                "trained_retention_4",
                "hybrid_shared_plus_oracle_retention_4",
            },
        )
        fixed = next(
            row for row in result["primary_table"]
            if row["mechanism"] == "syscall_fixed_shared_prefix"
        )
        self.assertEqual(result["measured_inputs"]["fixed_shared_prefix_lines"], 63)
        self.assertEqual(result["fixed_shared_prefix"]["line_count"], 63)
        self.assertLessEqual(
            max(
                sum(1 for line in result["fixed_shared_prefix"]["lines"]
                    if line["cache_set"] == cache_set)
                for cache_set in range(MODEL.SETS)
            ),
            MODEL.WAYS,
        )
        self.assertGreater(fixed["ready_demand_records"], 0)
        self.assertGreater(fixed["ready_before_demand_unique"], 0)


if __name__ == "__main__":
    unittest.main()
