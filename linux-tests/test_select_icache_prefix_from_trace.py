"""Validate fail-closed exact-order prefix selection from recorder output."""

import unittest

from select_icache_prefix_from_trace import select


def trace(addresses, overflow=0, passed=True):
    lines = [
        f"TRACE_HEADER i_count={len(addresses)} d_count=0 "
        f"i_overflow={overflow} d_overflow=0 armed=0"
    ]
    lines.extend(
        f"TRACE_RECORD seq={index} side=I index={index} cycle={index} "
        f"paddr=0x{value:09x}"
        for index, value in enumerate(addresses)
    )
    if passed:
        lines.append("TRACE_PASS")
    return "\n".join(lines)


class PrefixSelectorTest(unittest.TestCase):
    def test_selects_unique_lines_in_observed_order(self):
        result = select(trace([0x1000, 0x1040, 0x1040, 0x1080]), 0x1040, 2)
        lines = result["fixed_shared_prefix"]["lines"]
        self.assertEqual([line["paddr"] for line in lines], [0x1040, 0x1080])
        self.assertEqual([line["rank"] for line in lines], [0, 1])

    def test_rejects_overflow(self):
        with self.assertRaisesRegex(ValueError, "overflowed"):
            select(trace([0x1000], overflow=1), 0x1000, 1)

    def test_rejects_missing_pass(self):
        with self.assertRaisesRegex(ValueError, "TRACE_PASS"):
            select(trace([0x1000], passed=False), 0x1000, 1)

    def test_rejects_missing_start(self):
        with self.assertRaisesRegex(ValueError, "not observed"):
            select(trace([0x1000]), 0x1040, 1)

    def test_rejects_short_suffix(self):
        with self.assertRaisesRegex(ValueError, "only 1"):
            select(trace([0x1000]), 0x1000, 2)


if __name__ == "__main__":
    unittest.main()
