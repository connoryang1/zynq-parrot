"""Apply 0029 to copied Linux sources and execute its actual C decision branches.

Only CSR, privilege, preemption and copy primitives are mocked on the host.
Patch roundtrips cover 0027 alone and optional 0028 without modifying the SDK;
actual kernel compilation, exception handling and target execution remain gates.
"""
import errno
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from retained_control_test_support import HERE, PATCH, compile_fixture

SOURCE = Path("/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/build/linux-6.6")
PREVIOUS = HERE / "kernel-patches/0027-blackparrot-icache-retention-control.patch"
OPTIONAL = HERE / "kernel-patches/0028-blackparrot-mode14-early-only.patch"
FILES = ("kernel/sys.c", "include/uapi/linux/prctl.h", "kernel/sched/core.c")
CONTROL, STATUS = 0x42505063, 0x42505064
SENTINEL = 0x0123456789abcdef


class RetainedStoreKernelContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="retained-contract-", dir="/dev/shm")
        cls.binary = compile_fixture(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def call(self, option, a2=0, a3=0, a4=0, a5=0, ptr=False, **changes):
        env = {k: v for k, v in os.environ.items() if not k.startswith("MOCK_")}
        env.update({"MOCK_" + k: str(v) for k, v in changes.items()})
        result = subprocess.run([str(self.binary), *map(str, (option, a2, a3, a4, a5)),
                                 "ptr" if ptr else "raw"], env=env,
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out["depth"], 0)
        self.assertEqual(out["copy_depth"], 0)
        return out

    def test_all_controls_read_before_one_write_and_derive_lane_masks(self):
        for i, d in ((65, 1320), (0, 0), (0, 128), (512, 0)):
            for mask in range(16):
                with self.subTest(i=i, d=d, mask=mask):
                    got = self.call(CONTROL, mask, I_LINES=i, D_LINES=d)
                    expected = mask & ((9 if i else 0) | (6 if d else 0))
                    if not expected & 1:
                        expected &= ~8
                    if not expected & 2:
                        expected &= ~4
                    self.assertEqual((got["rc"], got["reads"], got["writes"], got["mode"]),
                                     (0, 1, 1, expected))

    def test_status_copies_all_64_bits_and_never_writes(self):
        got = self.call(STATUS, ptr=True, WRAP=0xc00)
        self.assertEqual(got["out"], (1 << 63) | (3 << 56) | (6 << 48) |
                         (1320 << 32) | (65 << 16) | 0xc00)
        self.assertEqual((got["rc"], got["reads"], got["writes"], got["copies"]), (0, 1, 0, 1))

    def test_absent_read_or_missing_capability_never_write_or_copy(self):
        for fault in ("ABSENT", "NO_CAP"):
            for option in (CONTROL, STATUS):
                got = self.call(option, 15 if option == CONTROL else 0,
                                ptr=option == STATUS, **{fault: 1})
                self.assertEqual(got["rc"], -errno.ENODEV)
                self.assertEqual((got["reads"], got["writes"], got["copies"]), (1, 0, 0))
                self.assertEqual(got["out"], SENTINEL)

    def test_invalid_arguments_precede_privilege_and_touch_no_hardware(self):
        invalid = [(CONTROL, 16, 0, 0, 0), (CONTROL, 2**64-1, 0, 0, 0),
                   (STATUS, 0, 0, 0, 0)]
        for n in range(3):
            args = [0, 0, 0]
            args[n] = 1
            invalid += [(CONTROL, 0, *args), (STATUS, 1, *args)]
        for call in invalid:
            for uid in (0, 65534):
                got = self.call(*call, UID=uid)
                self.assertEqual((got["rc"], got["reads"], got["writes"], got["copies"]),
                                 (-errno.EINVAL, 0, 0, 0))

    def test_privilege_then_single_cpu_precede_capability_read(self):
        for option in (CONTROL, STATUS):
            for uid, cpus, expected in ((65534, 1, errno.EPERM), (65534, 2, errno.EPERM),
                                         (0, 2, errno.EOPNOTSUPP)):
                got = self.call(option, 15 if option == CONTROL else 0,
                                ptr=option == STATUS, UID=uid, CPUS=cpus, ABSENT=1)
                self.assertEqual((got["rc"], got["reads"], got["writes"], got["copies"]),
                                 (-expected, 0, 0, 0))

    def test_faulting_usercopy_after_preempt_enable_and_absent_precedes_copy(self):
        got = self.call(STATUS, 1)
        self.assertEqual((got["rc"], got["reads"], got["copies"]), (-errno.EFAULT, 1, 1))
        got = self.call(STATUS, 1, ABSENT=1)
        self.assertEqual((got["rc"], got["reads"], got["copies"]), (-errno.ENODEV, 1, 0))


class RetainedStorePatchTests(unittest.TestCase):
    def setUp(self):
        self.source = Path(os.environ.get("BP_RETENTION_KERNEL_SOURCE", str(SOURCE)))
        if any(not (self.source / name).is_file() for name in FILES):
            self.skipTest("actual Linux source fixture unavailable")
        self.original = {name: (self.source / name).read_bytes() for name in FILES}
        self.tmp = tempfile.TemporaryDirectory(prefix="retained-patch-", dir="/dev/shm")
        self.addCleanup(self.tmp.cleanup)
        self.tree = Path(self.tmp.name)
        for name in FILES:
            path = self.tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.source / name, path)
        # Only this copied fixture removes the canonical orphan mode15.
        path = self.tree / "kernel/sys.c"
        path.write_text(path.read_text().replace("if (arg2 > 15 || arg3 || arg4 || arg5)",
                        "if (arg2 > 14 || arg3 || arg4 || arg5)").replace(
                        "arg2 && arg2 != 14 && arg2 != 15", "arg2 && arg2 != 14"))
        path = self.tree / "include/uapi/linux/prctl.h"
        path.write_text(path.read_text().replace(
            " * 14 instruction replay at futex-wake entry;\n * 15 instruction replay at pipe-write entry. */",
            " * 14 instruction replay at futex-wake entry. */"))
        self.baseline = self.snapshot()

    def tearDown(self):
        if hasattr(self, "original"):
            self.assertEqual({name: (self.source / name).read_bytes() for name in FILES}, self.original)

    def snapshot(self):
        return {name: (self.tree / name).read_bytes() for name in FILES}

    def patch(self, path=PATCH, reverse=False, dry=False):
        command = ["patch", "--batch", "--fuzz=0", "-p1", "-d", str(self.tree),
                   "--reverse" if reverse else "--forward"]
        if dry:
            command += ["--dry-run"]
        return subprocess.run(command, input=path.read_text(), text=True, capture_output=True, timeout=10)

    def apply(self, path=PATCH, reverse=False):
        got = self.patch(path, reverse)
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)

    def test_exact_roundtrip_after_0027_and_duplicate_refusal(self):
        self.apply(PREVIOUS)
        before = self.snapshot()
        accepted_sys = HERE.parent / "research/retention-kernel-20261120/accepted-rootfs/accepted-kernel_sys.c"
        self.assertEqual(before["kernel/sys.c"], accepted_sys.read_bytes(),
                         "0027 fixture differs from retained accepted kernel source")
        self.apply()
        after = self.snapshot()
        self.assertNotEqual(before, after)
        self.assertNotEqual(self.patch(dry=True).returncode, 0)
        self.assertEqual(self.snapshot(), after)
        self.apply(reverse=True)
        self.assertEqual(self.snapshot(), before)
        self.apply(PREVIOUS, reverse=True)
        self.assertEqual(self.snapshot(), self.baseline)

    def test_optional_0028_independence_and_old_helpers_unchanged(self):
        self.apply(PREVIOUS)
        before = self.snapshot()
        self.apply()
        first = self.snapshot()
        self.apply(OPTIONAL)
        both = self.snapshot()
        self.assertEqual(first["kernel/sys.c"], both["kernel/sys.c"])
        self.assertEqual(first["include/uapi/linux/prctl.h"], both["include/uapi/linux/prctl.h"])
        self.apply(reverse=True)
        self.apply(OPTIONAL, reverse=True)
        self.assertEqual(self.snapshot(), before)
        self.apply(OPTIONAL)
        self.apply()
        self.assertEqual(self.snapshot(), both)

    def test_missing_0027_fails_dry_run_without_mutation(self):
        result = self.patch(dry=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), self.baseline)

    def test_public_ids_unique_and_old_id_values_preserved(self):
        self.apply(PREVIOUS)
        self.apply()
        header = (self.tree / "include/uapi/linux/prctl.h").read_text()
        commands = re.findall(r"#define\s+(PR_BP_\w+)\s+(0x[0-9a-fA-F]+)", header)
        values = {name: int(value, 16) for name, value in commands}
        self.assertEqual(len(values), len(set(values.values())))
        self.assertEqual(values["PR_BP_ICACHE_RETENTION_CONTROL"], 0x42505061)
        self.assertEqual(values["PR_BP_ICACHE_RETENTION_STATUS"], 0x42505062)
        self.assertEqual(values["PR_BP_RETAINED_CONTROL"], CONTROL)
        self.assertEqual(values["PR_BP_RETAINED_STATUS"], STATUS)


if __name__ == "__main__":
    unittest.main()
