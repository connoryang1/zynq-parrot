"""Test fail-closed planning for the tagged replay board runner."""

import tempfile
import unittest
from pathlib import Path

import run_scheduler_tagged_replay as runner


class TaggedReplayRunnerTest(unittest.TestCase):
    def test_command_binds_all_experiment_parameters(self):
        self.assertEqual(
            runner.benchmark_command("joint", 123, 4, "fifo", 900),
            "/tmp/scheduler_tagged_replay_benchmark_dynamic joint 123 4 fifo 900; "
            "rc=$?; echo TAGGED_REPLAY_EXIT rc=$rc",
        )

    def test_delay_range_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nbf = root / "image.nbf"
            transfer = root / "transfer"
            log = root / "run.log"
            nbf.write_text("nbf")
            transfer.write_text("true\n")
            args = runner.parse_args([
                str(nbf), str(transfer), "0" * 64, str(log),
                "--delay", "65536",
            ])
            with self.assertRaisesRegex(ValueError, "delay"):
                runner.validate_args(args)

    def test_transfer_line_limit_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nbf = root / "image.nbf"
            transfer = root / "transfer"
            log = root / "run.log"
            nbf.write_text("nbf")
            transfer.write_text("x" * (runner.MAX_GUEST_COMMAND_LENGTH + 1))
            args = runner.parse_args([
                str(nbf), str(transfer), "0" * 64, str(log),
            ])
            with self.assertRaisesRegex(ValueError, "transfer command"):
                runner.validate_args(args)


if __name__ == "__main__":
    unittest.main()
