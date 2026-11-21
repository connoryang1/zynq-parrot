"""Verify optional global-retention workload controls using real host processes.

Retention prctls are an explicit shared-memory mock, never hardware accesses.
Host timing proves interval containment and protocol completion only; it is
neither simulated BlackParrot timing nor FPGA evidence.
"""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
MOCK = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
struct hardware { unsigned mode, reads; pid_t owner; };
static struct hardware *hardware;
static int log_fd;
static void event(const char *name, unsigned value)
{
    dprintf(log_fd, "%s pid=%ld mode=%u\n", name, (long)getpid(), value);
}
__attribute__((constructor)) static void initialize(void)
{
    hardware = mmap(NULL, sizeof(*hardware), PROT_READ | PROT_WRITE,
                    MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (hardware == MAP_FAILED) _exit(90);
    hardware->owner = getpid();
    log_fd = open(getenv("BP_RETENTION_MOCK_LOG"), O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (log_fd < 0) _exit(91);
}
int bp_resume_host_retention_prctl(int option, unsigned long arg2,
                                  unsigned long arg3, unsigned long arg4, unsigned long arg5)
{
    if (arg3 || arg4 || arg5) { errno = EINVAL; return -1; }
    if (option == 0x42505061) {
        event("control", arg2);
        if (arg2 > 2) { errno = EINVAL; return -1; }
        if (arg2 && getenv("BP_RETENTION_MOCK_SET_FAIL")) { errno = EPERM; return -1; }
        hardware->mode = arg2;
        hardware->reads = 0;
        return 0;
    }
    if (option != 0x42505062 || !arg2) { errno = EINVAL; return -1; }
    event("status", hardware->mode);
    if (getenv("BP_RETENTION_MOCK_OLD")) { errno = ENODEV; return -1; }
    ++hardware->reads;
    if (hardware->mode && hardware->reads >= 2 && getenv("BP_RETENTION_MOCK_FINISH_FAIL")) {
        errno = EIO; return -1;
    }
    uint64_t status = UINT64_C(1) << 63;
    if (hardware->mode)
        status |= hardware->mode | 4 | ((uint64_t)(100 + hardware->mode) << 16);
    if (getenv("BP_RETENTION_MOCK_CAP_ZERO")) status = 0;
    if (hardware->mode && getenv("BP_RETENTION_MOCK_WRONG_MODE")) status ^= 3;
    *(uint64_t *)arg2 = status;
    return 0;
}
void bp_resume_host_retention_hint(unsigned enabled)
{
    event("hint", enabled);
    if (getpid() != hardware->owner && getenv("BP_RETENTION_MOCK_CHILD_FAIL"))
        exit(7); /* Exercise inherited atexit handler without touching hardware. */
}
void bp_resume_host_retention_task_mode(unsigned enabled)
{
    event("task_mode", enabled);
}
'''


class ResumeRetentionProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="resume-retention-host-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        mock = cls.root / "retention_mock.c"
        mock.write_text(MOCK)
        cls.binary = cls.root / "benchmark"
        cls.compiler = os.environ.get("BP_HOST_CC", "cc")
        cls.base_command = [cls.compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-DBP_RESUME_HOST_VERIFY=1", str(HERE / "scheduler_pipe_hint_benchmark.c")]
        subprocess.run(cls.base_command + ["-DBP_RESUME_RETENTION=1", str(mock), "-o", str(cls.binary)],
                       check=True, capture_output=True, timeout=30)

    def run_benchmark(self, policy="retention-rr", sync="futex", workload="lookup", flags=None, binary=None):
        with tempfile.TemporaryDirectory(prefix="retention-events-") as directory:
            log = Path(directory) / "events"
            env = os.environ.copy()
            env.update(flags or {})
            env["BP_RETENTION_MOCK_LOG"] = str(log)
            selected = min(os.sched_getaffinity(0))
            run = subprocess.run([str(binary or self.binary), "3", "2", policy, "2", sync,
                                  "plain", "32", workload], env=env, text=True,
                                 capture_output=True, timeout=10,
                                 preexec_fn=lambda: os.sched_setaffinity(0, {selected}))
            events = [tuple(match.groups()) for match in re.finditer(
                r"^(control|status|hint|task_mode) pid=(\d+) mode=(\d+)$", log.read_text(), re.M)]
            return run, events

    def test_both_policies_both_transports_decode_mock_status_and_contain_timing(self):
        for policy, mode in (("retention-rr", 1), ("retention-first", 2)):
            for sync in ("pipe", "futex"):
                for workload in ("scan", "lookup", "parse", "chase"):
                    with self.subTest(policy=policy, sync=sync, workload=workload):
                        run, events = self.run_benchmark(policy, sync, workload)
                        self.assertEqual(run.returncode, 0, run.stderr)
                        self.assertIn("PIPE_HINT_HOST_VERIFY_PASS", run.stdout)
                        self.assertNotIn("PIPE_HINT_PASS", run.stdout)
                        self.assertFalse(any(event[0] == "hint" for event in events))
                        self.assertEqual([event[2] for event in events if event[0] == "task_mode"], ["0"])
                        controls = [event for event in events if event[0] == "control"]
                        self.assertEqual([int(event[2]) for event in controls], [0, 0, mode, 0, mode, 0, 0, 0])
                        self.assertEqual(len({event[1] for event in controls}), 1)
                        steady = [int(value) for value in re.findall(
                            r"HOST_VERIFY_RESULT .*? cycles=(\d+) loops=3", run.stdout)]
                        whole = [int(value) for value in re.findall(
                            r"HOST_VERIFY_WHOLE .*? cycles=(\d+) loops=3", run.stdout)]
                        self.assertEqual(len(steady), 4)
                        self.assertEqual(len(whole), 4)
                        self.assertTrue(all(total >= measured for total, measured in zip(whole, steady)))
                        statuses = re.findall(
                            r"HOST_VERIFY_RETENTION repeat=(\d+) order=(\d+) enabled=([01]) "
                            r"raw=(0x[0-9a-f]+) capability=(\d+) mode=(\d+) completed=(\d+) consumed_fetches=(\d+)",
                            run.stdout)
                        self.assertEqual(len(statuses), 4)
                        for _repeat, _order, enabled, raw, cap, actual, completed, consumed in statuses:
                            expected = mode if int(enabled) else 0
                            expected_raw = (1 << 63) | expected
                            if expected:
                                expected_raw |= 4 | ((100 + expected) << 16)
                            self.assertEqual(int(raw, 16), expected_raw)
                            self.assertEqual((int(cap), int(actual), int(completed), int(consumed)),
                                             (1, expected, bool(expected), 100 + expected if expected else 0))

    def test_legacy_control_in_optional_binary_reports_whole_cost_and_keeps_mode_zero(self):
        run, events = self.run_benchmark("preseed")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len([event for event in events if event[0] == "hint"]), 4)
        self.assertTrue(all(event[2] == "0" for event in events if event[0] == "control"))
        self.assertEqual(run.stdout.count("HOST_VERIFY_WHOLE"), 4)

    def test_old_hardware_or_absent_capability_fails_without_changing_policy(self):
        for flag in ("BP_RETENTION_MOCK_OLD", "BP_RETENTION_MOCK_CAP_ZERO"):
            with self.subTest(flag=flag):
                run, events = self.run_benchmark(flags={flag: "1"})
                self.assertEqual(run.returncode, 1, run.stderr)
                self.assertNotIn("CONFIG", run.stdout)
                self.assertFalse(any(event[0] == "control" for event in events))

    def test_control_readback_and_post_timing_errors_reset_global_policy(self):
        for flag in ("BP_RETENTION_MOCK_SET_FAIL", "BP_RETENTION_MOCK_WRONG_MODE",
                     "BP_RETENTION_MOCK_FINISH_FAIL"):
            with self.subTest(flag=flag):
                run, events = self.run_benchmark(flags={flag: "1"})
                self.assertEqual(run.returncode, 1, run.stderr)
                self.assertNotIn("HOST_VERIFY_PASS", run.stdout)
                controls = [event for event in events if event[0] == "control"]
                self.assertEqual(controls[-1][2], "0")
                self.assertEqual(len({event[1] for event in controls}), 1)

    def test_failing_child_cannot_run_global_cleanup_and_parent_reaps_it(self):
        run, events = self.run_benchmark("continuous", "pipe",
                                         flags={"BP_RETENTION_MOCK_CHILD_FAIL": "1"})
        self.assertEqual(run.returncode, 1, run.stderr)
        controls = [event for event in events if event[0] == "control"]
        owner = controls[0][1]
        self.assertTrue(any(event[0] == "hint" and event[1] != owner for event in events))
        self.assertEqual({event[1] for event in controls}, {owner})
        self.assertEqual(controls[-1][2], "0")

    def test_retention_zero_preserves_plain_and_zlib_only_elf_bytes(self):
        for zlib in (False, True):
            binaries = []
            for enabled in (False, True):
                binary = self.root / ("gate-zero-%d-%d" % (zlib, enabled))
                command = self.base_command + (["-DBP_RESUME_ZLIB=1"] if zlib else [])
                command += ["-DBP_RESUME_RETENTION=0"] if enabled else []
                command += ["-o", str(binary)] + (["-lz"] if zlib else [])
                subprocess.run(command, check=True, capture_output=True, timeout=30)
                binaries.append(binary.read_bytes())
            self.assertEqual(hashlib.sha256(binaries[0]).digest(), hashlib.sha256(binaries[1]).digest())

    def test_optional_retention_and_real_zlib_roundtrips_work_together(self):
        binary = self.root / "retention-zlib"
        subprocess.run(self.base_command + ["-DBP_RESUME_RETENTION=1", "-DBP_RESUME_ZLIB=1",
                                            str(self.root / "retention_mock.c"), "-lz", "-o", str(binary)],
                       check=True, capture_output=True, timeout=30)
        for policy in ("retention-rr", "retention-first"):
            run, events = self.run_benchmark(policy, workload="deflate", binary=binary)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("HOST_VERIFY_LIBRARY name=zlib", run.stdout)
            self.assertIn("HOST_VERIFY_PASS", run.stdout)
            self.assertFalse(any(event[0] == "hint" for event in events))


if __name__ == "__main__":
    unittest.main()
