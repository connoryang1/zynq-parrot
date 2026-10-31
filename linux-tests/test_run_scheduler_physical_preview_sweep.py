"""Validate complete, balanced board-run ordering for physical preview sweeps."""

import unittest

from run_scheduler_physical_preview_sweep import (
    SHELL_PROMPT,
    cell_exit_pattern,
    cell_plan,
    selected_cells,
)


class CellPlanTest(unittest.TestCase):
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

    def test_invalid_recovery_boundary_is_rejected(self):
        for start in (-1, 16):
            with self.assertRaisesRegex(ValueError, "start cell"):
                selected_cells(start)


if __name__ == "__main__":
    unittest.main()
