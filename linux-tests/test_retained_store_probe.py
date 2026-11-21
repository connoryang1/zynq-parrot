"""Exercise the new guest probe with real fork and mocked kernel primitives.

These tests issue no host prctl, change no real credentials, and run no target.
They check successful bounded polling and fail-closed capability/cleanup paths.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from retained_control_test_support import compile_fixture


class RetainedStoreProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="retained-probe-", dir="/dev/shm")
        cls.binary = compile_fixture(cls.tmp.name, probe=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_probe(self, argument="present", **changes):
        env = {key: value for key, value in os.environ.items() if not key.startswith("MOCK_")}
        env.update({"MOCK_" + key: str(value) for key, value in changes.items()})
        log = Path(self.tmp.name) / "calls.log"
        log.unlink(missing_ok=True)
        env["MOCK_LOG"] = str(log)
        result = subprocess.run([str(self.binary), argument], env=env, text=True,
                                capture_output=True, timeout=10)
        rows = [tuple(int(value, 16 if index == 2 else 10)
                      for index, value in enumerate(line.split()))
                for line in log.read_text().splitlines()] if log.exists() else []
        return result, rows

    def assert_fail(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("_PASS", result.stdout + result.stderr)
        self.assertIn("RETAINED_STORE_PROBE_HOST_VERIFY_FAIL", result.stderr)

    def test_present_uses_actual_geometry_all_masks_real_child_and_reset(self):
        result, rows = self.run_probe(WRAP=0xc00)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("i_lines=65 d_lines=1320 set_log2=6", result.stdout)
        self.assertIn("busy_scope=uce_client_backend", result.stdout)
        self.assertIn("RETAINED_STORE_PROBE_HOST_VERIFY_PASS capability=present", result.stdout)
        self.assertNotIn("RETAINED_STORE_PROBE_PASS", result.stdout)
        parent = rows[0][0]
        root_rows = [r for r in rows if r[0] == parent]
        child_rows = [r for r in rows if r[0] != parent]
        self.assertEqual(len(set(r[0] for r in child_rows)), 1)
        self.assertTrue(all(r[1] == 65534 and r[4] == -1 for r in child_rows))
        self.assertEqual([r[3] for r in child_rows if r[2] == 0x42505063], list(range(16)))
        writes = [r for r in root_rows if r[2] == 0x42505063 and r[4] == 0]
        self.assertEqual([r[3] for r in writes], list(range(16)) + [15, 0])
        # Every root command probes first; invalid and denied calls touch no CSR.
        self.assertEqual(rows[-1][5], 0)
        self.assertTrue(all(r[-1] == 0 for r in rows))
        self.assertEqual(child_rows[0][6:8], child_rows[-1][6:8])
        self.assertTrue(any(r[2] == 0x42505064 and r[4] == 0 for r in root_rows[:10]))

    def test_zero_or_single_lane_geometries_and_arbitrary_set_log2(self):
        for i, d, sets in ((0, 0, 0), (0, 256, 5), (1024, 0, 7), (1536, 1320, 8)):
            with self.subTest(i=i, d=d):
                result, rows = self.run_probe(I_LINES=i, D_LINES=d, SET_LOG2=sets)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"i_lines={i} d_lines={d} set_log2={sets}", result.stdout)
                self.assertEqual(rows[-1][5], 0)

    def test_absent_never_writes_or_copies_status_and_still_checks_privilege(self):
        for failure in ("ABSENT", "NO_CAP"):
            with self.subTest(failure=failure):
                result, rows = self.run_probe("absent", **{failure: 1})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("capability=absent", result.stdout)
                self.assertTrue(all(r[7] == 0 for r in rows))
                self.assertEqual(len(set(r[0] for r in rows)), 2)

    def test_capability_descriptor_failures_before_any_valid_write(self):
        for fault in ("ABSENT", "NO_CAP", "TRUNCATE", "NO_FULL64", "RESERVED"):
            with self.subTest(fault=fault):
                result, rows = self.run_probe(**{fault: 1})
                self.assert_fail(result)
                self.assertTrue(all(r[7] == 0 for r in rows))

    def test_wrong_mode_and_geometry_drift_fail_and_attempt_reset(self):
        for fault in ("IGNORE_WRITE", "GEOMETRY_DRIFT"):
            with self.subTest(fault=fault):
                result, rows = self.run_probe(**{fault: 1})
                self.assert_fail(result)
                successful_controls = [r for r in rows if r[2] == 0x42505063 and r[4] == 0]
                self.assertEqual(successful_controls[-1][3], 0)
                self.assertEqual(rows[-1][5], 0)

    def test_busy_forever_is_bounded_and_cleanup_failure_is_visible(self):
        result, rows = self.run_probe(BUSY_FOREVER=1)
        self.assert_fail(result)
        self.assertIn("cleanup/reset", result.stderr)
        # Two bounded polls, plus initial capability/error calls and reset probes.
        self.assertLessEqual(rows[-1][6], 2 * 4096 + 10)
        self.assertEqual(rows[-1][5], 0)

    def test_privilege_bypass_denied_mutation_or_drop_failure_never_pass(self):
        for fault in ("PRIV_BYPASS", "DENIED_MUTATION", "DROP_FAIL"):
            with self.subTest(fault=fault):
                result, rows = self.run_probe(**{fault: 1})
                self.assert_fail(result)
                self.assertEqual(rows[-1][5], 0)

    def test_error_output_mutation_is_detected(self):
        result, _ = self.run_probe("absent", ABSENT=1, DIRTY_ERROR=1)
        self.assert_fail(result)
        self.assertIn("invalid status modified output", result.stderr)

    def test_normal_reset_failure_cannot_print_pass(self):
        result, _ = self.run_probe(BAD_CLEAR=1)
        self.assert_fail(result)
        self.assertIn("cleanup/reset", result.stderr)

    def test_wrong_cli_or_unprivileged_invocation_makes_no_calls(self):
        result, rows = self.run_probe("other")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(rows)
        result, rows = self.run_probe(UID=65534)
        self.assert_fail(result)
        self.assertFalse(rows)


if __name__ == "__main__":
    unittest.main()
