"""Test strict analysis of the tagged 32-line Linux replay benchmark."""

import json
import tempfile
import unittest
from pathlib import Path

from analyze_scheduler_tagged_replay import analyze


def write_run(root, corrupt_counter=False):
    """Create a complete synthetic matched A/B transcript and status."""
    path = root / "run.log"
    rows = [
        "TAGGED_REPLAY_CONFIG mode=data lines=32 slot=2 delay=0 gap=2 "
        "policy=fifo lead_cycles=0"
    ]
    admitted = triggers = 0
    for trial in range(512):
        enabled = (trial ^ (trial >> 1)) & 1
        if enabled:
            admitted += 32
            triggers += 1
        if corrupt_counter and trial == 5:
            admitted -= 1
        entry = 100 + trial % 3
        load = 280 if enabled else 300
        rows.append(
            f"TAGGED_REPLAY trial={trial} enabled={enabled} hooks={enabled} "
            f"hook_cycles={10 + enabled} admitted={admitted} filtered=0 "
            f"triggers={triggers} dropped=0 wake_to_entry={entry} "
            f"load_cycles={load} wake_to_load={entry + load} "
            f"roundtrip={entry + load + 40}"
        )
    rows.extend((
        "TAGGED_REPLAY_CHILD PASS retries=0",
        "TAGGED_REPLAY_PARENT PASS",
        "CORE[0] PASS",
        "BSG PASS",
    ))
    path.write_text("\n".join(rows) + "\n")
    status = {
        "status": "PASS",
        "nbf_sha256": "1" * 64,
        "transfer_sha256": "2" * 64,
        "elf_sha256": "3" * 64,
        "control_program_sha256": "4" * 64,
        "bitstream_sha256": "5" * 64,
        "mode": "data",
        "delay": 0,
        "gap": 2,
        "policy": "fifo",
        "lead_cycles": 0,
    }
    path.with_suffix(".log.status.json").write_text(json.dumps(status) + "\n")
    return path


class TaggedReplayAnalyzerTest(unittest.TestCase):
    def test_known_effect_and_complete_counters_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(write_run(Path(directory)), bootstrap_samples=100)
        self.assertEqual(result["trials_per_arm"], 256)
        self.assertEqual(result["counter_deltas"]["accepted_triggers"], 256)
        self.assertEqual(result["counter_deltas"]["admitted_entries"], 8192)
        self.assertEqual(
            result["metrics"]["load_cycles"]["paired_median_saved_cycles"], 20
        )

    def test_incomplete_replay_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory), corrupt_counter=True)
            with self.assertRaisesRegex(ValueError, "did not complete all replay entries"):
                analyze(path, bootstrap_samples=10)

    def test_status_parameter_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory))
            status_path = path.with_suffix(".log.status.json")
            status = json.loads(status_path.read_text())
            status["gap"] = 3
            status_path.write_text(json.dumps(status) + "\n")
            with self.assertRaisesRegex(ValueError, "status gap"):
                analyze(path, bootstrap_samples=10)


if __name__ == "__main__":
    unittest.main()
