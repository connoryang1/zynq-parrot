"""Observe real fork/library cells with a disabled baseline issuing no controls.

The interposed syscall log verifies actual call placement and error cleanup.
Host timing is never hardware performance evidence; legacy inputs stay frozen.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_resume_resource_accounting import MOCK as RESOURCE_MOCK, EXPECTED
from test_retained29_benchmark import MOCK
from test_retained29_regex_benchmark import REGEX_MOCK

HERE = Path(__file__).resolve().parent


class TriggerCostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="r29-cost-", dir="/dev/shm")
        cls.root = Path(cls.tmp.name)
        cls.binaries = {}
        for regex in (False, True):
            name = "regex" if regex else "plain"
            mock = cls.root / (name + "-mock.c")
            mock.write_text(RESOURCE_MOCK.replace("int __wrap_getrusage(", "int deterministic_getrusage(")
                            + MOCK + (REGEX_MOCK if regex else ""))
            binary = cls.root / name
            source = HERE / ("scheduler_retained29_regex_cost_benchmark.c" if regex
                             else "scheduler_retained29_cost_benchmark.c")
            wraps = ["prctl", "fork", "waitpid", "free", "munmap", "getrusage", "calloc", "printf", "puts"]
            if regex:
                wraps += ["malloc", "regcomp", "regexec", "regfree"]
            command = [os.environ.get("BP_HOST_CC", "cc"), "-O2", "-Wall", "-Wextra", "-Werror",
                       "-std=c11", "-DBP_RETAINED29_HOST_VERIFY=1", str(source), str(mock), "-o", str(binary)]
            command += ["-Wl,--wrap=" + name for name in wraps]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.binaries[name] = binary

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, workload="lookup", policy="ordinary-joint", fault=None):
        log = self.root / "events.log"
        log.unlink(missing_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("R29_", "BP_RESOURCE_MOCK_"))}
        env["BP_RESOURCE_MOCK_LOG"] = str(log)
        if fault:
            env["R29_FAULT"] = fault
        binary = self.binaries["regex" if workload == "regex" else "plain"]
        result = subprocess.run([str(binary), "3", "2", policy, "2", "futex", "plain", "32", workload, "none"],
                                env=env, capture_output=True, text=True, timeout=20)
        events = [(m[1], int(m[2]), int(m[3])) for m in re.finditer(
            r"^(\w+) pid=(\d+) value=(-?\d+)$", log.read_text(), re.M)]
        return result, events

    def test_all_workloads_and_lanes_charge_controls_only_to_enabled_cells(self):
        for workload in ("scan", "lookup", "parse", "chase", "regex"):
            for policy, mask in (("ordinary-i", 9), ("ordinary-d", 6), ("ordinary-joint", 15)):
                with self.subTest(workload=workload, policy=policy):
                    result, events = self.run_case(workload, policy)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("baseline=mode0-no-retained-control", result.stdout)
                    self.assertEqual([v for n, _, v in events if n == "r29_control"], [mask, 0, mask, 0])
                    starts = [n for n, (kind, _, value) in enumerate(events) if kind == "usage" and value % 4 == 1]
                    self.assertEqual(len(starts), 4)
                    for cell, begin in enumerate(starts):
                        end = next(n for n in range(begin + 1, len(events))
                                   if events[n][0] == "usage" and events[n][2] == 4 * (cell + 1))
                        window = events[begin:end + 1]
                        controls = [v for kind, _, v in window if kind == "r29_control"]
                        self.assertEqual(controls, [mask, 0] if cell in (1, 2) else [])
                        self.assertTrue(any(kind == "allocation" for kind, _, _ in window))
                        self.assertTrue(any(kind == "wait" for kind, _, _ in window))
                        self.assertTrue(any(kind == "free" for kind, _, _ in window))
                        if controls:
                            first = next(n for n, event in enumerate(window) if event[0] == "r29_control")
                            last = max(n for n, event in enumerate(window) if event[0] == "r29_control")
                            self.assertLess(first, min(n for n, event in enumerate(window) if event[0] == "allocation"))
                            self.assertGreater(last, max(n for n, event in enumerate(window) if event[0] in ("wait", "free")))
                    rows = re.findall(r"_CONTROL repeat=\d+ order=\d+ enabled=([01]) .*retained_control_writes=(\d+)", result.stdout)
                    self.assertEqual(rows, [("0", "0"), ("1", "2"), ("1", "2"), ("0", "0")])
                    self.assertTrue(all(value == 0 for name, _, value in events if name in ("report", "final_mode")))
                    for field, value in EXPECTED.items():
                        self.assertEqual(len(re.findall(r"\b" + field + "=" + str(value) + r"\b", result.stdout)), 4)

    def test_initial_active_state_refuses_without_control_or_allocation(self):
        for workload in ("lookup", "regex"):
            result, events = self.run_case(workload, fault="initial-active")
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("_PASS", result.stdout)
            self.assertFalse(any(n in ("r29_control", "allocation") for n, _, _ in events))

    def test_failed_activation_cleans_up_and_never_reports_complete_cohort(self):
        for workload in ("lookup", "regex"):
            result, events = self.run_case(workload, fault="control-failure")
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("_PASS", result.stdout)
            self.assertEqual([v for n, _, v in events if n == "r29_control"], [15, 0])
            self.assertEqual([v for n, _, v in events if n == "final_mode"], [0])


if __name__ == "__main__":
    unittest.main()
