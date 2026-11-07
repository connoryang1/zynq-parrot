#!/usr/bin/env python3
"""Verify fail-closed transfer handling for the sustained pipe-hint runner."""

import base64
import hashlib
from pathlib import Path
import tempfile
import unittest

from run_scheduler_pipe_hint import (
    GUEST_ELF,
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

    def test_resume_leg_profile_rejects_pipe_sync(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--profile", "legs",
        ])
        with self.assertRaisesRegex(ValueError, "requires futex"):
            validate_args(args)

    def test_status_uses_pointer_copy_abi(self):
        source = (Path(__file__).resolve().parent
                  / "scheduler_pipe_hint_benchmark.c").read_text()
        self.assertIn("(unsigned long)&status", source)
        self.assertNotIn("PR_BP_PREVIEW_ICACHE_STATUS, 0UL", source)

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
