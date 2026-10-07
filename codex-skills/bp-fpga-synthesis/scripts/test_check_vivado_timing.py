#!/usr/bin/env python3

from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("check_vivado_timing.sh")


class TimingGateTests(unittest.TestCase):
    def run_gate(self, wns):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "timing.rpt"
            report.write_text(
                "    WNS(ns)      TNS(ns)  TNS Failing Endpoints\n"
                "    -------      -------  ---------------------\n"
                f"     {wns}        0.000                      0\n"
            )
            return subprocess.run(
                [str(SCRIPT), str(report)], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_accepts_nonnegative_wns(self):
        result = self.run_gate("0.350")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "WNS_NS=0.350\n")

    def test_rejects_negative_wns(self):
        result = self.run_gate("-0.377")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "WNS_NS=-0.377\n")
        self.assertIn("Routed timing failed", result.stderr)

    def test_rejects_missing_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "timing.rpt"
            report.write_text("not a timing summary\n")
            result = subprocess.run(
                [str(SCRIPT), str(report)], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unable to parse", result.stderr)


if __name__ == "__main__":
    unittest.main()
