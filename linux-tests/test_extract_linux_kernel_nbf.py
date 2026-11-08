#!/usr/bin/env python3
"""Test exact reconstruction of a canonical skip-zero NBF payload."""

import tempfile
import unittest
from pathlib import Path

from extract_linux_kernel_nbf import extract


def record(address, value, command=3):
    return f"{command:02x}_{address:016x}_{value:016x}\n"


class ExtractLinuxKernelNbfTests(unittest.TestCase):
    def test_reconstructs_written_records_and_zero_fills_holes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.nbf"
            output = Path(directory) / "payload.bin"
            source.write_text(
                record(0x80000000, 1)
                + record(0x80200000, 0x0807060504030201)
                + record(0x80200010, 0x1817161514131211)
                + record(0, 0, 0xFF)
            )
            summary = extract(source, output, 24)
            self.assertEqual(summary["records"], 2)
            self.assertEqual(
                output.read_bytes(),
                bytes(range(1, 9)) + bytes(8) + bytes(range(17, 25)),
            )

    def test_rejects_noncanonical_overlapping_write(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.nbf"
            output = Path(directory) / "payload.bin"
            source.write_text(record(0x80200000, 1, command=2))
            with self.assertRaisesRegex(ValueError, "noncanonical"):
                extract(source, output, 8)

    def test_rejects_duplicate_payload_write(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.nbf"
            output = Path(directory) / "payload.bin"
            source.write_text(record(0x80200000, 1) + record(0x80200000, 2))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                extract(source, output, 8)


if __name__ == "__main__":
    unittest.main()
