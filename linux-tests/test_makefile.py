#!/usr/bin/env python3
"""Verify Linux ELF freshness and transfer integrity without a cross toolchain.

The real Makefile runs against fake compilers and exclusively temporary outputs;
these checks never build a kernel or touch the SDK root filesystem.
"""

import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
APPS = {"app": "ctxtsw_user_smoke", "tiny": "ctxtsw_user_tiny",
        "shell-app": "ctxtsw_user_shell", "benchmark": "ctxtsw_user_benchmark"}
FAKE_COMPILER = """#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
output = pathlib.Path(args[args.index('-o') + 1])
output.write_bytes(json.dumps({'compiler': pathlib.Path(sys.argv[0]).name,
                             'args': args}).encode())
print('compiler diagnostic on stdout')
if os.environ.get('FAIL_COMPILER'):
    output.write_bytes(b'partial failed ELF')
    sys.exit(1)
"""


class LinuxHarnessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.out = self.base / "out"
        self.env = os.environ.copy()
        for key in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES", "FAIL_COMPILER"):
            self.env.pop(key, None)
        for name in ("first-gcc", "second-gcc"):
            compiler = self.base / name
            compiler.write_text(FAKE_COMPILER)
            compiler.chmod(0o755)
        for name in ("strip", "objcopy"):
            tool = self.base / name
            tool.write_text("#!/bin/sh\nexit 0\n")
            tool.chmod(0o755)

    def make(self, target, *options, compiler="first-gcc", fail=False):
        env = self.env.copy()
        if fail:
            env["FAIL_COMPILER"] = "1"
        return subprocess.run(
            ["make", "--no-print-directory", "-C", str(HERE), target,
             "OUT=" + str(self.out), "BP_LINUX_CC=" + str(self.base / compiler),
             "BP_LINUX_PREFIX=" + str(self.base) + "/", *options],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

    def read_app(self, target):
        return json.loads((self.out / APPS[target]).read_bytes())

    def test_target_syscall_round_trip(self):
        for target in ("tiny", "shell-app"):
            for flag in (1, 0, 1):
                with self.subTest(target=target, flag=flag):
                    result = self.make(target, "TINY_TARGET_SYSCALL=" + str(flag))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("-DBP_TARGET_SYSCALL=" + str(flag),
                                  self.read_app(target)["args"])

    def test_cflags_round_trip(self):
        for flag in ("-O0", "-O2", "-O0"):
            result = self.make("app", "CFLAGS=" + flag)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.read_app("app")["args"][0], flag)

    def test_compiler_change_for_every_app(self):
        for target in APPS:
            for compiler in ("first-gcc", "second-gcc", "first-gcc"):
                with self.subTest(target=target, compiler=compiler):
                    result = self.make(target, compiler=compiler)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.read_app(target)["compiler"], compiler)

    def test_transfer_is_only_shell_commands_and_current_base64(self):
        for target, app in (("emit-shell-transfer", "ctxtsw_user_shell"),
                            ("emit-tiny-transfer", "ctxtsw_user_shell"),
                            ("emit-benchmark-transfer", "ctxtsw_user_benchmark")):
            for flag in (1, 0, 1):
                with self.subTest(target=target, flag=flag):
                    result = self.make(target, "TINY_TARGET_SYSCALL=" + str(flag))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(b"compiler diagnostic on stdout", result.stderr)
                    lines = result.stdout.decode().splitlines()
                    b64_path, app_path = "/tmp/" + app + ".b64", "/tmp/" + app
                    self.assertEqual(lines[0], ": > " + b64_path)
                    self.assertEqual(lines[-2:], [
                        "base64 -d " + b64_path + " > " + app_path,
                        "chmod +x " + app_path])
                    payload = []
                    for line in lines[1:-2]:
                        match = re.fullmatch(r"echo '([A-Za-z0-9+/=]+)' >> "
                                             + re.escape(b64_path), line)
                        self.assertIsNotNone(match, line)
                        payload.append(match[1])
                    self.assertEqual(base64.b64decode("".join(payload), validate=True),
                                     (self.out / app).read_bytes())

    def test_failed_rebuild_never_emits_stale_transfer(self):
        for target, app in (("emit-shell-transfer", "ctxtsw_user_shell"),
                            ("emit-benchmark-transfer", "ctxtsw_user_benchmark")):
            with self.subTest(target=target):
                good = self.make(target)
                self.assertEqual(good.returncode, 0, good.stderr)
                failed = self.make(target, fail=True)
                self.assertNotEqual(failed.returncode, 0)
                self.assertEqual(failed.stdout, b"")
                self.assertFalse((self.out / app).exists(), "partial ELF must be deleted")


if __name__ == "__main__":
    unittest.main()
