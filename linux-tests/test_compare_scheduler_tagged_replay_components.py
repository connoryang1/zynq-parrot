#!/usr/bin/env python3
"""Test fail-closed attribution of tagged-replay component effects."""

import unittest
from pathlib import Path
from unittest import mock

from compare_scheduler_tagged_replay_components import compare


def loaded(mode, saved, identity="same", lines=32):
    config = {
        "mode": mode,
        "lines": lines,
        "slot": 2,
        "delay": 0,
        "gap": 0,
        "policy": "normal",
        "lead_cycles": 0,
        "probe_status": False,
        "layout": "skew",
        "sync": "futex",
        "kernel_mode": 9 if mode in ("data", "joint-explicit") else 0,
        "expected_hooks": 1 if mode in ("data", "joint-explicit") else 0,
        "icache_ranges": "full",
    }
    result = {"config": config, "identity": {"image": identity}}
    rows = []
    for trial in range(4):
        enabled = trial % 2
        row = {"enabled": enabled}
        for metric in ("hook_cycles", "wake_to_entry", "load_cycles",
                       "wake_to_load", "roundtrip"):
            row[metric] = 100 - (saved if enabled else 0)
        rows.append(row)
    return result, rows


class TaggedReplayComponentComparatorTests(unittest.TestCase):
    @mock.patch("compare_scheduler_tagged_replay_components.load")
    def test_reports_component_increments_and_interaction(self, load):
        load.side_effect = [
            loaded("data", 10), loaded("data", 10),
            loaded("instruction-explicit", 20),
            loaded("instruction-explicit", 20),
            loaded("joint-explicit", 35), loaded("joint-explicit", 35),
        ]
        output = compare(
            [Path("d1"), Path("d2")],
            [Path("i1"), Path("i2")],
            [Path("j1"), Path("j2")],
            bootstrap_samples=10,
        )
        metric = output["metrics"]["roundtrip"]
        self.assertEqual(metric["instruction_increment_with_data_saved_cycles"], 25)
        self.assertEqual(metric["data_increment_with_instruction_saved_cycles"], 15)
        self.assertEqual(metric["nonadditive_interaction_cycles"], 5)

    @mock.patch("compare_scheduler_tagged_replay_components.load")
    def test_rejects_wrong_mode(self, load):
        load.side_effect = [
            loaded("joint-explicit", 10), loaded("data", 10),
        ]
        with self.assertRaisesRegex(ValueError, "data transcripts"):
            compare([Path("d1"), Path("d2")],
                    [Path("i1"), Path("i2")],
                    [Path("j1"), Path("j2")], 10)

    @mock.patch("compare_scheduler_tagged_replay_components.load")
    def test_rejects_identity_change(self, load):
        load.side_effect = [
            loaded("data", 10), loaded("data", 10),
            loaded("instruction-explicit", 20),
            loaded("instruction-explicit", 20, identity="changed"),
            loaded("joint-explicit", 35), loaded("joint-explicit", 35),
        ]
        with self.assertRaisesRegex(ValueError, "exact image identity"):
            compare([Path("d1"), Path("d2")],
                    [Path("i1"), Path("i2")],
                    [Path("j1"), Path("j2")], 10)

    @mock.patch("compare_scheduler_tagged_replay_components.load")
    def test_rejects_workload_change(self, load):
        load.side_effect = [
            loaded("data", 10), loaded("data", 10),
            loaded("instruction-explicit", 20),
            loaded("instruction-explicit", 20),
            loaded("joint-explicit", 35, lines=16),
            loaded("joint-explicit", 35, lines=16),
        ]
        with self.assertRaisesRegex(ValueError, "workload configuration"):
            compare([Path("d1"), Path("d2")],
                    [Path("i1"), Path("i2")],
                    [Path("j1"), Path("j2")], 10)

    def test_requires_two_boots_per_arm(self):
        with self.assertRaisesRegex(ValueError, "data requires at least two"):
            compare([Path("d1")], [Path("i1"), Path("i2")],
                    [Path("j1"), Path("j2")], 10)


if __name__ == "__main__":
    unittest.main()
