"""Verify that NBF splicing changes only the selected OpenSBI address range."""

import unittest

from splice_opensbi_nbf import splice


def record(address, value):
    return f"03_{address:016x}_{value:016x}"


PREAMBLE = ["02_0000000000200008_0000000000000001",
            "fe_0000000000000000_0000000000000000"]
TAIL = ["fe_0000000000000000_0000000000000000",
        record(0x80001000, 0x55),
        "ff_0000000000000000_0000000000000000"]


class SpliceNbfTest(unittest.TestCase):
    def test_replaces_only_opensbi_and_retains_base_tail(self):
        base = PREAMBLE + [record(0x80000000, 1), record(0x80200000, 2),
                           record(0x80300000, 3)] + TAIL
        donor = PREAMBLE + [record(0x80000000, 10), record(0x80000008, 11),
                            record(0x80200000, 99)] + TAIL
        output, donor_low, base_high = splice(base, donor)
        self.assertEqual(donor_low, [record(0x80000000, 10),
                                     record(0x80000008, 11)])
        self.assertEqual(base_high, [record(0x80200000, 2),
                                     record(0x80300000, 3)])
        self.assertEqual(output, PREAMBLE + donor_low + base_high + TAIL)

    def test_rejects_mismatched_boot_preamble(self):
        base = PREAMBLE + [record(0x80000000, 1),
                           record(0x80200000, 2)] + TAIL
        donor = ["fe_0000000000000000_0000000000000000",
                 record(0x80000000, 10)] + TAIL
        with self.assertRaisesRegex(ValueError, "preambles differ"):
            splice(base, donor)

    def test_rejects_duplicate_selected_address(self):
        base = PREAMBLE + [record(0x80000000, 1),
                           record(0x80200000, 2)] + TAIL
        donor = PREAMBLE + [record(0x80000000, 10),
                            record(0x80000000, 11)] + TAIL
        with self.assertRaisesRegex(ValueError, "duplicate"):
            splice(base, donor)


if __name__ == "__main__":
    unittest.main()
