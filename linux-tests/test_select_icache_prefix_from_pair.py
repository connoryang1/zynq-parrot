"""Test evidence-ranked instruction-prefix selection from matched traces."""

import json
import tempfile
import unittest
from pathlib import Path

import select_icache_prefix_from_pair as selector


class SelectIcachePrefixFromPairTest(unittest.TestCase):
    def write_inputs(self, root):
        prefix = root / "prefix.json"
        prefix.write_text(json.dumps({
            "input_identity": {"kernel_sha256": "a" * 64},
            "fixed_shared_prefix": {
                "policy": "test source",
                "line_count": 3,
                "lines": [
                    {"rank": rank, "paddr": address,
                     "paddr_hex": f"0x{address:016x}",
                     "relative": 100 + rank, "cache_set": rank}
                    for rank, address in enumerate((0x1000, 0x2000, 0x3000))
                ],
            },
        }) + "\n")
        analysis = root / "analysis.json"
        analysis.write_text(json.dumps({
            "configured_lines": {
                "off": {"lines": [
                    {"paddr": 0x1000, "relatives": [1, 2]},
                    {"paddr": 0x2000, "relatives": [3]},
                    {"paddr": 0x3000, "relatives": [4]},
                ]},
                "on": {"lines": [
                    {"paddr": 0x1000, "relatives": []},
                    {"paddr": 0x2000, "relatives": []},
                    {"paddr": 0x3000, "relatives": [5, 6]},
                ]},
            },
        }) + "\n")
        return prefix, analysis

    def test_selects_positive_reductions_in_evidence_order(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix, analysis = self.write_inputs(Path(directory))
            result = selector.select(prefix, analysis)
        lines = result["fixed_shared_prefix"]["lines"]
        self.assertEqual([line["paddr"] for line in lines], [0x1000, 0x2000])
        self.assertEqual([line["event_reduction"] for line in lines], [2, 1])
        self.assertEqual([line["source_rank"] for line in lines], [0, 1])
        self.assertEqual([line["rank"] for line in lines], [0, 1])

    def test_rejects_analysis_with_different_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix, analysis = self.write_inputs(Path(directory))
            data = json.loads(analysis.read_text())
            data["configured_lines"]["on"]["lines"].pop()
            analysis.write_text(json.dumps(data) + "\n")
            with self.assertRaisesRegex(ValueError, "do not match"):
                selector.select(prefix, analysis)

    def test_rejects_no_positive_reduction(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix, analysis = self.write_inputs(Path(directory))
            data = json.loads(analysis.read_text())
            data["configured_lines"]["on"] = data["configured_lines"]["off"]
            analysis.write_text(json.dumps(data) + "\n")
            with self.assertRaisesRegex(ValueError, "no positive"):
                selector.select(prefix, analysis)


if __name__ == "__main__":
    unittest.main()
