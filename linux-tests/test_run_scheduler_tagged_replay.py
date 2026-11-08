"""Test fail-closed planning for the tagged replay board runner."""

import contextlib
import hashlib
import io
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

    def test_timer_guard_marker_is_bound(self):
        self.assertEqual(runner.TIMER_GUARD_MARKER, "BP_REPLAY_TIMER_GUARD")

    def test_kernel_failure_markers_are_bound(self):
        for marker in ("BUG:", "Kernel panic", "Oops:", "Oops [#1]",
                       "scheduling while atomic", "Segmentation fault",
                       "scheduler_tagge[41]: unhandled signal 11 code 0x2",
                       "RT throttling activated", "sbi_trap_error:"):
            self.assertIsNotNone(runner.KERNEL_FAILURE_MARKER.search(marker))

    def test_transfer_timeout_defaults_to_three_minutes(self):
        args = runner.parse_args([
            "missing.nbf", "missing.transfer", "0" * 64, "missing.log",
        ])
        self.assertEqual(args.transfer_timeout_s, 180)

    def test_transfer_timeout_is_fail_closed(self):
        args = runner.parse_args([
            "missing.nbf", "missing.transfer", "0" * 64, "missing.log",
            "--transfer-timeout-s", "0",
        ])
        with self.assertRaisesRegex(ValueError, "transfer timeout"):
            runner.validate_args(args)

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

    def test_command_binds_prewake_data_mode(self):
        self.assertIn(
            " data-prewake 0 0 normal 0 8 0 skew futex; ",
            runner.benchmark_command(
                "data-prewake", 0, 0, "normal", 0, 8, False,
                "skew", "futex"
            ),
        )

    def test_command_binds_equalized_prewake_data_mode(self):
        self.assertIn(
            " data-prewake-equalized 0 0 normal 0 8 0 skew futex; ",
            runner.benchmark_command(
                "data-prewake-equalized", 0, 0, "normal", 0, 8, False,
                "skew", "futex",
            ),
        )

    def test_command_binds_unlimited_rt_policy(self):
        self.assertTrue(
            runner.benchmark_command(
                "data-prewake-equalized", 0, 0, "fifo", 0,
                rt_unlimited=True,
            ).startswith("BP_TAGGED_REPLAY_RT_UNLIMITED=1 ")
        )

    def test_unlimited_rt_policy_requires_fifo(self):
        args = runner.parse_args([
            "missing.nbf", "missing.transfer", "0" * 64, "missing.log",
            "--policy", "normal", "--rt-unlimited",
        ])
        with self.assertRaisesRegex(ValueError, "requires FIFO"):
            runner.validate_args(args)

    def test_command_binds_instruction_selection_mode(self):
        self.assertIn(
            " instruction-select 0 0 normal 0 8 0 aligned pipe; ",
            runner.benchmark_command(
                "instruction-select", 0, 0, "normal", 0
            ),
        )

    def test_command_binds_instruction_wakeup_mode(self):
        self.assertIn(
            " instruction-wake 0 0 normal 0 8 0 aligned pipe; ",
            runner.benchmark_command(
                "instruction-wake", 0, 0, "normal", 0
            ),
        )

    def test_command_binds_explicit_instruction_mode(self):
        self.assertIn(
            " instruction-explicit 0 0 normal 0 8 0 aligned pipe; ",
            runner.benchmark_command(
                "instruction-explicit", 0, 0, "normal", 0
            ),
        )

    def test_command_binds_explicit_roundtrip_instruction_mode(self):
        self.assertIn(
            " instruction-explicit-roundtrip 0 0 normal 0 8 0 aligned pipe; ",
            runner.benchmark_command(
                "instruction-explicit-roundtrip", 0, 0, "normal", 0
            ),
        )

    def test_command_binds_explicit_directional_instruction_mode(self):
        self.assertIn(
            " instruction-explicit-directed 0 0 normal 0 8 0 aligned pipe; ",
            runner.benchmark_command(
                "instruction-explicit-directed", 0, 0, "normal", 0
            ),
        )

    def test_command_binds_explicit_roundtrip_return_trace_arms(self):
        self.assertIn(
            " trace-icache-return-prefix; ",
            runner.benchmark_command(
                "instruction-explicit-roundtrip", 0, 0, "normal", 0,
                trace_icache_return_prefix=True,
            ),
        )
        self.assertIn(
            " trace-icache-return-prefix-off; ",
            runner.benchmark_command(
                "instruction-explicit-roundtrip", 0, 0, "normal", 0,
                trace_icache_return_prefix_off=True,
            ),
        )

    def test_command_binds_explicit_disabled_trace_arm(self):
        self.assertIn(
            " instruction-explicit 0 0 normal 0 8 0 aligned pipe "
            "trace-icache-entry-prefix-off; ",
            runner.benchmark_command(
                "instruction-explicit", 0, 0, "normal", 0,
                trace_icache_entry_prefix_off=True,
            ),
        )

    def test_command_binds_explicit_enabled_first_trace_arm(self):
        self.assertIn(
            " instruction-explicit 0 0 normal 0 8 0 aligned pipe "
            "trace-icache-entry-prefix-first; ",
            runner.benchmark_command(
                "instruction-explicit", 0, 0, "normal", 0,
                trace_icache_entry_prefix_first=True,
            ),
        )

    def test_disabled_trace_arm_is_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            runner.parse_args([
                "missing.nbf", "missing.transfer", "0" * 64, "missing.log",
                "--trace-icache-entry-prefix",
                "--trace-icache-entry-prefix-off",
            ])

    def test_enabled_first_trace_arm_is_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            runner.parse_args([
                "missing.nbf", "missing.transfer", "0" * 64, "missing.log",
                "--trace-icache-entry-prefix-first",
                "--trace-icache-entry-prefix-off",
            ])

    def test_command_binds_split_joint_mode(self):
        self.assertIn(
            " joint-split 0 0 normal 0 8 0 aligned pipe; ",
            runner.benchmark_command("joint-split", 0, 0, "normal", 0),
        )

    def test_command_binds_split_joint_one_hook_diagnostic(self):
        self.assertIn(
            " joint-split-one-hook 0 0 normal 0 8 0 aligned pipe; ",
            runner.benchmark_command(
                "joint-split-one-hook", 0, 0, "normal", 0
            ),
        )

    def test_command_binds_joint_follow_only_diagnostic(self):
        self.assertIn(
            " joint-follow-only 0 0 normal 0 8 0 aligned pipe; ",
            runner.benchmark_command(
                "joint-follow-only", 0, 0, "normal", 0
            ),
        )

    def test_command_binds_explicit_instruction_with_wake_data(self):
        self.assertIn(
            " joint-explicit 0 0 normal 0 8 0 skew pipe; ",
            runner.benchmark_command(
                "joint-explicit", 0, 0, "normal", 0, 8, False, "skew"
            ),
        )

    def test_command_binds_explicit_instruction_with_prewake_data(self):
        self.assertIn(
            " joint-prewake-quiescent 0 0 fifo 0 8 0 skew futex; ",
            runner.benchmark_command(
                "joint-prewake-quiescent", 0, 0, "fifo", 0, 8, False,
                "skew", "futex", rt_unlimited=True,
            ),
        )

    def test_command_binds_preseed_instruction_with_prewake_data(self):
        self.assertIn(
            " joint-preseed-quiescent 0 0 fifo 0 8 0 skew futex; ",
            runner.benchmark_command(
                "joint-preseed-quiescent", 0, 0, "fifo", 0, 8, False,
                "skew", "futex", rt_unlimited=True,
            ),
        )

    def test_command_binds_raw_drained_preseed(self):
        self.assertIn(
            " joint-preseed-drained 0 0 normal 0 8 0 skew futex; ",
            runner.benchmark_command(
                "joint-preseed-drained", 0, 0, "normal", 0, 8, False,
                "skew", "futex",
            ),
        )

    def test_print_command_preserves_unlimited_rt_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nbf = root / "linux.nbf"
            transfer = root / "benchmark.transfer"
            log = root / "run.log"
            nbf.write_bytes(b"nbf")
            elf = b"elf"
            digest = hashlib.sha256(elf).hexdigest()
            transfer.write_text(self.valid_transfer(elf))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = runner.main([
                    str(nbf), str(transfer), digest, str(log),
                    "--mode", "joint-preseed-quiescent", "--policy", "fifo",
                    "--rt-unlimited", "--print-command",
                ])
        self.assertEqual(rc, 0)
        self.assertTrue(output.getvalue().startswith(
            "BP_TAGGED_REPLAY_RT_UNLIMITED=1 "
        ))

    def test_command_binds_replay_off_stability_mode(self):
        self.assertIn(
            " off 0 0 normal 0 8 0 aligned futex; ",
            runner.benchmark_command(
                "off", 0, 0, "normal", 0, 8, False, "aligned", "futex"
            ),
        )

    def test_command_binds_futex_sync(self):
        self.assertIn(
            " 8 0 skew futex; ",
            runner.benchmark_command(
                "data", 0, 0, "normal", 0, 8, False, "skew", "futex"
            ),
        )

    def test_command_binds_instruction_trace(self):
        self.assertIn(
            " 8 0 skew futex trace-icache; ",
            runner.benchmark_command(
                "off", 0, 0, "normal", 0, 8, False,
                "skew", "futex", False, True,
            ),
        )

    def test_command_binds_entry_bounded_instruction_trace(self):
        self.assertIn(
            " 8 0 skew futex trace-icache-entry; ",
            runner.benchmark_command(
                "instruction-wake", 0, 0, "normal", 0, 8, False,
                "skew", "futex", False, False, True,
            ),
        )

    def test_command_binds_truncated_entry_prefix_trace(self):
        self.assertIn(
            " 8 0 skew futex trace-icache-entry-prefix; ",
            runner.benchmark_command(
                "instruction-wake", 0, 0, "normal", 0, 8, False,
                "skew", "futex", False, False, False, True,
            ),
        )

    def test_instruction_trace_modes_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            runner.parse_args([
                "missing.nbf", "missing.transfer", "0" * 64, "missing.log",
                "--trace-icache", "--trace-icache-entry-prefix",
            ])

    def test_command_binds_guest_diagnostic_environment(self):
        self.assertTrue(
            runner.benchmark_command(
                "joint-split", 0, 0, "normal", 0, 8, False,
                "skew", "futex", True,
            ).startswith(
            "BP_TAGGED_REPLAY_DIAG=1 "
                "/tmp/scheduler_tagged_replay_benchmark_dynamic "
            )
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
