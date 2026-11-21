"""Check real fork/workload/teardown with a shared ABI29 mock, never a board.

Resource values and event observers reuse the maintained resource-test fixture.
New assertions check ownership, activation/output boundaries and failure cleanup.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_resume_resource_accounting import MOCK as RESOURCE_MOCK, EXPECTED

HERE = Path(__file__).resolve().parent
MOCK = r'''
#include <stdarg.h>
struct hw { unsigned mode, busy, writes, source_count, injected, replay_reads, data_count, data_injected; };
static struct hw *hw;
static const char *fault;
static int isfault(const char *name) { return fault && !strcmp(fault,name); }
int __real_getrusage(int,struct rusage *);
int __wrap_getrusage(int who,struct rusage *usage) {
    if(getenv("R29_REAL_USAGE")) {
        if(getpid()!=owner) _exit(94);
        event("actual_usage",who);
        return __real_getrusage(who,usage);
    }
    return deterministic_getrusage(who,usage);
}
__attribute__((constructor)) static void hw_init(void) {
    hw=mmap(0,sizeof(*hw),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
    if(hw==MAP_FAILED) _exit(95);
    fault=getenv("R29_FAULT");
    if(isfault("initial-active")) hw->mode=9;
}
__attribute__((destructor)) static void hw_final(void) {
    if(getpid()==owner) event("final_mode",hw->mode);
}
long bp_retained29_host_replay_status(void) {
    if(getpid()!=owner) _exit(93);
    ++hw->replay_reads;
    uint64_t raw=UINT64_C(3)<<58;
    if(isfault("replay-activity") && hw->writes>=2 && !hw->data_injected) {
        hw->data_count=1;hw->data_injected=1;
    }
    raw|=(uint64_t)hw->data_count<<10;
    if(isfault("replay-saturated")) raw|=UINT64_C(65535)<<10;
    if(hw->replay_reads<3 || isfault("replay-busy")) raw|=(UINT64_C(1)<<63)|(UINT64_C(2)<<60);
    event("replay",(long)raw);
    return (long)raw;
}
void *__real_calloc(size_t,size_t);
void *__wrap_calloc(size_t n,size_t size) {
    event("allocation",n*size);
    if((isfault("child-allocation") && getpid()!=owner) ||
       (isfault("parent-allocation") && getpid()==owner)) { errno=ENOMEM; return 0; }
    return __real_calloc(n,size);
}
int __wrap_prctl(int option,...) {
    va_list ap;va_start(ap,option);
    unsigned long a2=va_arg(ap,unsigned long),a3=va_arg(ap,unsigned long);
    unsigned long a4=va_arg(ap,unsigned long),a5=va_arg(ap,unsigned long);va_end(ap);
    if(a3||a4||a5) _exit(96);
    if(option==0x4250505a) {
        event("task_mode",a2);
        if(a2) _exit(97);
        if(isfault("source-off") && hw->mode && getpid()==owner) { errno=EIO;return -1; }
        return 0;
    }
    if(option==0x4250505e) {
        if(isfault("prefix-activity") && hw->writes>=2 && !hw->injected) { hw->source_count=1;hw->injected=1; }
        uint64_t raw=1|(32UL<<4)|((uint64_t)hw->source_count<<38);
        if(isfault("prefix-busy")) raw|=2;
        if(isfault("prefix-saturated")) raw|=UINT64_C(255)<<38;
        *(uint64_t *)a2=raw;event("prefix",hw->source_count);return 0;
    }
    if(option==0x42505063) {
        event("r29_control",a2);
        if(getpid()!=owner || a2>15) _exit(98);
        if(isfault("control-failure") && a2) { errno=EIO; return -1; }
        ++hw->writes;hw->mode=a2;hw->busy=3;
        if(isfault("wrong-readback") && a2) hw->mode=0;
        if(isfault("bad-reset") && !a2 && hw->writes>1) hw->mode=1;
        return 0;
    }
    if(option==0x42505064) {
        event("r29_status",hw->mode);
        if(getpid()!=owner) _exit(99);
        if(isfault("absent")) { errno=ENODEV;return -1; }
        uint64_t raw=(UINT64_C(1)<<63)|(UINT64_C(3)<<56)|(UINT64_C(6)<<48)
          |(UINT64_C(1320)<<32)|(UINT64_C(65)<<16)|hw->mode;
        if(hw->busy || (isfault("busy") && hw->writes)) { raw|=0x300;if(hw->busy)--hw->busy; }
        if(isfault("truncated")) raw&=0xffffffff;
        if(isfault("no-i")) raw&=~(UINT64_C(65535)<<16);
        if(isfault("no-d")) raw&=~(UINT64_C(65535)<<32);
        if(isfault("reserved")) raw|=16;
        if(isfault("geometry-drift") && hw->writes) raw^=UINT64_C(1)<<16;
        *(uint64_t *)a2=raw;return 0;
    }
    event("FORBIDDEN_PRCTL",option);errno=EINVAL;return -1;
}
static void report_guard(void) {
    event("report",hw->mode);
    if(hw->mode) _exit(100);
}
int __wrap_printf(const char *format,...) {
    report_guard();va_list ap;va_start(ap,format);int r=vprintf(format,ap);va_end(ap);return r;
}
int __real_puts(const char *);
int __wrap_puts(const char *text) { report_guard();return __real_puts(text); }
'''


class Retained29BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="retained29-benchmark-", dir="/dev/shm")
        cls.root = Path(cls.tmp.name)
        mock = cls.root / "mock.c"
        self_observer = RESOURCE_MOCK.replace("int __wrap_getrusage(", "int deterministic_getrusage(")
        if self_observer == RESOURCE_MOCK: raise AssertionError("resource fixture observer missing")
        mock.write_text(self_observer + MOCK)
        cls.binary = cls.root / "benchmark"
        command = [os.environ.get("BP_HOST_CC", "cc"), "-O2", "-Wall", "-Wextra", "-Werror",
                   "-std=c11", "-DBP_RETAINED29_HOST_VERIFY=1", "-o", str(cls.binary),
                   str(HERE / "scheduler_retained29_benchmark.c"), str(mock)]
        command += ["-Wl,--wrap=" + n for n in ("prctl", "fork", "waitpid", "free", "munmap",
                                               "getrusage", "calloc", "printf", "puts")]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        if result.returncode: raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, policy="ordinary-joint", sync="futex", workload="scan", kib=32,
                 profile="plain", fault=None, resource=None, arguments=None):
        log = self.root / "events.log"
        log.unlink(missing_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("R29_", "BP_RESOURCE_MOCK_"))}
        env["BP_RESOURCE_MOCK_LOG"] = str(log)
        if fault: env["R29_FAULT"] = fault
        if resource: env.update(resource)
        args = arguments if arguments is not None else ["3", "2", policy, "2", sync, profile, str(kib), workload, "none"]
        result = subprocess.run([str(self.binary), *args], env=env, text=True, capture_output=True, timeout=15)
        events = [tuple((m[1], int(m[2]), int(m[3]))) for m in re.finditer(
                  r"^(\w+) pid=(\d+) value=(-?\d+)$", log.read_text(), re.M)]
        return result, events

    def fail_closed(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("_PASS", result.stdout)

    def test_all_six_policies_real_processes_requested_masks_and_teardown(self):
        for policy, mask in (("ordinary-i", 9), ("ordinary-d", 6), ("ordinary-joint", 15),
                             ("advisory-i", 1), ("advisory-d", 2), ("advisory-joint", 3)):
            for sync in ("pipe", "futex"):
                with self.subTest(policy=policy, sync=sync):
                    result, events = self.run_case(policy=policy, sync=sync)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("RESUME_RETAINED29_HOST_VERIFY_PASS", result.stdout)
                    self.assertNotIn("RESUME_RETAINED29_PASS", result.stdout)
                    self.assertNotIn("PIPE_HINT_", result.stdout)
                    self.assertIn("advisory_source=none", result.stdout)
                    parent = next(pid for name, pid, _ in events if name == "r29_control")
                    controls = [(pid, value) for name, pid, value in events if name == "r29_control"]
                    self.assertTrue(all(pid == parent for pid, _ in controls))
                    self.assertEqual([v for _, v in controls], [0, 0, mask, 0, mask, 0, 0, 0])
                    self.assertEqual(sum(name == "fork" for name, _, _ in events), 4)
                    self.assertEqual(len(set(pid for name, pid, _ in events if name == "allocation")), 5)
                    self.assertTrue(all(value == 0 for name, _, value in events if name in ("task_mode", "report", "final_mode")))
                    self.assertFalse(any(name == "FORBIDDEN_PRCTL" for name, _, _ in events))
                    self.assertEqual(sum(name == "usage" for name, _, _ in events), 16)
                    resources = re.findall(r"_RESOURCE .*", result.stdout)
                    for row in resources:
                        values = dict((k, int(v)) for k, v in re.findall(r"(\w+)=(\d+)", row))
                        for field, expected in EXPECTED.items(): self.assertEqual(values[field], expected)
                    steady = [int(v) for v in re.findall(r"_RESULT .*?cycles=(\d+)", result.stdout)]
                    whole = [int(v) for v in re.findall(r"_WHOLE .*?cycles=(\d+)", result.stdout)]
                    self.assertEqual(len(steady), 4)
                    self.assertTrue(all(a >= b for a, b in zip(whole, steady)))

    def test_observers_control_before_allocation_and_reset_after_all_free_reap(self):
        result, events = self.run_case(resource={"BP_RESOURCE_MOCK_DELAY": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        parent = next(pid for name, pid, _ in events if name == "r29_control")
        # Split on the real parent's four-call resource snapshots per cell.
        start = [n for n, (name, pid, value) in enumerate(events) if name == "usage" and value % 4 == 1]
        for index, begin in enumerate(start):
            end = next(n for n in range(begin + 1, len(events)) if events[n][0] == "usage" and events[n][2] == 4*(index+1))
            cell = events[begin:end + 1]
            control = [n for n, e in enumerate(cell) if e[0] == "r29_control"]
            allocations = [n for n, e in enumerate(cell) if e[0] == "allocation"]
            frees = [n for n, e in enumerate(cell) if e[0] == "free"]
            wait = [n for n, e in enumerate(cell) if e[0] == "wait" and e[1] == parent]
            self.assertEqual(len(control), 2)
            self.assertLess(control[0], min(allocations))
            self.assertGreater(control[-1], max(frees + wait))
            self.assertFalse(any(e[0] == "report" for e in cell))

    def test_primary_workloads_and_larger_corpus_have_checks_and_plain_or_legs(self):
        for work in ("scan", "lookup", "parse", "chase"):
            for size in (32, 128):
                with self.subTest(work=work, size=size):
                    result, _ = self.run_case(workload=work, kib=size, profile="legs")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.count("_LEGS "), 4)

    def test_single_lane_control_accepts_missing_opposite_lane(self):
        for policy, fault in (("ordinary-i", "no-d"), ("ordinary-d", "no-i"),
                              ("advisory-i", "no-d"), ("advisory-d", "no-i")):
            result, _ = self.run_case(policy=policy, fault=fault)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_rusage_coarse_nonnegative_process_totals(self):
        result, events = self.run_case(resource={"R29_REAL_USAGE": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(name == "actual_usage" for name, _, _ in events), 16)
        fields = [dict((key, int(value)) for key, value in re.findall(r"(\w+)=(\d+)", row))
                  for row in re.findall(r"_RESOURCE .*", result.stdout)]
        self.assertEqual(len(fields), 4)
        self.assertTrue(all(row["minor_faults"] > 0 for row in fields))
        self.assertTrue(all(row[name] >= 0 for row in fields for name in EXPECTED))

    def test_capability_geometry_and_missing_lane_fail_before_allocation(self):
        for fault in ("absent", "truncated", "reserved", "initial-active", "no-i", "no-d"):
            with self.subTest(fault=fault):
                result, events = self.run_case(fault=fault)
                self.fail_closed(result)
                self.assertFalse(any(n == "allocation" for n, _, _ in events))
                self.assertFalse(any(n == "r29_control" for n, _, _ in events))

    def test_mode_poll_errors_fail_before_allocation_and_reset(self):
        for fault in ("busy", "wrong-readback", "geometry-drift", "control-failure"):
            with self.subTest(fault=fault):
                result, events = self.run_case(fault=fault)
                self.fail_closed(result)
                # First off cell may pass; no enabled cell may allocate after
                # its deliberately broken enable/control acknowledgement.
                nonzero = [n for n, e in enumerate(events) if e[0] == "r29_control" and e[2]]
                if nonzero:
                    self.assertFalse(any(e[0] == "allocation" for e in events[nonzero[0] + 1:]))
                if fault in ("busy", "geometry-drift"):
                    self.assertIn("cleanup/reset", result.stderr)
                    self.assertEqual([v for n, _, v in events if n == "r29_control"][-1], 0)
                    self.assertLess(sum(n == "r29_status" for n, _, _ in events), 2*4096+20)
                else:
                    self.assertEqual([v for n, _, v in events if n == "final_mode"], [0])

    def test_child_parent_failure_cleanup_and_resource_failure_never_pass(self):
        for fault in ("child-allocation", "parent-allocation", "prefix-activity", "prefix-busy", "prefix-saturated",
                      "replay-activity", "replay-busy", "replay-saturated", "bad-reset"):
            with self.subTest(fault=fault):
                result, events = self.run_case(fault=fault)
                self.fail_closed(result)
                if fault == "prefix-busy":
                    self.assertIn("cleanup/reset", result.stderr)
                    self.assertEqual([v for n, _, v in events if n == "r29_control"][-1], 0)
                    self.assertLessEqual(sum(n == "prefix" for n, _, _ in events), 2*4096)
                elif fault == "replay-busy":
                    self.assertIn("cleanup/reset", result.stderr)
                    self.assertEqual([v for n, _, v in events if n == "r29_control"][-1], 0)
                    self.assertLessEqual(sum(n == "replay" for n, _, _ in events), 2*4096)
                elif fault != "bad-reset":
                    self.assertEqual([v for n, _, v in events if n == "final_mode"], [0])
        for resource in ({"BP_RESOURCE_MOCK_FAILURE_CALL": "3"}, {"BP_RESOURCE_MOCK_FAULT": "negative-counter"}):
            result, events = self.run_case(resource=resource)
            self.fail_closed(result)
            self.assertEqual([v for n, _, v in events if n == "final_mode"], [0])

    def test_invalid_cli_legacy_names_and_advisory_source_are_rejected(self):
        for args in (["3", "2", "retention-rr"], ["3", "2", "retention-first"],
                     ["3", "2", "continuous"], ["-1"],
                     ["3", "2", "ordinary-joint", "2", "pipe", "legs"],
                     ["3", "2", "ordinary-joint", "2", "futex", "plain", "32", "deflate"],
                     ["3", "2", "advisory-joint", "2", "futex", "plain", "32", "scan", "mode14"]):
            result, events = self.run_case(arguments=args)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(any(n in ("r29_control", "allocation") for n, _, _ in events))

    def test_resource_helpers_are_exact_maintained_implementation(self):
        old = (HERE / "scheduler_pipe_hint_benchmark.c").read_text()
        new = (HERE / "scheduler_retained29_benchmark.c").read_text()
        helpers = "struct cell_resources {" + old.split("struct cell_resources {", 1)[1].split("\n#endif\n\nstatic uint64_t cycle", 1)[0]
        self.assertIn(helpers, new)

    def test_inherited_full_width_completed_reply_is_drained_before_cells(self):
        result, events = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        first_control = next(n for n, e in enumerate(events) if e[0] == "r29_control")
        reads = [value for name, _, value in events[:first_control] if name == "replay"]
        self.assertTrue(reads[0] < 0 and reads[1] < 0)
        self.assertTrue(reads[2] >= 0)
        self.assertEqual(result.stdout.count("_REPLAY "), 4)

    def test_auxiliary_source_failure_cannot_skip_global_reset_attempt(self):
        result, events = self.run_case(fault="source-off")
        self.fail_closed(result)
        self.assertIn("cleanup/reset", result.stderr)
        self.assertIn("Input/output error", result.stderr)
        controls = [value for name, _, value in events if name == "r29_control"]
        self.assertEqual(controls, [0, 0, 15, 0])
        self.assertEqual([value for name, _, value in events if name == "r29_status"][-1], 0)


if __name__ == "__main__": unittest.main()
