"""Test exact tagged-futex instruction-prefix extraction."""

import json
import tempfile
import unittest
from pathlib import Path

from extract_tagged_icache_prefix import extract


class TaggedIcachePrefixExtractionTest(unittest.TestCase):
    def make_trace(self, root, overflow=0):
        path = root / "trace.log"
        rows = [
            "TAGGED_REPLAY_ITRACE_HEADER trial=0 enabled=0 i_count=4 "
            f"d_count=2 i_overflow={overflow} d_overflow=0 armed=0 "
            "status=0x0000000000000404",
            "TAGGED_REPLAY_ITRACE_RECORD index=0 relative=99 "
            "paddr=0x810000000 raw=0x0000000000000000",
            "TAGGED_REPLAY_ITRACE_RECORD index=1 relative=100 "
            "paddr=0x80200040 raw=0x0000000000000000",
            "TAGGED_REPLAY_ITRACE_RECORD index=2 relative=101 "
            "paddr=0x80200080 raw=0x0000000000000000",
            "TAGGED_REPLAY_ITRACE_RECORD index=3 relative=102 "
            "paddr=0x80200080 raw=0x0000000000000000",
            "TAGGED_REPLAY_ITRACE_PASS records=4",
        ]
        path.write_text("\n".join(rows) + "\n")
        path.with_suffix(".log.status.json").write_text(json.dumps({
            "status": "PASS", "mode": "off", "trace_icache": True,
        }) + "\n")
        return path

    def test_selects_unique_privileged_post_floor_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            result = extract(
                self.make_trace(Path(directory)), "a" * 64, 100, 2
            )
        lines = result["fixed_shared_prefix"]["lines"]
        self.assertEqual([line["paddr"] for line in lines], [
            0x80200040, 0x80200080,
        ])
        self.assertEqual(result["selection"]["captured_instruction_records"], 4)

    def test_rejects_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_trace(Path(directory), overflow=1)
            with self.assertRaisesRegex(ValueError, "clean disabled capture"):
                extract(path, "a" * 64, 100, 2)


if __name__ == "__main__":
    unittest.main()
