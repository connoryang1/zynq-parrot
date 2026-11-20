"""Exercise the ABI microprobe with wrapped syscalls and real host fork/wait.

The host mock models shared CPU policy and private credentials. These tests
never invoke retention hardware, change actual credentials, or access a board.
"""
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
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <unistd.h>
static unsigned *mode;
static uid_t uid;
static gid_t gid;
static int log_fd, present;
__attribute__((constructor)) static void setup(void)
{
    mode = mmap(NULL, sizeof(*mode), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (mode == MAP_FAILED) _exit(90);
    log_fd = open(getenv("PROBE_MOCK_LOG"), O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (log_fd < 0) _exit(91);
    present = !strcmp(getenv("PROBE_MOCK_CAP"), "present");
    if (getenv("PROBE_MOCK_NONROOT")) uid = 1001;
}
uid_t __wrap_geteuid(void) { return uid; }
gid_t __wrap_getegid(void) { return gid; }
int __wrap_setgid(gid_t value)
{
    if (uid) { errno = EPERM; return -1; }
    gid = value; return 0;
}
int __wrap_setuid(uid_t value)
{
    if (uid || getenv("PROBE_MOCK_DROP_FAIL")) { errno = EPERM; return -1; }
    uid = value; return 0;
}
int __wrap_prctl(int option, ...)
{
    va_list ap;
    unsigned long a[4];
    int error = 0;
    const char *op = option == 0x42505061 ? "control" : "status";
    va_start(ap, option);
    for (unsigned i = 0; i < 4; ++i) a[i] = va_arg(ap, unsigned long);
    va_end(ap);
    if ((option != 0x42505061 && option != 0x42505062) || a[1] || a[2] || a[3]
        || (option == 0x42505061 && a[0] > 2) || (option == 0x42505062 && !a[0]))
        error = EINVAL;
    else if (uid && !getenv("PROBE_MOCK_PRIV_BYPASS")) error = EPERM;
    else if (!present) error = getenv("PROBE_MOCK_BAD_ERRNO") ? EINVAL : ENODEV;
    else if (option == 0x42505061) {
        if (!(a[0] == 2 && getenv("PROBE_MOCK_IGNORE_MODE"))) *mode = a[0];
    } else {
        uint64_t raw = (UINT64_C(1) << 63) | 0x00110004 | *mode;
        if (getenv("PROBE_MOCK_TRUNCATE")) raw = (uint32_t)raw;
        *(uint64_t *)a[0] = raw;
    }
    if (error == ENODEV && option == 0x42505062 && getenv("PROBE_MOCK_DIRTY_SENTINEL"))
        *(uint64_t *)a[0] = 0;
    if (error == EPERM && getenv("PROBE_MOCK_DENIED_MUTATION")) *mode = 0;
    dprintf(log_fd, "pid=%ld uid=%lu op=%s arg=%lu error=%d state=%u\n",
            (long)getpid(), (unsigned long)uid, op, a[0], error, *mode);
    errno = error;
    return error ? -1 : 0;
}
'''


class IcacheRetentionProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="icache-retention-probe-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        mock = cls.root / "mock.c"
        mock.write_text(MOCK)
        cls.binary = cls.root / "probe"
        command = [os.environ.get("BP_HOST_CC", "cc"), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                   "-DBP_RETENTION_PROBE_HOST_VERIFY=1", str(HERE / "icache_retention_probe.c"), str(mock),
                   "-o", str(cls.binary)]
        for function in ("prctl", "geteuid", "getegid", "setuid", "setgid"):
            command.append("-Wl,--wrap=" + function)
        subprocess.run(command, check=True, capture_output=True, timeout=30)

    def run_probe(self, expected, capability=None, flags=None, extra=()):
        with tempfile.TemporaryDirectory(prefix="icache-probe-events-") as directory:
            log = Path(directory) / "events"
            env = os.environ.copy()
            env.update(flags or {})
            env.update(PROBE_MOCK_CAP=capability or expected, PROBE_MOCK_LOG=str(log))
            run = subprocess.run([str(self.binary), expected, *extra], text=True,
                                 capture_output=True, env=env, timeout=10)
            events = [dict(zip(("pid", "uid", "op", "arg", "error", "state"), match))
                      for match in re.findall(r"pid=(\d+) uid=(\d+) op=(control|status) "
                                              r"arg=(\d+) error=(\d+) state=(\d+)", log.read_text())]
            return run, events

    def test_absent_and_present_validate_privilege_and_return_alive(self):
        for capability in ("absent", "present"):
            with self.subTest(capability=capability):
                run, events = self.run_probe(capability)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(),
                                 "ICACHE_RETENTION_PROBE_HOST_VERIFY_PASS capability=" + capability)
                self.assertNotIn("ICACHE_RETENTION_PROBE_PASS", run.stdout)
                self.assertEqual(len({item["pid"] for item in events}), 2)
                child = [item for item in events if item["uid"] == "65534"]
                self.assertEqual(len(child), 4)
                self.assertTrue(all(int(item["error"]) == 1 for item in child))
                self.assertEqual([int(item["arg"]) for item in child if item["op"] == "control"], [0, 1, 2])
                self.assertEqual(events[-1]["state"], "0")
                root_valid = [item for item in events if item["uid"] == "0" and int(item["error"]) == 19]
                if capability == "absent":
                    self.assertEqual(len(root_valid), 5)
                else:
                    self.assertFalse(root_valid)

    def test_capability_mismatch_error_and_truncated_status_are_rejected(self):
        cases = [("present", "absent", {}), ("absent", "present", {}),
                 ("absent", "absent", {"PROBE_MOCK_BAD_ERRNO": "1"}),
                 ("absent", "absent", {"PROBE_MOCK_DIRTY_SENTINEL": "1"}),
                 ("present", "present", {"PROBE_MOCK_TRUNCATE": "1"}),
                 ("present", "present", {"PROBE_MOCK_IGNORE_MODE": "1"})]
        for expected, actual, flags in cases:
            with self.subTest(expected=expected, actual=actual, flags=flags):
                run, events = self.run_probe(expected, actual, flags)
                self.assertEqual(run.returncode, 1, run.stderr)
                self.assertIn("HOST_VERIFY_FAIL", run.stderr)
                self.assertNotIn("HOST_VERIFY_PASS", run.stdout)
                self.assertEqual(events[-1]["state"], "0")

    def test_failed_child_or_privilege_bypass_fails_parent_and_resets_policy(self):
        for flag in ("PROBE_MOCK_DROP_FAIL", "PROBE_MOCK_PRIV_BYPASS", "PROBE_MOCK_DENIED_MUTATION"):
            with self.subTest(flag=flag):
                run, events = self.run_probe("present", flags={flag: "1"})
                self.assertEqual(run.returncode, 1, run.stderr)
                self.assertNotIn("HOST_VERIFY_PASS", run.stdout)
                self.assertEqual(events[-1]["state"], "0")
                self.assertEqual(events[-1]["uid"], "0")

    def test_invalid_cli_and_nonroot_run_fail_before_any_prctl(self):
        for expected, flags, extra, code in (("unknown", {}, (), 2),
                                             ("present", {}, ("extra",), 2),
                                             ("present", {"PROBE_MOCK_NONROOT": "1"}, (), 1)):
            run, events = self.run_probe(expected, "present", flags, extra)
            self.assertEqual(run.returncode, code, run.stderr)
            self.assertFalse(events)
            self.assertNotIn("HOST_VERIFY_PASS", run.stdout)


if __name__ == "__main__":
    unittest.main()
