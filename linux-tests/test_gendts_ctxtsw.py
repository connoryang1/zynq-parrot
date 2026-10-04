#!/usr/bin/env python3
"""Verify the context-switch DTS wrapper changes bootargs and timebase once."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
WRAPPER = HERE / "gendts_ctxtsw.py"
SOURCE = '''/dts-v1/;
/ {
  cpus { timebase-frequency = <10000000>; };
  chosen { bootargs = "console=hvc0 loglevel=8 root=/dev/ram0"; };
};
'''


class DeviceTreeWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.generator = Path(self.temp.name) / "base.py"
        self.generator.write_text(
            "#!/usr/bin/env python3\nprint(" + repr(SOURCE) + ")\n")
        self.generator.chmod(0o755)

    def run_wrapper(self, **updates):
        env = os.environ.copy()
        env["BP_BASE_GENDTS"] = str(self.generator)
        env.update(updates)
        return subprocess.run([sys.executable, str(WRAPPER)], env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_defaults_select_pid1_and_eight_mhz(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('bootargs = "console=hvc0 loglevel=8 rdinit=/ctxtsw_user_tiny";',
                      result.stdout)
        self.assertIn("timebase-frequency = <8000000>;", result.stdout)
        self.assertNotIn("timebase-frequency = <10000000>;", result.stdout)

    def test_frequency_override_and_invalid_value(self):
        result = self.run_wrapper(BP_DEMO_TIMEBASE_FREQUENCY="4000000")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("timebase-frequency = <4000000>;", result.stdout)
        bad = self.run_wrapper(BP_DEMO_TIMEBASE_FREQUENCY="zero")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("must be an integer", bad.stderr)


if __name__ == "__main__":
    unittest.main()
