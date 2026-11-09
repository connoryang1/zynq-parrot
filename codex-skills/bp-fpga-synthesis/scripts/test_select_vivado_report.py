#!/usr/bin/env python3
"""Verify deterministic Vivado timing and utilization report selection."""

from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("select_vivado_report.sh")


class ReportSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def select(self, kind):
        return subprocess.run(
            [str(SCRIPT), kind, str(self.root)], check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()

    def touch(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n")
        return str(path)

    def test_prefers_postroute_physopt_timing(self):
        self.touch("z_timing_summary_routed.rpt")
        preferred = self.touch("a_timing_summary_postroute_physopted.rpt")
        self.assertEqual(self.select("timing"), preferred)

    def test_falls_back_to_routed_timing(self):
        routed = self.touch("z_timing_summary_routed.rpt")
        self.assertEqual(self.select("timing"), routed)

    def test_prefers_placed_utilization_and_ignores_clock_report(self):
        self.touch("a_clock_utilization_routed.rpt")
        self.touch("b_utilization_routed.rpt")
        placed = self.touch("z_utilization_placed.rpt")
        self.assertEqual(self.select("utilization"), placed)

    def test_falls_back_to_design_routed_utilization(self):
        self.touch("a_clock_utilization_routed.rpt")
        routed = self.touch("b_utilization_routed.rpt")
        self.assertEqual(self.select("utilization"), routed)

    def test_missing_report_returns_empty_successfully(self):
        self.assertEqual(self.select("timing"), "")


if __name__ == "__main__":
    unittest.main()
