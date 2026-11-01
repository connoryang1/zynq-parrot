"""Validate balanced-cell parsing and full-sweep acceptance for preview analysis."""

import gzip
import tempfile
import unittest
from pathlib import Path

from analyze_scheduler_physical_preview_sweep import analyze
from analyze_scheduler_physical_preview_benchmark import TIMING_MODES
from compare_scheduler_physical_preview_sweeps import compare, compare_timing_pairs
from pool_scheduler_physical_preview_replicates import pool
from analyze_scheduler_physical_preview_tail import (
    analyze as analyze_tail,
    pool_tail,
)
from analyze_scheduler_physical_preview_chronology import (
    analyze as analyze_chronology,
)


def transcript(group=0, timing="late", trials=512, extra_enabled_hook=False,
               core_marker="CORE PASS", saved_load_cycles=20,
               saved_return_cycles=0, include_tail=False):
    mode_value = TIMING_MODES[timing]
    lines = [
        f"PHYSICAL_BENCH_CONFIG group={group} first_offset={group * 256} "
        f"lines=4 timing={timing} mode={mode_value}",
        "PHYSICAL_BENCH_CHILD PASS",
    ]
    for trial in range(trials):
        mode = 1 if trial % 4 in (1, 2) else 0
        entry = 100 + mode
        load = 300 - saved_load_cycles * mode
        hooks = 0 if timing in ("trigger", "wake-trigger") else mode
        hooks += 1 if extra_enabled_hook and mode and trial == 1 else 0
        post_load = 20
        return_handoff = 30 - saved_return_cycles * mode
        lines.append(
            f"PHYSICAL_BENCH trial={trial} mode={mode} hooks={hooks} "
            f"wake_to_entry={entry} load_cycles={load} "
            f"wake_to_load={entry + load} "
            f"roundtrip={entry + load + post_load + return_handoff}"
        )
        if include_tail:
            lines.append(
                f"PHYSICAL_BENCH_TAIL trial={trial} "
                f"child_post_load={post_load} return_handoff={return_handoff}"
            )
    lines.extend(("PHYSICAL_BENCH_PARENT PASS", core_marker, "BSG PASS"))
    return "\n".join(lines)


