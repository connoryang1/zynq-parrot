"""Test strict analysis of the tagged Linux replay benchmark."""

import json
import tempfile
import unittest
from pathlib import Path

from analyze_scheduler_tagged_replay import analyze


def write_run(root, corrupt_counter=False, lines=32, probe_status=False,
              downstream_status=False, status_bits_59_58=False,
              layout="aligned"):
    """Create a complete synthetic matched A/B transcript and status."""
    path = root / "run.log"
    rows = [
        f"TAGGED_REPLAY_CONFIG mode=data lines={lines} slot=2 delay=0 gap=2 "
        f"policy=fifo lead_cycles=0 layout={layout} "
        f"probe_status={int(probe_status)}"
    ]
    for trial in range(512):
        enabled = ((trial ^ (trial >> 1)) & 1) ^ ((trial >> 2) & 1)
        admitted = lines if enabled else 0
        triggers = enabled
        if corrupt_counter and trial == 4:
            admitted -= 1
        entry = 100 + trial % 3
        load = 280 if enabled else 300
        preblock = ((1 << 42) | (admitted << 10)) \
            if probe_status and enabled else 0
        entry_status = preblock
        if probe_status and enabled and downstream_status:
            preblock |= (2 << 60) | (1 << 63)
            entry_status |= 1 << 60
        if probe_status and enabled and status_bits_59_58:
            preblock |= 3 << 58
            entry_status |= 2 << 58
        rows.append(
            f"TAGGED_REPLAY trial={trial} enabled={enabled} hooks={enabled} "
            f"hook_cycles={10 + enabled} admitted={admitted} filtered=0 "
            f"triggers={triggers} dropped=0 wake_to_entry={entry} "
            f"load_cycles={load} wake_to_load={entry + load} "
            f"roundtrip={entry + load + 40} "
            f"preblock_status=0x{preblock:016x} "
            f"preblock_probe_cycles={30 if probe_status else 0} "
            f"entry_probe_status=0x{entry_status:016x} "
            f"entry_probe_cycles={32 if probe_status else 0}"
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
        "lines_per_base": lines // 4,
        "probe_status": probe_status,
        "layout": layout,
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

    def test_reduced_footprint_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), lines=16), bootstrap_samples=10
            )
        self.assertEqual(result["config"]["lines"], 16)
        self.assertEqual(result["counter_deltas"]["admitted_entries"], 4096)

    def test_skew_layout_is_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), layout="skew"),
                bootstrap_samples=10,
            )
        self.assertEqual(result["config"]["layout"], "skew")

    def test_preblock_probe_is_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), lines=16, probe_status=True),
                bootstrap_samples=10,
            )
        self.assertEqual(result["preblock_probe"]["enabled_busy_trials"], 0)
        self.assertEqual(result["preblock_probe"]["enabled_admitted_median"], 16)
        self.assertEqual(result["preblock_probe"]["entry_admitted_median"], 16)

    def test_downstream_uce_status_is_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), lines=16, probe_status=True,
                          downstream_status=True),
                bootstrap_samples=10,
            )
        probe = result["preblock_probe"]
        self.assertEqual(probe["uce_outstanding_histogram"]["enabled"], {"2": 256})
        self.assertEqual(probe["uce_complete_histogram"]["enabled"], {"1": 256})
        self.assertEqual(
            probe["entry_uce_outstanding_histogram"]["enabled"], {"1": 256}
        )
        self.assertEqual(
            probe["entry_uce_complete_histogram"]["enabled"], {"0": 256}
        )

    def test_status_bits_59_58_are_reported_neutrally(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), lines=16, probe_status=True,
                          status_bits_59_58=True),
                bootstrap_samples=10,
            )
        probe = result["preblock_probe"]
        self.assertEqual(
            probe["status_bits_59_58_histogram"]["enabled"], {"3": 256}
        )
        self.assertEqual(
            probe["entry_status_bits_59_58_histogram"]["enabled"], {"2": 256}
        )

    def test_status_parameter_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory))
            status_path = path.with_suffix(".log.status.json")
            status = json.loads(status_path.read_text())
            status["gap"] = 3
            status_path.write_text(json.dumps(status) + "\n")
            with self.assertRaisesRegex(ValueError, "status gap"):
                analyze(path, bootstrap_samples=10)

    def test_rt_throttling_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory))
            path.write_text(path.read_text() + "sched: RT throttling activated\n")
            with self.assertRaisesRegex(ValueError, "RT throttling activated"):
                analyze(path, bootstrap_samples=10)


if __name__ == "__main__":
    unittest.main()
