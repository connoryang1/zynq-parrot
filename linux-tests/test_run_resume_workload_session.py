"""Verify the whole-session reservation without contacting any board.

Every command and benchmark run is mocked. Real local flock operations prove
that staging, recovery, test launch, and failure cleanup share one held inode.
"""
import base64
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest import mock

import run_resume_workload_session as session
from run_scheduler_pipe_hint import GUEST_ELF


class ResumeWorkloadSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="resume-session-lock-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock = self.root / "session.lock"
        self.lock.write_text("coordinator-created inode\n")
        self.inode = self.lock.stat().st_ino
        self.original_lock_bytes = self.lock.read_bytes()
        self.output = self.root / "results"
        self.nbf = self.root / "test.nbf"
        self.nbf.write_text("verified-by-guest-runner fixture\n")
        self.package = self.root / "package.tar.xz.b64"
        self.package.write_text("staging is mocked\n")
        self.transfer = self.root / "guest.transfer"
        payload = b"host-only ELF validation fixture"
        self.elf_sha = hashlib.sha256(payload).hexdigest()
        encoded = base64.b64encode(payload).decode()
        self.transfer.write_text(
            f": > {GUEST_ELF}.b64\n"
            f"echo '{encoded}' >> {GUEST_ELF}.b64\n"
            f"base64 -d {GUEST_ELF}.b64 > {GUEST_ELF}\n"
            f"chmod +x {GUEST_ELF}\n")
        self.argv = [str(self.nbf), str(self.transfer), self.elf_sha,
                     str(self.package), str(self.output),
                     "--bitstream-sha256", "b" * 64,
                     "--cell", "lookup:32:futex-early",
                     "--cell", "parse:256:preseed",
                     "--loops", "3", "--warmup", "2", "--repeats", "2",
                     "--all-three-acknowledged"]
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(session, "SESSION_LOCK", self.lock).start()
        mock.patch.dict(session.os.environ,
                        {"PYNQ_POWER_STATE_URL": "http://example.invalid/controller"}).start()
        self.events = []
        self.command = mock.patch.object(session.subprocess, "run",
                                         side_effect=self.command_held).start()
        self.run_guest = mock.patch.object(session, "run", side_effect=self.guest_held).start()
        original_recover = session.recover

        def recovery(host, env):
            self.assert_held()
            self.events.append("recover")
            original_recover(host, env)

        self.recovery = mock.patch.object(session, "recover", side_effect=recovery).start()
        self.handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}

    def assert_held(self):
        self.assertEqual(self.lock.stat().st_ino, self.inode)
        with self.lock.open("r") as competitor:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def assert_released_unchanged(self):
        self.assertEqual(self.lock.stat().st_ino, self.inode)
        self.assertEqual(self.lock.read_bytes(), self.original_lock_bytes)
        with self.lock.open("r") as competitor:
            fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(competitor, fcntl.LOCK_UN)
        for sig, expected in self.handlers.items():
            self.assertEqual(signal.getsignal(sig), expected)

    def command_held(self, command, **kwargs):
        self.assert_held()
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["env"]["PYNQ_POWER_OFF_SECONDS"], "15")
        self.events.append(Path(command[0]).name)
        return mock.Mock(returncode=0)

    def guest_held(self, args):
        self.assert_held()
        self.assertTrue(args.log.parent.is_dir())
        self.events.append("run:" + args.workload)

    def test_busy_lock_runs_nothing_and_creates_no_output(self):
        with self.lock.open("r") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                session.main(self.argv)
            self.assertFalse(self.output.exists())
            self.command.assert_not_called()
            self.run_guest.assert_not_called()
            self.recovery.assert_not_called()
            fcntl.flock(owner, fcntl.LOCK_UN)
        self.assert_released_unchanged()

    def test_success_holds_one_inode_over_full_stage_recover_run_order(self):
        self.assertEqual(session.main(self.argv), 0)
        self.assertEqual(self.events, [
            "stage_pynq_artifacts.sh",
            "recover", "power_cycle_pynq.sh", "wait_pynq_ready.sh", "load_pynq_overlay.sh", "run:lookup",
            "recover", "power_cycle_pynq.sh", "wait_pynq_ready.sh", "load_pynq_overlay.sh", "run:parse",
        ])
        status = json.loads((self.output / "session.json").read_text())
        self.assertEqual(status["state"], "complete")
        self.assertTrue(status["all_three_acknowledged"])
        self.assertIn("released_utc", status)
        self.assertEqual([item["workload"] for item in status["plan"]], ["lookup", "parse"])
        self.assert_released_unchanged()

    def test_guest_failure_recovers_before_releasing_original_inode(self):
        def failed(args):
            self.guest_held(args)
            raise RuntimeError("injected guest failure")
        self.run_guest.side_effect = failed
        with self.assertRaisesRegex(RuntimeError, "injected guest failure"):
            session.main(self.argv)
        self.assertEqual(self.events[-4:], ["recover", "power_cycle_pynq.sh",
                                            "wait_pynq_ready.sh", "load_pynq_overlay.sh"])
        self.assertNotIn("run:parse", self.events)
        status = json.loads((self.output / "session.json").read_text())
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["recovery"], "complete before reservation release")
        self.assert_released_unchanged()

    def test_recovery_failure_still_releases_lock_and_preserves_original_error(self):
        self.run_guest.side_effect = RuntimeError("original guest failure")
        calls = 0

        def recovery(host, env):
            nonlocal calls
            self.assert_held()
            calls += 1
            if calls == 2:
                raise RuntimeError("cleanup recovery failed")

        self.recovery.side_effect = recovery
        with self.assertRaisesRegex(RuntimeError, "original guest failure"):
            session.main(self.argv)
        status = json.loads((self.output / "session.json").read_text())
        self.assertIn("cleanup recovery failed", status["recovery"])
        self.assert_released_unchanged()

    def test_invalid_transfer_never_stages_recovers_or_launches(self):
        self.transfer.write_text("unexpected shell command\n")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            session.main(self.argv)
        self.command.assert_not_called()
        self.run_guest.assert_not_called()
        self.recovery.assert_not_called()
        self.assert_released_unchanged()

    def test_absent_lock_is_not_created(self):
        missing = self.root / "missing.lock"
        with mock.patch.object(session, "SESSION_LOCK", missing):
            with self.assertRaises(FileNotFoundError):
                session.main(self.argv)
        self.assertFalse(missing.exists())
        self.assertFalse(self.output.exists())
        self.command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