class SweepAnalyzerTest(unittest.TestCase):
    def test_chronology_analyzer_preserves_known_balanced_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wake-trigger.log"
            path.write_text("\n".join(
                transcript(group=group, timing="wake-trigger",
                           saved_load_cycles=20)
                for group in range(8)
            ))
            result = analyze_chronology(
                [path], "wake-trigger", samples=100
            )
        self.assertEqual(result["replay_state"], "historical-persistent")
        complete = result["windows"]["complete"]["metrics"]
        self.assertEqual(
            complete["load_cycles"]["paired_saved"]["median_cycles"], 20
        )
        self.assertEqual(
            complete["wake_to_entry"]["off3_minus_off0"]["median_cycles"],
            0,
        )

    def test_single_cell_analyzer_accepts_instruction_mode(self):
        self.assertEqual(TIMING_MODES["instruction"], 3)

    def test_single_cell_analyzer_accepts_counter_mode(self):
        self.assertEqual(TIMING_MODES["counter"], 4)

    def test_single_cell_analyzer_accepts_trigger_mode(self):
        self.assertEqual(TIMING_MODES["trigger"], 5)

    def test_single_cell_analyzer_accepts_wakeup_trigger_mode(self):
        self.assertEqual(TIMING_MODES["wake-trigger"], 6)
        self.assertEqual(TIMING_MODES["wake-data"], 6)
        self.assertEqual(TIMING_MODES["wake-early-data"], 1)

    def test_wakeup_early_data_matrix_requires_counted_hooks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wake-early-data.log"
            path.write_text("\n".join(
                transcript(group=group, timing="wake-early-data")
                for group in range(8)
            ))
            result = analyze([path], bootstrap_samples=100)
        self.assertEqual(
            result["pooled"]["wake-early-data"]["load_cycles"]
            ["stratified_median_saved_cycles"],
            20.0,
        )

    def test_partial_cell_reports_known_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(transcript(group=3))
            result = analyze([path], allow_partial=True, bootstrap_samples=100)
        self.assertEqual(result["cells"]["late_3"]["l2_set_group"], 3)
        self.assertEqual(
            result["pooled"]["late"]["load_cycles"]
            ["stratified_median_saved_cycles"], 20.0)

    def test_instruction_only_matrix_is_analyzable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instruction.log"
            path.write_text("\n".join(
                transcript(group=group, timing="instruction")
                for group in range(8)
            ))
            result = analyze([path], bootstrap_samples=100)
        self.assertEqual(
            result["pooled"]["instruction"]["load_cycles"]
            ["stratified_median_saved_cycles"],
            20.0,
        )

    def test_counter_only_matrix_is_analyzable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "counter.log"
            path.write_text("\n".join(
                transcript(group=group, timing="counter")
                for group in range(8)
            ))
            result = analyze([path], bootstrap_samples=100)
        self.assertEqual(
            result["pooled"]["counter"]["load_cycles"]
            ["stratified_median_saved_cycles"],
            20.0,
        )

    def test_trigger_only_matrix_requires_zero_hooks_and_is_analyzable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trigger.log"
            path.write_text("\n".join(
                transcript(group=group, timing="trigger")
                for group in range(8)
            ))
            result = analyze([path], bootstrap_samples=100)
        self.assertEqual(
            result["pooled"]["trigger"]["load_cycles"]
            ["stratified_median_saved_cycles"],
            20.0,
        )

    def test_wakeup_trigger_matrix_requires_zero_hooks_and_is_analyzable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wake-trigger.log"
            path.write_text("\n".join(
                transcript(group=group, timing="wake-trigger")
                for group in range(8)
            ))
            result = analyze([path], bootstrap_samples=100)
        self.assertEqual(
            result["pooled"]["wake-trigger"]["load_cycles"]
            ["stratified_median_saved_cycles"],
            20.0,
        )

    def test_incomplete_sweep_is_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(transcript())
            with self.assertRaisesRegex(ValueError, "incomplete sweep"):
                analyze([path], bootstrap_samples=100)

    def test_second_enabled_hook_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(transcript(extra_enabled_hook=True))
            with self.assertRaisesRegex(ValueError, "expected hook count 1"):
                analyze([path], allow_partial=True, bootstrap_samples=100)

    def test_truncated_cell_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(transcript(trials=128))
            with self.assertRaisesRegex(ValueError, "expected exactly 512"):
                analyze([path], allow_partial=True, bootstrap_samples=100)

    def test_indexed_core_pass_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(transcript(core_marker="CORE[0] PASS"))
            result = analyze([path], allow_partial=True, bootstrap_samples=100)
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

    def test_late_only_comparison_accepts_complete_late_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "control-late.log"
            candidate = root / "candidate-late.log"
            control.write_text("\n".join(
                transcript(group=group, timing="late", saved_load_cycles=10)
                for group in range(8)
            ))
            candidate.write_text("\n".join(
                transcript(group=group, timing="late", saved_load_cycles=30)
                for group in range(8)
            ))
            result = compare(
                [control], [candidate], samples=100, timings=("late",)
            )
        self.assertEqual(set(result["timings"]), {"late"})
        metric = result["timings"]["late"]["load_cycles"]
        self.assertEqual(metric["candidate_minus_control_saved_cycles"], 20.0)
        self.assertEqual(metric["candidate_minus_control_95pct_ci"], [20.0, 20.0])

    def test_cross_mode_comparison_accepts_two_complete_matrices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "counter.log"
            candidate = root / "instruction.log"
            control.write_text("\n".join(
                transcript(group=group, timing="counter", saved_load_cycles=10)
                for group in range(8)
            ))
            candidate.write_text("\n".join(
                transcript(group=group, timing="instruction", saved_load_cycles=30)
                for group in range(8)
            ))
            result = compare_timing_pairs(
                [control], [candidate], (("counter", "instruction"),),
                samples=100,
            )
        label = "instruction_minus_counter"
        self.assertEqual(
            result["timing_pairs"][label],
            {"control": "counter", "candidate": "instruction"},
        )
        metric = result["timings"][label]["load_cycles"]
        self.assertEqual(metric["candidate_minus_control_saved_cycles"], 20.0)
        self.assertEqual(metric["candidate_minus_control_95pct_ci"], [20.0, 20.0])

    def test_replication_pool_preserves_boot_and_group_strata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.log"
            second = root / "second.log"
            first.write_text("\n".join(
                transcript(group=group, timing="late", saved_load_cycles=10)
                for group in range(8)
            ))
            second.write_text("\n".join(
                transcript(group=group, timing="late", saved_load_cycles=30)
                for group in range(8)
            ))
            result = pool([[first], [second]], "late", samples=100)
        metric = result["metrics"]["load_cycles"]
        self.assertEqual(
            [item["saved_cycles"] for item in metric["replicates"]],
            [10.0, 30.0],
        )
        self.assertEqual(metric["pooled_saved_cycles"], 20.0)
        self.assertEqual(metric["pooled_95pct_ci_saved_cycles"], [20.0, 20.0])

    def test_tail_partition_localizes_return_handoff_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tail.log"
            path.write_text("\n".join(
                transcript(group=group, timing="late", saved_load_cycles=0,
                           saved_return_cycles=12, include_tail=True)
                for group in range(8)
            ))
            result = analyze_tail([path], "late", bootstrap_samples=100)
        self.assertEqual(
            result["pooled"]["child_post_load"]
            ["stratified_median_saved_cycles"], 0.0,
        )
        self.assertEqual(
            result["pooled"]["return_handoff"]
            ["stratified_median_saved_cycles"], 12.0,
        )
        self.assertEqual(
            result["pooled"]["post_load_total"]
            ["stratified_median_saved_cycles"], 12.0,
        )

    def test_trigger_tail_partition_accepts_zero_hook_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trigger-tail.log"
            path.write_text("\n".join(
                transcript(group=group, timing="trigger", saved_load_cycles=0,
                           saved_return_cycles=12, include_tail=True)
                for group in range(8)
            ))
            result = analyze_tail([path], "trigger", bootstrap_samples=100)
        self.assertEqual(
            result["pooled"]["return_handoff"]
            ["stratified_median_saved_cycles"], 12.0,
        )

    def test_tail_replication_pool_preserves_boot_and_group_strata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first-tail.log"
            second = root / "second-tail.log"
            first.write_text("\n".join(
                transcript(group=group, timing="late", saved_load_cycles=0,
                           saved_return_cycles=8, include_tail=True)
                for group in range(8)
            ))
            second.write_text("\n".join(
                transcript(group=group, timing="late", saved_load_cycles=0,
                           saved_return_cycles=16, include_tail=True)
                for group in range(8)
            ))
            result = pool_tail([[first], [second]], "late", samples=100)
        metric = result["metrics"]["return_handoff"]
        self.assertEqual(
            [item["saved_cycles"] for item in metric["replicates"]],
            [8.0, 16.0],
        )
        self.assertEqual(metric["pooled_saved_cycles"], 12.0)
        self.assertEqual(metric["pooled_95pct_ci_saved_cycles"], [12.0, 12.0])
        self.assertEqual(
            result["metrics"]["post_load_total"]["pooled_saved_cycles"],
            12.0,
        )


if __name__ == "__main__":
    unittest.main()
