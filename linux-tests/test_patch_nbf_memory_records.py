"""Test fail-closed exact NBF memory-record replacement."""

import unittest

from patch_nbf_memory_records import parse_replacement, patch


class PatchNbfMemoryRecordsTest(unittest.TestCase):
    def test_exact_record_changes_and_other_lines_stay_identical(self):
        source = [
            "01_0000000000000000",
            "03_0000000080017e60_0000000080a12500",
            "03_0000000080017e68_0123456789abcdef",
            "fe_0000000000000000",
        ]
        result = patch(source, [(0x80017E60, 0x80A12500, 0x8023F780)])
        self.assertEqual(
            result,
            [
                source[0],
                "03_0000000080017e60_000000008023f780",
                source[2],
                source[3],
            ],
        )

    def test_wrong_expected_data_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "expected"):
            patch(
                ["03_0000000080017e60_0000000080a12500"],
                [(0x80017E60, 0xDEAD, 0x8023F780)],
            )

    def test_missing_and_duplicate_requests_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly once"):
            patch([], [(0x80017E60, 1, 2)])
        with self.assertRaisesRegex(ValueError, "duplicate replacement"):
            patch([], [(0x80017E60, 1, 2), (0x80017E60, 2, 3)])

    def test_cli_replacement_parser_accepts_hex(self):
        self.assertEqual(
            parse_replacement("0x80017e60:0x80a12500:0x8023f780"),
            (0x80017E60, 0x80A12500, 0x8023F780),
        )


if __name__ == "__main__":
    unittest.main()
