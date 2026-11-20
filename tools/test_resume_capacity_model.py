#!/usr/bin/env python3
"""Check capacity controls, complete service drain and independent bus timing."""
import tempfile
import json
from pathlib import Path
import unittest

from resume_capacity_model import Access, Timing, main, parse_trace, simulate


A = 0x80000000
B = A + 64
C = A + 128


class ServiceModelTest(unittest.TestCase):
    def test_demand_populates_same_capacity_without_replay(self):
        accesses = [Access(0, "I", A), Access(100, "I", B), Access(200, "I", A)]
        row = simulate(accesses, 200, mode="demand-retained", i_lines=2, d_lines=0,
                       timing=Timing(first_response=40, install=2))
        self.assertEqual(row["stats"]["demand_reads"], 2)
        self.assertEqual(row["stats"]["side_hits"], 1)
        self.assertNotIn("replay_reads", row["stats"])
        self.assertEqual(row["drained_service_envelope_cycles"], 200)

    def test_prefix_capacity_is_not_overwritten_by_ordinary_misses(self):
        events = [Access(0, "I", B), Access(200, "I", A)]
        training = [Access(0, "I", A)]
        retained = simulate(events, 200, training, "retained-prefix", 1, 0)
        replay = simulate(events, 200, training, "preseed", 1, 0)
        self.assertEqual(retained["stats"]["side_hits"], 1)
        self.assertEqual(replay["stats"]["side_hits"], 1)
        self.assertEqual(retained["stats"]["demand_reads"], 1)
        self.assertEqual(replay["stats"]["demand_reads"], 1)

    def test_unused_replay_count_distinguishes_later_hits_from_waiters(self):
        training = [Access(0, "I", A), Access(1, "I", B)]
        row = simulate([Access(200, "I", A)], 200, training, "continuous", 2, 0)
        self.assertEqual(row["stats"]["replay_completed_without_waiter"], 2)
        self.assertEqual(row["stats"]["replay_fills_consumed"], 1)
        self.assertEqual(row["stats"]["replay_fills_not_consumed"], 1)

    def test_prior_demand_history_is_separate_from_first_prefix(self):
        training = [Access(0, "I", A), Access(1, "I", B), Access(2, "I", C)]
        # LRU history keeps B/C, while first-prefix replay would keep A/B.
        row = simulate([Access(0, "I", C)], 0, training,
                       mode="demand-retained", i_lines=2, d_lines=0)
        self.assertEqual(row["stats"]["side_hits"], 1)
        self.assertEqual(row["drained_service_envelope_cycles"], 0)

    def test_retained_prefix_matches_replay_tags_without_read_cost(self):
        training = [Access(0, "I", A), Access(1, "I", B), Access(2, "I", C)]
        row = simulate([Access(0, "I", A)], 0, training,
                       mode="retained-prefix", i_lines=2, d_lines=0)
        self.assertEqual(row["stats"]["side_hits"], 1)
        self.assertNotIn("replay_reads", row["stats"])

    def test_independent_i_d_capacity(self):
        training = [Access(0, "I", A), Access(1, "D", A)]
        events = [Access(0, "I", A), Access(0, "D", A)]
        row = simulate(events, 0, training, "demand-retained", 1, 0)
        self.assertEqual(row["by_side"]["I"]["side_hits"], 1)
        self.assertEqual(row["by_side"]["D"]["demand_reads"], 1)

    def test_replay_join_suppresses_duplicate_demand_read(self):
        row = simulate([Access(5, "I", A)], 5, [Access(0, "I", A)], "continuous",
                       i_lines=1, d_lines=0,
                       timing=Timing(first_response=40, install=2))
        self.assertEqual(row["stats"]["joined_replay"], 1)
        self.assertNotIn("demand_reads", row["stats"])
        self.assertEqual(row["last_demand_completion_cycle"], 50)

    def test_issued_replay_burst_interferes_with_demand(self):
        events = [Access(5, "D", B)]
        timing = Timing(first_response=40, install=2)
        base = simulate(events, 5, timing=timing)
        replay = simulate(events, 5, [Access(0, "I", A)], "continuous", 1, 0, timing)
        self.assertEqual(base["last_demand_completion_cycle"], 55)
        self.assertEqual(replay["last_demand_completion_cycle"], 58)
        self.assertGreater(replay["drained_service_envelope_cycles"],
                           base["drained_service_envelope_cycles"])

    def test_demand_priority_at_equal_response_time(self):
        timing = Timing(first_response=40, install=2)
        row = simulate([Access(0, "D", B)], 0, [Access(0, "I", A)],
                       "continuous", 1, 0, timing)
        self.assertEqual(row["last_demand_completion_cycle"], 50)
        self.assertEqual(row["last_replay_completion_cycle"], 58)
        self.assertEqual(row["drained_service_envelope_cycles"], 58)

    def test_trigger_cost_charged_to_complete_endpoint(self):
        events = [Access(0, "I", A), Access(100, "I", B)]
        training = [Access(0, "I", A), Access(1, "I", B)]
        free = simulate(events, 100, training, "continuous", 2, 0,
                        Timing(first_response=40, install=2))
        costly = simulate(events, 100, training, "continuous", 2, 0,
                          Timing(first_response=40, install=2, trigger_cost=200))
        self.assertEqual(free["drained_service_envelope_cycles"], 100)
        self.assertEqual(costly["drained_service_envelope_cycles"], 300)

    def test_zero_latency_still_drains_and_respects_demand_priority(self):
        row = simulate([Access(0, "D", B)], 0, [Access(0, "I", A)],
                       "continuous", 1, 0,
                       Timing(first_response=0, install=0))
        self.assertEqual(row["last_demand_completion_cycle"], 8)
        self.assertEqual(row["last_replay_completion_cycle"], 16)

    def test_latency_and_bandwidth_are_independent(self):
        training = [Access(0, "I", A), Access(1, "D", B)]
        rows = [simulate([], 0, training, "continuous", 1, 1,
                         Timing(first_response=latency, install=0))
                for latency in (40, 80)]
        self.assertEqual(rows[0]["stats"]["bus_busy_cycles"], 16)
        self.assertEqual(rows[1]["stats"]["bus_busy_cycles"], 16)
        self.assertEqual(rows[1]["last_replay_completion_cycle"] -
                         rows[0]["last_replay_completion_cycle"], 40)
        slow = simulate([], 0, training, "continuous", 1, 1,
                        Timing(first_response=40, install=0, cycles_per_beat=2))
        self.assertEqual(slow["stats"]["bus_busy_cycles"], 32)
        self.assertEqual(slow["last_replay_completion_cycle"], 72)

    def test_one_mshr_per_demand_side(self):
        row = simulate([Access(0, "I", A), Access(1, "I", B)], 1,
                       timing=Timing(first_response=40, install=2))
        self.assertEqual(row["last_demand_completion_cycle"], 100)
        self.assertEqual(row["stats"]["demand_reads"], 2)

    def test_retained_lru_does_not_issue_speculation(self):
        row = simulate([Access(1, "I", A)], 1,
                       [Access(0, "I", A)], "demand-retained", 1, 0,
                       Timing(trigger_cost=100))
        self.assertEqual(row["drained_service_envelope_cycles"], 1)
        self.assertNotIn("triggers", row["stats"])

    def test_preseed_and_continuous_are_identical_for_one_window(self):
        args = ([Access(100, "I", A)], 200, [Access(0, "I", A)])
        preseed = simulate(*args, mode="preseed")
        continuous = simulate(*args, mode="continuous")
        preseed.pop("mechanism")
        continuous.pop("mechanism")
        self.assertEqual(preseed, continuous)

    def test_continuous_has_multiple_triggers_only_when_supplied(self):
        args = ([Access(100, "I", A)], 200, [Access(0, "I", A)])
        one = simulate(*args, mode="preseed", triggers=(0, 150))
        two = simulate(*args, mode="continuous", triggers=(0, 150))
        self.assertEqual(one["stats"]["triggers"], 1)
        self.assertEqual(two["stats"]["triggers"], 2)
        self.assertEqual(two["stats"]["suppressed_replay_reads"], 1)

    def test_invalid_timing_rejected(self):
        for kwargs in ({"first_response": -1}, {"replay_slots": 0},
                       {"cycles_per_beat": 0}, {"trigger_cost": -1}):
            with self.assertRaises(ValueError):
                Timing(**kwargs)

    def test_cli_generates_bound_inputs_and_all_mechanisms(self):
        raw = ("TRACE_HEADER elapsed=10 i_count=1 d_count=0 i_overflow=0 "
               "d_overflow=0 armed=0\n"
               "TRACE_RECORD side=I relative=2 paddr=0x80000000\n"
               "TRACE_PASS records=1\n")
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "trace.log"
            out = Path(directory) / "results.json"
            p.write_text(raw)
            main(["--training", str(p), "--trace", str(p), "--output", str(out),
                  "--latencies", "41", "--capacities", "1", "--oracle"])
            data = json.loads(out.read_text())
            self.assertEqual(len(data["rows"]), 15)
            self.assertEqual(data["inputs"][0]["accesses"], 1)
            self.assertIn("not Linux speedup", data["scope"])

    def test_trace_parser_counts_disarm_tail(self):
        raw = ("TRACE_HEADER elapsed=10 i_count=2 d_count=0 i_overflow=0 "
               "d_overflow=0 armed=0\n"
               "TRACE_RECORD side=I relative=2 paddr=0x80000000\n"
               "TRACE_RECORD side=I relative=11 paddr=0x80000040\n"
               "TRACE_PASS records=2\n")
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "trace.log"
            p.write_text(raw)
            trace = parse_trace(p)
            self.assertEqual(len(trace.accesses), 1)
            self.assertEqual(trace.post_boundary_records, 1)
            for modified in (raw.replace("i_overflow=0", "i_overflow=1"),
                             raw.replace("i_count=2", "i_count=3"),
                             raw.replace("TRACE_PASS", "TRACE_TRUNCATED")):
                p.write_text(modified)
                with self.assertRaises(ValueError):
                    parse_trace(p)


if __name__ == "__main__":
    unittest.main()
