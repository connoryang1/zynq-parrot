"""Validate balanced-cell parsing and full-sweep acceptance for preview analysis."""

import gzip
import tempfile
import unittest
from pathlib import Path

from analyze_scheduler_physical_preview_sweep import analyze
from compare_scheduler_physical_preview_sweeps import compare


def transcript(group=0, timing="late", trials=512, extra_enabled_hook=False,
               core_marker="CORE PASS", saved_load_cycles=20):
    mode_value = 2 if timing == "late" else 1
    lines = [
        f"PHYSICAL_BENCH_CONFIG group={group} first_offset={group * 256} "
        f"lines=4 timing={timing} mode={mode_value}",
        "PHYSICAL_BENCH_CHILD PASS",
    ]
    for trial in range(trials):
        mode = 1 if trial % 4 in (1, 2) else 0
        entry = 100 + mode
        load = 300 - saved_load_cycles * mode
        hooks = mode + (1 if extra_enabled_hook and mode and trial == 1 else 0)
        lines.append(
            f"PHYSICAL_BENCH trial={trial} mode={mode} hooks={hooks} "
            f"wake_to_entry={entry} load_cycles={load} "
            f"wake_to_load={entry + load} roundtrip={entry + load + 50}"
        )
    lines.extend(("PHYSICAL_BENCH_PARENT PASS", core_marker, "BSG PASS"))
    return "\n".join(lines)


class SweepAnalyzerTest(unittest.TestCase):
    def test_partial_cell_reports_known_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(transcript(group=3))
            result = analyze([path], allow_partial=True)
        self.assertEqual(result["cells"]["late_3"]["l2_set_group"], 3)
        self.assertEqual(
            result["pooled"]["late"]["load_cycles"]
            ["stratified_median_saved_cycles"], 20.0)

    def test_incomplete_sweep_is_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(transcript())
            with self.assertRaisesRegex(ValueError, "incomplete sweep"):
                analyze([path])

    def test_second_enabled_hook_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(transcript(extra_enabled_hook=True))
            with self.assertRaisesRegex(ValueError, "expected exactly one hook"):
                analyze([path], allow_partial=True)

    def test_truncated_cell_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(transcript(trials=128))
            with self.assertRaisesRegex(ValueError, "expected exactly 512"):
                analyze([path], allow_partial=True)

    def test_indexed_core_pass_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(transcript(core_marker="CORE[0] PASS"))
            result = analyze([path], allow_partial=True)
        self.assertEqual(result["cells"]["late_0"]["trials"], 512)

    def test_independent_sweep_comparison_has_known_sign(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "control.log"
            candidate = root / "candidate.log.gz"
            control_text = "\n".join(
                transcript(group=group, timing=timing, saved_load_cycles=10)
                for timing in ("early", "late") for group in range(8)
            )
            candidate_text = "\n".join(
                transcript(group=group, timing=timing, saved_load_cycles=30)
                for timing in ("early", "late") for group in range(8)
            )
            control.write_text(control_text)
            with gzip.open(candidate, "wt") as stream:
                stream.write(candidate_text)
            result = compare([control], [candidate], samples=100)
        metric = result["timings"]["late"]["load_cycles"]
        self.assertEqual(metric["control_saved_cycles"], 10.0)
        self.assertEqual(metric["candidate_saved_cycles"], 30.0)
        self.assertEqual(metric["candidate_minus_control_saved_cycles"], 20.0)
        self.assertEqual(metric["candidate_minus_control_95pct_ci"], [20.0, 20.0])

    def test_comparison_rejects_incomplete_control(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "control.log"
            candidate = root / "candidate.log"
            control.write_text(transcript())
            candidate.write_text("\n".join(
                transcript(group=group, timing=timing)
                for timing in ("early", "late") for group in range(8)
            ))
            with self.assertRaisesRegex(ValueError, "control: incomplete sweep"):
                compare([control], [candidate], samples=10)


if __name__ == "__main__":
    unittest.main()
