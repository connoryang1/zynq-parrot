"""Test fail-closed replacement of an immutable NBF instruction table."""

import json
import tempfile
import unittest
from pathlib import Path

from patch_icache_prefix_table_nbf import load_prefix, patch


class PatchIcachePrefixTableNbfTest(unittest.TestCase):
    def test_unique_table_changes_only_requested_words(self):
        source = [
            "01_0000000000000000",
            "03_00000000800000f0_0000000000000001",
            "03_00000000800000f0_0000000000000002",
            "03_0000000080010000_0000000080200000",
            "03_0000000080010008_0000000080200040",
            "03_0000000080200000_0123456789abcdef",
            "fe_0000000000000000",
        ]
        result, base, changed = patch(
            source, [0x80200000, 0x80200040],
            [0x80200000, 0x80A00000],
        )
        self.assertEqual(base, 0x80010000)
        self.assertEqual(changed, [0x80010008])
        self.assertEqual(
            result[4], "03_0000000080010008_0000000080a00000"
        )
        self.assertEqual(result[5], source[5])

    def test_missing_duplicate_and_payload_tables_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "found 0"):
            patch([], [0x80200000], [0x80A00000])
        duplicate = [
            "03_0000000080010000_0000000080200000",
            "03_0000000080011000_0000000080200000",
        ]
        with self.assertRaisesRegex(ValueError, "found 2"):
            patch(duplicate, [0x80200000], [0x80A00000])
        payload = ["03_0000000080200000_0000000080200000"]
        with self.assertRaisesRegex(ValueError, "Linux payload"):
            patch(payload, [0x80200000], [0x80A00000])

    def test_prefix_loader_accepts_integer_and_hex_addresses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prefix.json"
            path.write_text(json.dumps({
                "fixed_shared_prefix": {
                    "line_count": 2,
                    "lines": [
                        {"paddr": 0x80200000},
                        {"paddr_hex": "0x0000000080200040"},
                    ],
                }
            }))
            self.assertEqual(
                load_prefix(path), [0x80200000, 0x80200040]
            )


if __name__ == "__main__":
    unittest.main()
