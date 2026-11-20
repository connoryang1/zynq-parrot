"""Verify optional whole-cell resource accounting with real host processes.

Interposed getrusage values check exact arithmetic and observer placement;
actual kernel rusage checks coarse process-accounting invariants only.
Host nanoseconds and host resources are not FPGA performance evidence.
"""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
FIELDS = ("minor_faults", "major_faults", "user_us", "system_us",
          "voluntary_switches", "involuntary_switches")
EXPECTED = dict(zip(FIELDS, (16, 22, 500000, 90, 26, 34)))
MOCK = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
static unsigned calls, mode;
static pid_t owner;
static int log_fd;
static void event(const char *name, long value)
{
    dprintf(log_fd, "%s pid=%ld value=%ld\n", name, (long)getpid(), value);
}
__attribute__((constructor)) static void initialize(void)
{
    owner = getpid();
    log_fd = open(getenv("BP_RESOURCE_MOCK_LOG"), O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (log_fd < 0) _exit(90);
}
pid_t __real_fork(void);
pid_t __wrap_fork(void)
{
    pid_t child = __real_fork();
    if (child > 0) event("fork", child);
    return child;
}
pid_t __real_waitpid(pid_t, int *, int);
pid_t __wrap_waitpid(pid_t child, int *status, int options)
{
    pid_t result = __real_waitpid(child, status, options);
    event("wait", result);
    return result;
}
void __real_free(void *);
void __wrap_free(void *memory)
{
    if (memory) event("free", 0);
    __real_free(memory);
}
int __real_munmap(void *, size_t);
int __wrap_munmap(void *memory, size_t size)
{
    event("munmap", 0);
    return __real_munmap(memory, size);
}
int __wrap_getrusage(int who, struct rusage *usage)
{
    unsigned cell = calls / 4, position = calls++ % 4;
    int child = who == RUSAGE_CHILDREN, end = position >= 2;
    const char *fault = getenv("BP_RESOURCE_MOCK_FAULT");
    const char *failure = getenv("BP_RESOURCE_MOCK_FAILURE_CALL");
    const char *delay = getenv("BP_RESOURCE_MOCK_DELAY");
    long base = (child ? 9000 + cell * 1000 : 1000 + cell * 100);
    if (getpid() != owner || child != (int)(position & 1) ||
        (who != RUSAGE_SELF && who != RUSAGE_CHILDREN)) _exit(91);
    event("usage", calls);
    if (failure && calls == strtoul(failure, NULL, 10)) { errno = EIO; return -1; }
    if (delay) {
        struct timespec pause = { .tv_nsec = 2000000 };
        while (nanosleep(&pause, &pause) && errno == EINTR) { }
    }
    memset(usage, 0, sizeof(*usage));
    usage->ru_minflt = base + (end ? (child ? 13 : 3) : 0);
    usage->ru_majflt = base + 50 + (end ? (child ? 17 : 5) : 0);
    usage->ru_nvcsw = base + 100 + (end ? (child ? 19 : 7) : 0);
    usage->ru_nivcsw = base + 150 + (end ? (child ? 23 : 11) : 0);
    usage->ru_utime.tv_sec = (child ? 100 + cell * 9 : 10 + cell * 3) + end;
    usage->ru_utime.tv_usec = end ? 100000 : (child ? 800000 : 900000);
    usage->ru_stime.tv_sec = (child ? 200 + cell * 9 : 20 + cell * 3) + end;
    usage->ru_stime.tv_usec = end ? (child ? 40 : 20) : (child ? 999980 : 999990);
    if (fault && end) {
        if (!strcmp(fault, "negative-counter")) usage->ru_minflt = base - 1;
        if (!strcmp(fault, "negative-time")) {
            --usage->ru_utime.tv_sec;
            usage->ru_utime.tv_usec = 0;
        }
        if (!strcmp(fault, "invalid-usec")) usage->ru_utime.tv_usec = 1000000;
        if (!strcmp(fault, "time-overflow")) usage->ru_utime.tv_sec = LONG_MAX;
    }
    if (fault && !strcmp(fault, "negative-base")) usage->ru_minflt = -1;
    if (fault && !strcmp(fault, "sum-overflow")) {
        usage->ru_utime.tv_sec = end ? INT64_C(10000000000000) : 0;
        usage->ru_utime.tv_usec = 0;
    }
    return 0;
}
/* The optional retention mock records the same stream as the observers.
 * Resource-only binaries link without these functions being called.
 */
int bp_resume_host_retention_prctl(int option, unsigned long arg2,
                                  unsigned long arg3, unsigned long arg4, unsigned long arg5)
{
    if (getpid() != owner || arg3 || arg4 || arg5) _exit(92);
    if (option == 0x42505061) {
        event("control", arg2);
        mode = arg2;
        return 0;
    }
    if (option != 0x42505062 || !arg2) _exit(93);
    event("status", mode);
    *(uint64_t *)arg2 = (UINT64_C(1) << 63) | mode | (mode ? 4 : 0);
    return 0;
}
void bp_resume_host_retention_hint(unsigned enabled) { (void)enabled; }
void bp_resume_host_retention_task_mode(unsigned enabled) { event("task_mode", enabled); }
'''


class ResumeResourceAccountingTests(unittest.TestCase):
    def test_plain_resource_make_target_does_not_link_optional_library_or_abi(self):
        run = subprocess.run(
            ["make", "--no-print-directory", "-n", "-C", str(HERE),
             "emit-pipe-hint-benchmark-plain-resources-compressed-transfer",
             "BP_LINUX_DYNAMIC_CC=/bin/true", "OUT=" + str(self.root / "make-only")],
            text=True, capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        commands = [line for line in run.stdout.splitlines()
                    if " -o " in line and "scheduler_pipe_hint_benchmark.c" in line]
        self.assertEqual(len(commands), 1, run.stdout)
        self.assertIn("-DBP_RESUME_RESOURCE_STATS=1", commands[0])
        self.assertNotIn("BP_RESUME_ZLIB", commands[0])
        self.assertNotIn("BP_RESUME_RETENTION", commands[0])
        self.assertNotIn("-lz", commands[0])
        self.assertIn("scheduler_pipe_hint_benchmark_plain_resources_dynamic", run.stdout)
        self.assertIn("emit_resume_transfer.py", run.stdout)

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="resume-resource-host-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.mock = cls.root / "resource_mock.c"
        cls.mock.write_text(MOCK)
        cls.compiler = os.environ.get("BP_HOST_CC", "cc")
        cls.base_command = [cls.compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-DBP_RESUME_HOST_VERIFY=1", str(HERE / "scheduler_pipe_hint_benchmark.c")]
        cls.mocked = cls.compile("mocked", mock=True)
        cls.combined = cls.compile("combined", mock=True, retention=True)
        cls.actual = cls.compile("actual", zlib=True)

    @classmethod
    def compile(cls, name, mock=False, retention=False, zlib=False):
        binary = cls.root / name
        command = cls.base_command + ["-DBP_RESUME_RESOURCE_STATS=1"]
        if retention:
            command += ["-DBP_RESUME_RETENTION=1"]
        if zlib:
            command += ["-DBP_RESUME_ZLIB=1"]
        if mock:
            command += [str(cls.mock)]
            command += ["-Wl,--wrap=" + name for name in ("getrusage", "fork", "waitpid", "free", "munmap")]
        command += ["-o", str(binary)] + (["-lz"] if zlib else [])
        subprocess.run(command, check=True, capture_output=True, timeout=30)
        return binary

    def run_benchmark(self, binary=None, sync="pipe", profile="plain", workload="lookup", flags=None,
                      policy="preseed"):
        with tempfile.TemporaryDirectory(prefix="resource-events-") as directory:
            log = Path(directory) / "events"
            env = os.environ.copy()
            env.update(flags or {})
            env["BP_RESOURCE_MOCK_LOG"] = str(log)
            selected = min(os.sched_getaffinity(0))
            run = subprocess.run([str(binary or self.mocked), "3", "2", policy, "2", sync,
                                  profile, "32", workload], env=env, text=True,
                                 capture_output=True, timeout=10,
                                 preexec_fn=lambda: os.sched_setaffinity(0, {selected}))
            events = [tuple(match.groups()) for match in re.finditer(
                r"^(\w+) pid=(\d+) value=(-?\d+)$", log.read_text() if log.exists() else "", re.M)]
            return run, events

    def resources(self, output):
        pattern = (r"^PIPE_HINT_HOST_VERIFY_RESOURCE repeat=(\d+) order=(\d+) enabled=([01]) "
                   + " ".join(field + r"=(\d+)" for field in FIELDS) + "$")
        return [tuple(map(int, match)) for match in re.findall(pattern, output, re.M)]

    def assert_markers(self, run, retention=False, legs=False):
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("PIPE_HINT_HOST_VERIFY_PASS", run.stdout)
        self.assertNotRegex(run.stdout, r"PIPE_HINT_(?:RESULT|WHOLE|RETENTION|RESOURCE|PASS)\b")
        sequence = ["RESULT"] + (["LEGS"] if legs else []) + ["WHOLE"]
        sequence += (["RETENTION"] if retention else []) + ["RESOURCE"]
        markers = re.findall(r"^PIPE_HINT_HOST_VERIFY_(RESULT|LEGS|WHOLE|RETENTION|RESOURCE)\b", run.stdout, re.M)
        self.assertEqual(markers, sequence * 4)
        steady = list(map(int, re.findall(r"HOST_VERIFY_RESULT .*? cycles=(\d+) loops=3", run.stdout)))
        whole = list(map(int, re.findall(r"HOST_VERIFY_WHOLE .*? cycles=(\d+) loops=3", run.stdout)))
        self.assertEqual(len(steady), 4)
        self.assertEqual(len(whole), 4)
        self.assertTrue(all(total >= measured for total, measured in zip(whole, steady)))
        return steady, whole

    def test_exact_deltas_and_cumulative_children_with_real_forks(self):
        for sync in ("pipe", "futex"):
            for profile in (("plain", "legs") if sync == "futex" else ("plain",)):
                with self.subTest(sync=sync, profile=profile):
                    run, events = self.run_benchmark(sync=sync, profile=profile)
                    self.assert_markers(run, legs=profile == "legs")
                    rows = self.resources(run.stdout)
                    self.assertEqual([row[:3] for row in rows], [(0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 0)])
                    self.assertEqual([dict(zip(FIELDS, row[3:])) for row in rows], [EXPECTED] * 4)
                    parent = next(pid for name, pid, value in events if name == "usage")
                    owned = [(name, int(value)) for name, pid, value in events if pid == parent]
                    usage = [index for index, event in enumerate(owned) if event[0] == "usage"]
                    self.assertEqual([owned[index][1] for index in usage], list(range(1, 17)))
                    for cell in range(4):
                        window = owned[usage[cell * 4 + 1] + 1:usage[cell * 4 + 2]]
                        self.assertEqual([name for name, _ in window],
                                         ["fork", "wait"] + (["munmap"] if sync == "futex" else []) + ["free"])
                        self.assertGreater(window[0][1], 0)
                        self.assertEqual(window[0][1], window[1][1])
                    self.assertFalse(any(name in ("control", "status", "task_mode") for name, _, _ in events))

    def test_whole_timer_includes_all_four_resource_observers(self):
        run, _ = self.run_benchmark(flags={"BP_RESOURCE_MOCK_DELAY": "1"})
        steady, whole = self.assert_markers(run)
        # Each of four wrapped observers sleeps at least 2 ms per cell.
        self.assertTrue(all(total - measured >= 8_000_000 for total, measured in zip(whole, steady)))

    def test_combined_accounting_finishes_after_retention_reset_and_readback(self):
        for policy, mode in (("preseed", 0), ("retention-rr", 1), ("retention-first", 2)):
            for sync in ("pipe", "futex"):
                with self.subTest(sync=sync, policy=policy):
                    run, events = self.run_benchmark(binary=self.combined, sync=sync, policy=policy)
                    self.assert_markers(run, retention=True)
                    self.assertEqual([dict(zip(FIELDS, row[3:])) for row in self.resources(run.stdout)], [EXPECTED] * 4)
                    parent = next(pid for name, pid, value in events if name == "usage")
                    owned = [(name, int(value)) for name, pid, value in events if pid == parent]
                    for index, (name, value) in enumerate(owned):
                        if name == "usage" and value % 4 == 3:
                            cell = (value - 3) // 4
                            enabled = (cell // 2) ^ (cell % 2)
                            self.assertEqual(owned[index - 3:index],
                                             [("status", mode if enabled else 0), ("control", 0), ("status", 0)])

    def test_each_resource_syscall_error_fails_closed(self):
        for call in (1, 2, 3, 4, 5, 6, 7, 8):
            with self.subTest(call=call):
                run, _ = self.run_benchmark(flags={"BP_RESOURCE_MOCK_FAILURE_CALL": str(call)})
                self.assertEqual(run.returncode, 1, run.stderr)
                self.assertIn("cell resource", run.stderr)
                self.assertNotIn("HOST_VERIFY_PASS", run.stdout)
                self.assertEqual(len(self.resources(run.stdout)), (call - 1) // 4)

    def test_negative_invalid_and_overflowing_accounting_fails_closed(self):
        for fault in ("negative-counter", "negative-base", "negative-time", "invalid-usec",
                      "time-overflow", "sum-overflow"):
            with self.subTest(fault=fault):
                run, _ = self.run_benchmark(flags={"BP_RESOURCE_MOCK_FAULT": fault})
                self.assertEqual(run.returncode, 1, run.stderr)
                self.assertIn("cell resource accounting", run.stderr)
                self.assertNotIn("HOST_VERIFY_RESOURCE", run.stdout)
                self.assertNotIn("HOST_VERIFY_PASS", run.stdout)

    def test_actual_kernel_rusage_for_all_workloads_and_transports(self):
        for sync in ("pipe", "futex"):
            for workload in ("scan", "lookup", "parse", "chase", "deflate"):
                with self.subTest(sync=sync, workload=workload):
                    run, _ = self.run_benchmark(binary=self.actual, sync=sync, workload=workload)
                    self.assert_markers(run)
                    rows = self.resources(run.stdout)
                    self.assertEqual(len(rows), 4)
                    for row in rows:
                        values = dict(zip(FIELDS, row[3:]))
                        self.assertTrue(all(value >= 0 for value in values.values()))
                        self.assertGreater(values["minor_faults"], 0)  # New child and private allocation.
                        self.assertGreater(values["user_us"] + values["system_us"], 0)
                        self.assertGreater(values["voluntary_switches"] + values["involuntary_switches"], 0)

    def test_resource_zero_preserves_plain_and_zlib_only_elf_bytes(self):
        for zlib in (False, True):
            binaries = []
            for defined in (False, True):
                binary = self.root / ("gate-zero-%d-%d" % (zlib, defined))
                command = self.base_command + (["-DBP_RESUME_ZLIB=1"] if zlib else [])
                command += ["-DBP_RESUME_RESOURCE_STATS=0"] if defined else []
                command += ["-o", str(binary)] + (["-lz"] if zlib else [])
                subprocess.run(command, check=True, capture_output=True, timeout=30)
                binaries.append(binary.read_bytes())
            self.assertEqual(hashlib.sha256(binaries[0]).digest(), hashlib.sha256(binaries[1]).digest())


if __name__ == "__main__":
    unittest.main()
