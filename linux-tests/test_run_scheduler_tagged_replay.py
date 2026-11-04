"""Test fail-closed planning for the tagged replay board runner."""

import tempfile
import unittest
from pathlib import Path

import run_scheduler_tagged_replay as runner


class TaggedReplayRunnerTest(unittest.TestCase):
    @staticmethod
    def valid_transfer(payload=b"ELF"):
        import base64
        encoded = base64.b64encode(payload).decode()
        guest = runner.GUEST_ELF
        return (
            f": > {guest}.b64\n"
            f"echo '{encoded}' >> {guest}.b64\n"
            f"base64 -d {guest}.b64 > {guest}\n"
            f"chmod +x {guest}\n"
        )

    def test_command_binds_all_experiment_parameters(self):
        self.assertEqual(
            runner.benchmark_command("joint", 123, 4, "fifo", 900),
            "/tmp/scheduler_tagged_replay_benchmark_dynamic joint 123 4 fifo 900 8 0 aligned pipe; "
            "rc=$?; echo TAGGED_REPLAY_EXIT rc=$rc",
        )

    def test_command_binds_skew_layout(self):
        self.assertIn(
            " 8 1 skew pipe; ",
            runner.benchmark_command(
                "data", 0, 0, "normal", 0, 8, True, "skew"
            ),
        )

    def test_command_binds_late_data_mode(self):
        self.assertIn(
            " data-late 0 0 normal 0 8 0 aligned pipe; ",
            runner.benchmark_command("data-late", 0, 0, "normal", 0),
        )

    def test_command_binds_futex_sync(self):
        self.assertIn(
            " 8 0 skew futex; ",
            runner.benchmark_command(
                "data", 0, 0, "normal", 0, 8, False, "skew", "futex"
            ),
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

    def test_transfer_rejects_make_directory_chatter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nbf = root / "image.nbf"
            transfer = root / "transfer"
            log = root / "run.log"
            nbf.write_text("nbf")
            transfer.write_text("make: Entering directory '/tmp'\n"
                                + self.valid_transfer())
            args = runner.parse_args([
                str(nbf), str(transfer), "0" * 64, str(log),
            ])
            with self.assertRaisesRegex(ValueError, "unexpected shell commands"):
                runner.validate_args(args)

    def test_transfer_payload_hash_is_bound_before_board_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nbf = root / "image.nbf"
            transfer = root / "transfer"
            log = root / "run.log"
            nbf.write_text("nbf")
            transfer.write_text(self.valid_transfer())
            args = runner.parse_args([
                str(nbf), str(transfer), "0" * 64, str(log),
            ])
            with self.assertRaisesRegex(ValueError, "does not match ELF"):
                runner.validate_args(args)

    def test_lines_per_base_range_is_fail_closed(self):
        args = runner.parse_args([
            "missing.nbf", "missing.transfer", "0" * 64, "missing.log",
            "--lines-per-base", "0",
        ])
        with self.assertRaisesRegex(ValueError, "lines per base"):
            runner.validate_args(args)


if __name__ == "__main__":
    unittest.main()
