"""Validate balanced-cell parsing and full-sweep acceptance for preview analysis."""

import tempfile
import unittest
from pathlib import Path

from analyze_scheduler_physical_preview_sweep import analyze


def transcript(group=0, timing="late", trials=512, extra_enabled_hook=False):
    mode_value = 2 if timing == "late" else 1
    lines = [
        f"PHYSICAL_BENCH_CONFIG group={group} first_offset={group * 256} "
        f"lines=4 timing={timing} mode={mode_value}",
        "PHYSICAL_BENCH_CHILD PASS",
    ]
    for trial in range(trials):
        mode = 1 if trial % 4 in (1, 2) else 0
        entry = 100 + mode
        load = 300 - 20 * mode
        hooks = mode + (1 if extra_enabled_hook and mode and trial == 1 else 0)
        lines.append(
            f"PHYSICAL_BENCH trial={trial} mode={mode} hooks={hooks} "
            f"wake_to_entry={entry} load_cycles={load} "
            f"wake_to_load={entry + load} roundtrip={entry + load + 50}"
        )
    lines.extend(("PHYSICAL_BENCH_PARENT PASS", "CORE PASS", "BSG PASS"))
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


if __name__ == "__main__":
    unittest.main()
