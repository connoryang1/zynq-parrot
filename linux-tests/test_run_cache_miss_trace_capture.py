"""Validate bounded command construction and argument checks for trace runs."""

import argparse
import tempfile
import unittest
from pathlib import Path

from run_cache_miss_trace_capture import (
    PIPE_GUEST_ELF,
    capture_command,
    guest_command,
    guest_elf,
    validate_args,
)


class TraceRunnerTest(unittest.TestCase):
    def args(self, directory, **updates):
        nbf = Path(directory) / "image.nbf"
        transfer = Path(directory) / "transfer.txt"
        nbf.write_text("nbf")
        transfer.write_text("command\n")
        values = {
            "nbf": nbf,
            "transfer": transfer,
            "elf_sha256": "1" * 64,
            "control_sha256": "2" * 64,
            "samples": 1,
            "window": "full",
            "program": "cache-miss",
            "group": 0,
            "preview_mode": "disabled",
            "cache_preview_mode": "legacy",
            "cache_summary_only": False,
            "cache_allow_overflow": False,
            "runtime_ms": 100,
        }
        values.update(updates)
        return argparse.Namespace(**values)

    def test_default_command_is_one_full_capture(self):
        self.assertEqual(
            capture_command("full", 1),
            "/tmp/cache_miss_trace_capture_dynamic --window full; "
            "rc=$?; echo TRACE_CAPTURE_EXIT rc=$rc",
        )

    def test_multisample_command_is_explicit(self):
        self.assertIn("--samples 7", capture_command("to-peer", 7))

    def test_cache_wakeup_trigger_command_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory, samples=201,
                             cache_preview_mode="wake-trigger")
            self.assertEqual(
                guest_command(args),
                "/tmp/cache_miss_trace_capture_dynamic --window full "
                "--samples 201 --preview-mode wake-trigger; rc=$?; "
                "echo TRACE_CAPTURE_EXIT rc=$rc",
            )

    def test_cache_disabled_registration_command_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory, cache_preview_mode="disabled")
            self.assertIn("--preview-mode disabled", guest_command(args))

    def test_persistent_timing_command_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(
                directory, samples=201, window="to-peer",
                cache_preview_mode="wake-trigger", cache_summary_only=True,
                cache_allow_overflow=True,
            )
            self.assertEqual(
                guest_command(args),
                "/tmp/cache_miss_trace_capture_dynamic --window to-peer "
                "--samples 201 --preview-mode wake-trigger --summary-only "
                "--allow-overflow; rc=$?; echo TRACE_CAPTURE_EXIT rc=$rc",
            )

    def test_overflow_requires_summary_only(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "summary-only"):
                validate_args(self.args(directory, cache_allow_overflow=True))

    def test_pipe_command_is_fixed_and_group_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory, program="physical-preview-pipe",
                             group=7)
            self.assertEqual(
                guest_command(args),
                f"{PIPE_GUEST_ELF} 7 disabled; rc=$?; "
                "echo TRACE_CAPTURE_EXIT rc=$rc",
            )
            self.assertEqual(guest_elf(args), PIPE_GUEST_ELF)

    def test_pipe_trigger_command_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory, program="physical-preview-pipe",
                             group=3, preview_mode="trigger")
            self.assertEqual(
                guest_command(args),
                f"{PIPE_GUEST_ELF} 3 trigger; rc=$?; "
                "echo TRACE_CAPTURE_EXIT rc=$rc",
            )

    def test_pipe_wakeup_trigger_command_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory, program="physical-preview-pipe",
                             group=3, preview_mode="wake-trigger")
            self.assertEqual(
                guest_command(args),
                f"{PIPE_GUEST_ELF} 3 wake-trigger; rc=$?; "
                "echo TRACE_CAPTURE_EXIT rc=$rc",
            )

    def test_pipe_rejects_multiple_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory, program="physical-preview-pipe",
                             samples=2)
            with self.assertRaisesRegex(ValueError, "exactly one sample"):
                validate_args(args)

    def test_group_bounds_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "group"):
                validate_args(self.args(directory, group=8))

    def test_sample_bounds_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "samples"):
                validate_args(self.args(directory, samples=0))

    def test_hash_format_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "ELF SHA-256"):
                validate_args(self.args(directory, elf_sha256="bad"))

    def test_existing_inputs_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            validate_args(self.args(directory))


if __name__ == "__main__":
    unittest.main()
