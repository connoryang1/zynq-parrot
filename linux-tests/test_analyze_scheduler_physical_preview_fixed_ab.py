"""Test strict fresh-boot fixed-arm pipe replay analysis."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from analyze_scheduler_physical_preview_fixed_ab import analyze


IDENTITY = {
    "nbf_sha256": "1" * 64,
    "transfer_sha256": "2" * 64,
    "elf_sha256": "3" * 64,
    "control_program_sha256": "4" * 64,
}


def write_run(root, name, arm, base, group=7):
    """Write one complete synthetic runner transcript and status."""
    path = root / f"{name}.log"
    mode = 1 if arm == "enabled" else 0
    lines = [
        f"PHYSICAL_BENCH_CONFIG group={group} first_offset={group * 256} "
        "lines=4 timing=wake-trigger mode=6 footprint=hot-proxy policy=fifo "
        f"replay_state=persistent arm={arm}",
        "PHYSICAL_BENCH_CHILD PASS retries=0",
    ]
    for trial in range(512):
        entry = base + trial % 3
        load = 20
        child = 30
        returned = 40
        lines.append(
            f"PHYSICAL_BENCH trial={trial} mode={mode} hooks=0 "
            f"wake_to_entry={entry} load_cycles={load} "
            f"wake_to_load={entry + load} "
            f"roundtrip={entry + load + child + returned}"
        )
        lines.append(
            f"PHYSICAL_BENCH_TAIL trial={trial} child_post_load={child} "
            f"return_handoff={returned}"
        )
    lines.extend((
        "PHYSICAL_BENCH_PARENT PASS",
        f"PHYSICAL_CELL_EXIT group={group} timing=wake-trigger rc=0",
        "CORE[0] PASS",
        "BSG PASS",
    ))
    path.write_text("\n".join(lines) + "\n")
    status = {
        "status": "PASS",
        **IDENTITY,
        "footprint": "hot-proxy",
        "policy": "fifo",
        "replay_state": "persistent",
        "arm": arm,
        "cells": [f"{group}:wake-trigger"],
    }
    path.with_suffix(".log.status.json").write_text(
        json.dumps(status) + "\n"
    )
    return path


class FixedArmAnalyzerTest(unittest.TestCase):
    def test_kernel_failure_marker_is_rejected_despite_pass_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_run(root, "bad", "enabled", 90)
            path.write_text(
                path.read_text().replace("BSG PASS", "BUG: synthetic\nBSG PASS")
            )
            with self.assertRaisesRegex(ValueError, "kernel failure marker"):
                from analyze_scheduler_physical_preview_fixed_ab import load_run
                load_run(path, "enabled", IDENTITY, 7)

    def test_opposite_order_replicates_report_known_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            e1 = write_run(root, "e1", "enabled", 90)
            d1 = write_run(root, "d1", "disabled", 100)
            e2 = write_run(root, "e2", "enabled", 92)
            d2 = write_run(root, "d2", "disabled", 102)
            args = argparse.Namespace(
                **IDENTITY,
                group=7,
                replicate=[
                    ("enabled-disabled", str(e1), str(d1)),
                    ("disabled-enabled", str(e2), str(d2)),
                ],
                iid_resamples=100,
                block_resamples=100,
            )
            result = analyze(args)
        metric = result["metrics"]["wake_to_entry"]
        self.assertEqual(metric["replicate_stratified_point_estimate"], -10)
        self.assertEqual(metric["pooled_median_difference_enabled_minus_disabled"], -10)
        self.assertEqual(metric["iid_bootstrap"]["fraction_enabled_faster"], 1)

    def test_mismatched_status_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            e1 = write_run(root, "e1", "enabled", 90)
            d1 = write_run(root, "d1", "disabled", 100)
            e2 = write_run(root, "e2", "enabled", 92)
            d2 = write_run(root, "d2", "disabled", 102)
            status_path = e1.with_suffix(".log.status.json")
            status = json.loads(status_path.read_text())
            status["elf_sha256"] = "f" * 64
            status_path.write_text(json.dumps(status) + "\n")
            args = argparse.Namespace(
                **IDENTITY,
                group=7,
                replicate=[
                    ("enabled-disabled", str(e1), str(d1)),
                    ("disabled-enabled", str(e2), str(d2)),
                ],
                iid_resamples=10,
                block_resamples=10,
            )
            with self.assertRaisesRegex(ValueError, "status elf_sha256"):
                analyze(args)


if __name__ == "__main__":
    unittest.main()
