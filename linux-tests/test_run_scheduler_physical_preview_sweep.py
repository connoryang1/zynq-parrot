"""Validate complete, balanced board-run ordering for physical preview sweeps."""

import argparse
import tempfile
import unittest
from pathlib import Path

from run_scheduler_physical_preview_sweep import (
    SHELL_PROMPT,
    benchmark_command,
    cell_exit_pattern,
    cell_plan,
    parse_args,
    selected_cells,
    validate_args,
)


class CellPlanTest(unittest.TestCase):
    def test_board_runner_defaults_to_isolated_replay_arms(self):
        args = parse_args(["image.nbf", "transfer.sh", "1" * 64, "run.log"])
        self.assertEqual(args.replay_state, "isolated")

    def test_hot_proxy_is_the_only_extra_guest_argument(self):
        target = benchmark_command(2, "early", "target")
        proxy = benchmark_command(2, "early", "hot-proxy")
        self.assertIn(" 2 early; rc=$?", target)
        self.assertIn(" 2 early hot-proxy; rc=$?", proxy)

    def test_fifo_policy_materializes_footprint_argument(self):
        target = benchmark_command(2, "early", "target", "fifo")
        proxy = benchmark_command(2, "early", "hot-proxy", "fifo")
        self.assertIn(" 2 early target fifo; rc=$?", target)
        self.assertIn(" 2 early hot-proxy fifo; rc=$?", proxy)

    def test_isolated_replay_materializes_all_positional_arguments(self):
        target = benchmark_command(
            2, "wake-trigger", "target", "normal", "isolated"
        )
        proxy = benchmark_command(
            2, "wake-trigger", "hot-proxy", "fifo", "isolated"
        )
        self.assertIn(
            " 2 wake-trigger target normal isolated; rc=$?", target
        )
        self.assertIn(
            " 2 wake-trigger hot-proxy fifo isolated; rc=$?", proxy
        )

    def test_fixed_arm_materializes_all_positional_arguments(self):
        enabled = benchmark_command(
            2, "wake-trigger", "hot-proxy", "normal", "persistent", "enabled"
        )
        disabled = benchmark_command(
            2, "wake-trigger", "hot-proxy", "normal", "persistent", "disabled"
        )
        self.assertIn(
            " 2 wake-trigger hot-proxy normal persistent enabled; rc=$?",
            enabled,
        )
        self.assertIn(
            " 2 wake-trigger hot-proxy normal persistent disabled; rc=$?",
            disabled,
        )

    def test_accepts_both_established_root_prompts(self):
        self.assertIsNotNone(SHELL_PROMPT.search("\r\n~ # "))
        self.assertIsNotNone(SHELL_PROMPT.search("\r\n# "))
        self.assertIsNone(SHELL_PROMPT.search("\r\n$ "))

    def test_cell_exit_accepts_repeated_uart_carriage_returns(self):
        match = cell_exit_pattern(3, "late").search(
            "PHYSICAL_CELL_EXIT group=3 timing=late rc=1\r\r\r\n"
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "1")

    def test_plan_covers_each_cell_once(self):
        plan = cell_plan()
        expected = {(group, timing) for group in range(8)
                    for timing in ("early", "late")}
        self.assertEqual(len(plan), 16)
        self.assertEqual(set(plan), expected)

    def test_timing_order_alternates_by_group(self):
        plan = cell_plan()
        for group in range(8):
            timings = [timing for cell_group, timing in plan
                       if cell_group == group]
            expected = ["early", "late"] if group % 2 == 0 else ["late", "early"]
            self.assertEqual(timings, expected)

    def test_recovery_suffix_has_no_duplicate_prefix_cells(self):
        plan = cell_plan()
        self.assertEqual(selected_cells(10), plan[10:])
        self.assertFalse(set(plan[:10]) & set(selected_cells(10)))

    def test_late_only_plan_fits_one_pre_boundary_boot(self):
        late = selected_cells(0, "late")
        self.assertEqual(len(late), 8)
        self.assertEqual({group for group, _timing in late}, set(range(8)))
        self.assertTrue(all(timing == "late" for _group, timing in late))

    def test_instruction_plan_has_one_cell_per_group_and_suffix(self):
        instruction = selected_cells(0, "instruction")
        self.assertEqual(
            instruction,
            [(group, "instruction") for group in range(8)],
        )
        self.assertEqual(selected_cells(6, "instruction"), instruction[6:])

    def test_counter_plan_has_one_cell_per_group_and_suffix(self):
        counter = selected_cells(0, "counter")
        self.assertEqual(
            counter,
            [(group, "counter") for group in range(8)],
        )
        self.assertEqual(selected_cells(6, "counter"), counter[6:])

    def test_trigger_plan_has_one_cell_per_group_and_suffix(self):
        trigger = selected_cells(0, "trigger")
        self.assertEqual(
            trigger,
            [(group, "trigger") for group in range(8)],
        )
        self.assertEqual(selected_cells(6, "trigger"), trigger[6:])

    def test_wakeup_trigger_plan_has_one_cell_per_group_and_suffix(self):
        trigger = selected_cells(0, "wake-trigger")
        self.assertEqual(
            trigger,
            [(group, "wake-trigger") for group in range(8)],
        )
        self.assertEqual(selected_cells(6, "wake-trigger"), trigger[6:])

    def test_single_group_filter_selects_one_wakeup_cell(self):
        self.assertEqual(
            selected_cells(0, "wake-trigger", 3),
            [(3, "wake-trigger")],
        )

    def test_invalid_recovery_boundary_is_rejected(self):
        for start in (-1, 16):
            with self.assertRaisesRegex(ValueError, "start cell"):
                selected_cells(start)

    def test_missing_log_parent_fails_before_board_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nbf = root / "image.nbf"
            transfer = root / "transfer.sh"
            nbf.write_text("nbf")
            transfer.write_text("command\n")
            args = argparse.Namespace(
                nbf=nbf,
                transfer=transfer,
                elf_sha256="1" * 64,
                control_sha256="2" * 64,
                runtime_ms=100,
                footprint="target",
                policy="normal",
                replay_state="persistent",
                arm="enabled",
                only_timing=None,
                only_group=None,
                start_cell=0,
                log=root / "missing" / "run.log",
            )
            with self.assertRaisesRegex(ValueError, "log parent"):
                validate_args(args)


if __name__ == "__main__":
    unittest.main()
