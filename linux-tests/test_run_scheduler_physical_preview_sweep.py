"""Validate complete, balanced board-run ordering for physical preview sweeps."""

import unittest

from run_scheduler_physical_preview_sweep import cell_plan


class CellPlanTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
