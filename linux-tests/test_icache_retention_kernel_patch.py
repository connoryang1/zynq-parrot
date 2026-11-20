"""Apply and reverse the retention ABI against copied actual Linux sources.

These tests never modify the SDK, compile a kernel, or access a board. They
validate real patch upgrade/idempotence and public constants; CSR trap behavior
still needs an RV64 kernel build and old-hardware execution gate.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PATCH = HERE / "kernel-patches/0027-blackparrot-icache-retention-control.patch"
EARLY_ONLY = HERE / "kernel-patches/0028-blackparrot-mode14-early-only.patch"
PREVIOUS = HERE / "kernel-patches/0026-blackparrot-early-futex-instruction-replay.patch"
DEFAULT_SOURCE = Path("/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/build/linux-6.6")
FILES = ("kernel/sys.c", "include/uapi/linux/prctl.h", "kernel/futex/syscalls.c", "kernel/sched/core.c")


class IcacheRetentionKernelPatchTests(unittest.TestCase):
    def setUp(self):
        source = Path(os.environ.get("BP_RETENTION_KERNEL_SOURCE", str(DEFAULT_SOURCE)))
        if any(not (source / name).is_file() for name in FILES):
            self.skipTest("actual Linux 6.6 source fixture unavailable; set BP_RETENTION_KERNEL_SOURCE")
        self.source = source
        self.original_source = {name: (source / name).read_bytes() for name in FILES}
        self.temp = tempfile.TemporaryDirectory(prefix="linux-retention-patch-")
        self.addCleanup(self.temp.cleanup)
        self.tree = Path(self.temp.name)
        for name in FILES:
            target = self.tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
        # The shared source retains an orphan pipe mode outside this branch.
        # Remove it only in our copied fixture to bind the accepted 0026 tail.
        sys_c = self.tree / "kernel/sys.c"
        sys_c.write_text(sys_c.read_text().replace(
            "if (arg2 > 15 || arg3 || arg4 || arg5)",
            "if (arg2 > 14 || arg3 || arg4 || arg5)").replace(
            "arg2 && arg2 != 14 && arg2 != 15", "arg2 && arg2 != 14"))
        header = self.tree / "include/uapi/linux/prctl.h"
        header.write_text(header.read_text().replace(
            " * 14 instruction replay at futex-wake entry;\n * 15 instruction replay at pipe-write entry. */",
            " * 14 instruction replay at futex-wake entry. */"))
        self.baseline = self.snapshot()
        previous = self.patch(PREVIOUS, reverse=True, dry_run=True)
        self.assertEqual(previous.returncode, 0, previous.stdout + previous.stderr)

    def tearDown(self):
        if hasattr(self, "original_source"):
            self.assertEqual({name: (self.source / name).read_bytes() for name in FILES},
                             self.original_source, "test modified a canonical source")

    def snapshot(self):
        return {name: (self.tree / name).read_bytes() for name in FILES}

    def patch(self, path=PATCH, reverse=False, dry_run=False, content=None):
        command = ["patch", "--batch", "--fuzz=0", "-p1", "-d", str(self.tree),
                   "--reverse" if reverse else "--forward"]
        if dry_run:
            command.append("--dry-run")
        return subprocess.run(command, input=path.read_text() if content is None else content,
                              text=True, capture_output=True, timeout=10)

    def stage(self):
        env = os.environ.copy()
        for name in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES"):
            env.pop(name, None)
        return subprocess.run(["make", "--no-print-directory", "-C", str(HERE),
                               "stage-linux-data-preview", "LINUX_BUILD_DIR=" + str(self.tree)],
                              env=env, text=True, capture_output=True, timeout=20)

    def test_actual_source_forward_reverse_roundtrip(self):
        for reverse in (False, True, False):
            probe = self.patch(reverse=reverse, dry_run=True)
            self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
            result = self.patch(reverse=reverse)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if reverse:
                self.assertEqual(self.snapshot(), self.baseline)
        self.assertNotEqual(self.snapshot(), self.baseline)
        self.assertEqual(self.patch(reverse=True).returncode, 0)
        self.assertEqual(self.snapshot(), self.baseline)

    def test_actual_stage_upgrades_0026_once_and_is_idempotent(self):
        result = self.stage()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        accepted = self.snapshot()
        result = self.stage()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("stack already applied", result.stdout)
        self.assertEqual(self.snapshot(), accepted)
        self.assertEqual(self.patch(EARLY_ONLY, reverse=True).returncode, 0)
        self.assertEqual(self.patch(reverse=True).returncode, 0)
        self.assertEqual(self.snapshot(), self.baseline)

    def test_stage_upgrades_complete_0027_without_partial_false_positive(self):
        self.assertEqual(self.patch().returncode, 0)
        retention = self.snapshot()
        result = self.stage()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.patch(EARLY_ONLY, reverse=True).returncode, 0)
        self.assertEqual(self.snapshot(), retention)

    def test_0028_actual_source_roundtrip_and_all_mode_predicates(self):
        core = self.tree / "kernel/sched/core.c"

        def selection_modes():
            text = core.read_text().split("if (bp_preview_mode &&", 1)[1]
            predicate = "bp_preview_mode &&" + text.split(") {", 1)[0]
            source = ('#include <stdio.h>\nint main(void) {\n'
                      'for (unsigned bp_preview_mode=0; bp_preview_mode<256; ++bp_preview_mode)\n'
                      'if (' + predicate + ') printf("%u\\n", bp_preview_mode);\nreturn 0; }\n')
            binary = self.tree / "predicate"
            compiled = subprocess.run([os.environ.get("BP_HOST_CC", "cc"), "-x", "c", "-",
                                       "-o", str(binary)], input=source, text=True,
                                      capture_output=True, timeout=10)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            return set(map(int, subprocess.check_output([str(binary)], text=True).split()))

        old = selection_modes()
        self.assertEqual(old, {2, 3, 5} | set(range(14, 256)))
        self.assertEqual(self.patch(EARLY_ONLY, dry_run=True).returncode, 0)
        self.assertEqual(self.patch(EARLY_ONLY).returncode, 0)
        self.assertEqual(selection_modes(), old - {14})
        self.assertEqual(self.patch(EARLY_ONLY, reverse=True, dry_run=True).returncode, 0)
        self.assertEqual(self.patch(EARLY_ONLY, reverse=True).returncode, 0)
        self.assertEqual(self.snapshot(), self.baseline)

    def test_stage_rejects_0028_without_0027_and_preserves_sources(self):
        self.assertEqual(self.patch(EARLY_ONLY).returncode, 0)
        partial = self.snapshot()
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mode-14 tail present without complete", result.stderr)
        self.assertEqual(self.snapshot(), partial)

    def test_stage_rejects_a_partial_zero_context_tail_without_duplication(self):
        header_only = PATCH.read_text().split("--- a/kernel/sys.c", 1)[0]
        result = self.patch(content=header_only)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        partial = self.snapshot()
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("partial I-retention patch", result.stderr)
        self.assertEqual(self.snapshot(), partial)

    def test_patched_public_header_exposes_distinct_retention_commands(self):
        result = self.patch()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        macros = subprocess.run([os.environ.get("BP_HOST_CC", "cc"), "-E", "-dM", "-x", "c",
                                 "-I", str(self.tree / "include/uapi"),
                                 "-include", "linux/prctl.h", "-"],
                                input="", text=True, capture_output=True, timeout=10)
        self.assertEqual(macros.returncode, 0, macros.stderr)
        values = dict(line.split(maxsplit=2)[1:] for line in macros.stdout.splitlines()
                      if line.startswith("#define PR_BP_ICACHE_RETENTION_"))
        self.assertEqual(int(values["PR_BP_ICACHE_RETENTION_CONTROL"], 0), 0x42505061)
        self.assertEqual(int(values["PR_BP_ICACHE_RETENTION_STATUS"], 0), 0x42505062)


if __name__ == "__main__":
    unittest.main()
