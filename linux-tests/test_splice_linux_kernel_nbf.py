"""Validate fail-closed replacement of an exact Linux NBF payload."""

import tempfile
import unittest
from pathlib import Path

from splice_linux_kernel_nbf import splice


class LinuxKernelNbfSpliceTest(unittest.TestCase):
    def inputs(self, directory):
        root = Path(directory)
        source = root / "source.nbf"
        old = root / "old.bin"
        new = root / "new.bin"
        output = root / "output.nbf"
        old.write_bytes(bytes.fromhex("01000000000000000203000000000000"))
        new.write_bytes(bytes.fromhex("04050000000000000000000000000000"))
        source.write_text(
            "03_0000000080000000_0000000000000009\n"
            "03_0000000080200000_0000000000000001\n"
            "03_0000000080200008_0000000000000302\n"
            "03_0000000082200000_0000000000000007\n"
            "ff_0000000000000000_0000000000000000\n"
        )
        return source, old, new, output

    def test_replaces_payload_and_preserves_surrounding_records(self):
        with tempfile.TemporaryDirectory() as directory:
            source, old, new, output = self.inputs(directory)
            summary = splice(source, old, new, output)
            self.assertEqual(summary["old_records"], 2)
            self.assertEqual(summary["new_records"], 1)
            self.assertEqual(
                output.read_text(),
                "03_0000000080000000_0000000000000009\n"
                "03_0000000080200000_0000000000000504\n"
                "03_0000000082200000_0000000000000007\n"
                "ff_0000000000000000_0000000000000000\n",
            )

    def test_exact_old_payload_round_trips_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            source, old, _new, output = self.inputs(directory)
            splice(source, old, old, output)
            self.assertEqual(output.read_bytes(), source.read_bytes())

    def test_wrong_source_payload_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source, old, new, output = self.inputs(directory)
            source.write_text(source.read_text().replace("0302", "0303"))
            with self.assertRaisesRegex(ValueError, "exact old payload"):
                splice(source, old, new, output)

    def test_size_change_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source, old, new, output = self.inputs(directory)
            new.write_bytes(b"short")
            with self.assertRaisesRegex(ValueError, "size differs"):
                splice(source, old, new, output)


if __name__ == "__main__":
    unittest.main()
