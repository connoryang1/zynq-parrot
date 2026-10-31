"""Validate bounded command construction and argument checks for trace runs."""

import argparse
import tempfile
import unittest
from pathlib import Path

from run_cache_miss_trace_capture import capture_command, validate_args


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
