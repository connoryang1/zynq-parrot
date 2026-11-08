#!/usr/bin/env python3
"""Verify fail-closed transfer handling for the sustained pipe-hint runner."""

import base64
import hashlib
from pathlib import Path
import tempfile
import unittest

from run_scheduler_pipe_hint import (
    GUEST_ELF,
    build_guest_command,
    parse_args,
    validate_args,
    validate_transfer,
)


class PipeHintRunnerTests(unittest.TestCase):
    def test_seed_policy_is_bound_into_runner_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--policy", "seed",
        ])
        self.assertEqual(args.policy, "seed")

    def test_warmup_is_bound_into_runner_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--warmup", "256",
        ])
        self.assertEqual(args.warmup, 256)

    def test_preseed_policy_is_accepted(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--policy", "preseed",
        ])
        self.assertEqual(args.policy, "preseed")

    def test_futex_sync_is_bound_into_runner_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--sync", "futex",
        ])
        self.assertEqual(args.sync, "futex")

    def test_resume_leg_profile_is_bound_into_runner_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--sync", "futex",
            "--profile", "legs",
        ])
        self.assertEqual(args.profile, "legs")

    def test_working_set_is_bound_into_runner_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--sync", "futex",
            "--working-set-kib", "256",
        ])
        self.assertEqual(args.working_set_kib, 256)
        self.assertTrue(build_guest_command(args).endswith("futex plain 256"))

    def test_accepts_unmatched_continuous_policy(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64,
            "--policy", "continuous-unmatched",
        ])
        self.assertEqual(args.policy, "continuous-unmatched")

    def test_futex_early_policy_requires_futex(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64,
            "--policy", "futex-early",
        ])
        with self.assertRaisesRegex(ValueError, "requires futex"):
            validate_args(args)

    def test_accepts_futex_early_policy_with_futex(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64,
            "--policy", "futex-early", "--sync", "futex",
        ])
        self.assertEqual(args.policy, "futex-early")

    def test_resume_leg_profile_rejects_pipe_sync(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--profile", "legs",
        ])
        with self.assertRaisesRegex(ValueError, "requires futex"):
            validate_args(args)

    def test_legacy_four_arg_cli_omits_new_mode_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--policy", "preseed",
            "--warmup", "256", "--legacy-four-arg-cli",
        ])
        self.assertEqual(
            build_guest_command(args),
            f"{GUEST_ELF} 512 8 preseed 256",
        )

    def test_legacy_four_arg_cli_rejects_new_futex_mode(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--sync", "futex",
            "--legacy-four-arg-cli",
        ])
        with self.assertRaisesRegex(ValueError, "requires pipe/plain"):
            validate_args(args)

    def test_status_uses_pointer_copy_abi(self):
        source = (Path(__file__).resolve().parent
                  / "scheduler_pipe_hint_benchmark.c").read_text()
        self.assertIn("(unsigned long)&status", source)
        self.assertNotIn("PR_BP_PREVIEW_ICACHE_STATUS, 0UL", source)

    def test_parent_resume_leg_stops_before_working_set(self):
        source = (Path(__file__).resolve().parent
                  / "scheduler_pipe_hint_benchmark.c").read_text()
        futex = source.split("static struct cell_result run_futex_cell", 1)[1]
        measured = futex.split("begin = cycle();", 1)[1].split(
            "end = cycle();", 1)[0]
        resume = measured.index(
            "parent_resume += cycle() - shared->child_launch;")
        working_set = measured.index(
            "parent_checksum += touch_working_set(")
        self.assertLess(resume, working_set)

    def test_futex_early_patch_excludes_internal_wake_callers(self):
        patch = (Path(__file__).resolve().parent / "kernel-patches" /
                 "0026-blackparrot-early-futex-instruction-replay.patch").read_text()
        self.assertIn("--- a/kernel/futex/syscalls.c", patch)
        self.assertIn("this at syscall dispatch excludes internal", patch)
        self.assertNotIn("--- a/kernel/futex/waitwake.c", patch)

    def test_transfer_binds_exact_elf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transfer"
            payload = b"exact pipe benchmark"
            encoded = base64.b64encode(payload).decode()
            path.write_text(
                f": > {GUEST_ELF}.b64\n"
                f"echo '{encoded}' >> {GUEST_ELF}.b64\n"
                f"base64 -d {GUEST_ELF}.b64 > {GUEST_ELF}\n"
                f"chmod +x {GUEST_ELF}\n"
            )
            validate_transfer(path, hashlib.sha256(payload).hexdigest())
            with self.assertRaisesRegex(ValueError, "does not match"):
                validate_transfer(path, "0" * 64)

    def test_transfer_rejects_extra_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transfer"
            path.write_text(
                f": > {GUEST_ELF}.b64\n"
                "uname -a\n"
                f"base64 -d {GUEST_ELF}.b64 > {GUEST_ELF}\n"
                f"chmod +x {GUEST_ELF}\n"
            )
            with self.assertRaisesRegex(ValueError, "unexpected"):
                validate_transfer(path, "0" * 64)

    def test_transfer_rejects_oversize_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transfer"
            path.write_text("x" * 769 + "\n")
            with self.assertRaisesRegex(ValueError, "exceeds 768"):
                validate_transfer(path, "0" * 64)


if __name__ == "__main__":
    unittest.main()
