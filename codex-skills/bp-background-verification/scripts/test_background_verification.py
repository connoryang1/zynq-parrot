#!/usr/bin/env python3
"""Validate launcher isolation, layer selection, and detached command assembly.

The tests use a temporary Git repository and a fake tmux executable. They never
build Verilator, alter a real worktree, or launch a background worker.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).with_name("background_verification.sh")


class BackgroundVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bp-bg-verify ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo with spaces"
        self.repo.mkdir()
        self.env = os.environ.copy()
        self.env.update(
            GIT_AUTHOR_NAME="Background Test",
            GIT_COMMITTER_NAME="Background Test",
            GIT_AUTHOR_EMAIL="test@example.invalid",
            GIT_COMMITTER_EMAIL="test@example.invalid",
        )
        for key in (
            "ZP_BG_VERIFY_SOURCE_REPO",
            "ZP_BG_VERIFY_STATE_ROOT",
            "ZP_BG_VERIFY_LOG_ROOT",
            "ZP_BG_VERIFY_BUILD_JOBS",
            "ZP_BG_VERIFY_MIN_FREE_KB",
            "ZP_BG_VERIFY_TIMEOUT_S",
            "TMUX",
        ):
            self.env.pop(key, None)
        self.run_command(["git", "init", "-q", str(self.repo)])
        launcher_dir = self.repo / "skill" / "scripts"
        launcher_dir.mkdir(parents=True)
        self.launcher = launcher_dir / "background_verification.sh"
        shutil.copy2(SOURCE, self.launcher)
        self.launcher.chmod(0o755)
        install_bin = self.repo / "install" / "bin"
        install_bin.mkdir(parents=True)
        compiler = install_bin / "riscv64-unknown-elf-gcc"
        compiler.write_text("#!/bin/sh\nexit 0\n")
        compiler.chmod(0o755)
        self.run_command(["git", "-C", str(self.repo), "add", "."])
        self.run_command(["git", "-C", str(self.repo), "commit", "-q", "-m", "fixture"])
        self.commit = self.run_command(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"]
        ).stdout.strip()

        self.state = self.base / "state with spaces"
        self.logs = self.base / "logs with spaces"
        self.capture = self.base / "tmux.json"
        fake_bin = self.base / "fake-bin"
        fake_bin.mkdir()
        fake_tmux = fake_bin / "tmux"
        fake_tmux.write_text(
            "#!" + sys.executable + "\n"
            "import json,os,pathlib,sys\n"
            "if sys.argv[1] == 'new-session':\n"
            " pathlib.Path(os.environ['TMUX_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
            "elif sys.argv[1] == 'display-message': print(os.getppid())\n"
            "elif sys.argv[1] == 'has-session': raise SystemExit(1)\n"
            "else: raise SystemExit('unexpected tmux invocation')\n"
        )
        fake_tmux.chmod(0o755)
        self.env.update(
            ZP_BG_VERIFY_SOURCE_REPO=str(self.repo),
            ZP_BG_VERIFY_STATE_ROOT=str(self.state),
            ZP_BG_VERIFY_LOG_ROOT=str(self.logs),
            ZP_BG_VERIFY_BUILD_JOBS="1",
            ZP_BG_VERIFY_MIN_FREE_KB="1",
            ZP_BG_VERIFY_TIMEOUT_S="17",
            TMUX_CAPTURE=str(self.capture),
            PATH=str(fake_bin) + os.pathsep + self.env["PATH"],
        )

    def run_command(self, command, check=True):
        return subprocess.run(
            command,
            env=self.env,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )

    def test_plan_is_deterministic_and_contains_exact_topology(self):
        result = self.run_command([str(self.launcher), "plan", "full"])
        self.assertEqual(result.stdout.splitlines()[0], "host check-harness")
        self.assertIn("2/4 mt_protected_rpc_hardware_test", result.stdout)
        self.assertIn("2/10 mt_protected_rpc_hardware_test", result.stdout)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.logs.exists())

    def test_unknown_layer_is_rejected(self):
        result = self.run_command(
            [str(self.launcher), "plan", "everything"], check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown verification layer", result.stderr)

    def test_dirty_checkout_is_rejected(self):
        tracked = self.repo / "tracked.txt"
        tracked.write_text("initial\n")
        self.run_command(["git", "-C", str(self.repo), "add", "tracked.txt"])
        self.run_command(
            ["git", "-C", str(self.repo), "commit", "-q", "-m", "tracked"]
        )
        tracked.write_text("dirty\n")
        result = self.run_command(
            [str(self.launcher), "start", "smoke"], check=False
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("uncommitted checkout", result.stderr)
        self.assertFalse(self.capture.exists())

    def test_start_returns_after_assembling_isolated_worker(self):
        result = self.run_command([str(self.launcher), "start", "targeted"])
        self.assertIn("layer=targeted", result.stdout)
        self.assertIn(f"revision={self.commit}", result.stdout)
        captured = json.loads(self.capture.read_text())
        self.assertEqual(captured[:3], ["new-session", "-d", "-s"])
        command = captured[-1]
        self.assertIn("nice -n 15", command)
        self.assertIn("worker", command)
        self.assertIn("targeted", command)
        self.assertIn(str(self.state), command)
        self.assertIn("ZP_BG_VERIFY_TIMEOUT_S=17", command)
        job_dir, = self.logs.iterdir()
        self.assertEqual((job_dir / "status").read_text(), "QUEUED\n")

    def test_failed_worker_retains_a_failure_summary(self):
        job_dir = self.logs / "forced-failure"
        job_dir.mkdir(parents=True)
        result = self.run_command(
            [
                str(self.launcher),
                "worker",
                "forced-failure",
                "smoke",
                self.commit,
            ],
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((job_dir / "status").read_text(), "FAIL\n")
        summary = (job_dir / "summary.txt").read_text()
        self.assertIn("verdict=FAIL", summary)
        self.assertIn("exit_code", summary)
        self.assertIn("topology", summary)


if __name__ == "__main__":
    unittest.main()
