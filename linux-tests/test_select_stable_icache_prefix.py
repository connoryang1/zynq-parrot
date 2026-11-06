"""Test stable post-switch instruction-prefix selection."""

import json
import tempfile
import unittest
from pathlib import Path

import select_stable_icache_prefix as selector


class StableIcachePrefixTest(unittest.TestCase):
    def make_trace(self, root, name, records, elf="3" * 64):
        path = root / name
        status = {
            "status": "PASS", "mode": "off",
            "trace_icache_entry_prefix": True,
            "nbf_sha256": name[0] * 64,
            "transfer_sha256": "2" * 64, "elf_sha256": elf,
            "control_program_sha256": "4" * 64,
            "bitstream_sha256": "5" * 64,
        }
        path.with_suffix(path.suffix + ".status.json").write_text(
            json.dumps(status) + "\n"
        )
        rows = "".join(
            f"TAGGED_REPLAY_ITRACE_RECORD index={index} relative={relative} "
            f"paddr=0x{address:x} raw=0x{index:016x}\n"
            for index, (relative, address) in enumerate(records)
        )
        path.write_text(
            f"TAGGED_REPLAY_ITRACE_HEADER trial=1 enabled=0 "
            f"i_count={len(records)} d_count=0 i_overflow=0 d_overflow=0 "
            "armed=0 status=0x0000000000000000\n"
            + rows
            + f"TAGGED_REPLAY_ITRACE_PREFIX_PASS truncated=0 "
              f"records={len(records)}\n"
            + "TAGGED_REPLAY trial=1 enabled=0 hooks=0 woken=1 "
              "hook_cycles=1 admitted=0 filtered=0 triggers=0 dropped=0 "
              "wake_to_entry=20 load_cycles=3 wake_to_load=23 roundtrip=40\n"
        )
        return path

    def test_selects_common_post_floor_lines_by_latest_first_use(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.make_trace(root, "a.log", [
                (50, 0x80001000), (110, 0x80002000),
                (130, 0x80003000), (150, 0x80004000),
            ])
            second = self.make_trace(root, "b.log", [
                (60, 0x80001000), (120, 0x80003000),
                (140, 0x80002000), (170, 0x80005000),
            ])
            result = selector.select(
                [first, second], "a" * 64, selection_floor=100, limit=2
            )
        lines = result["fixed_shared_prefix"]["lines"]
        self.assertEqual([line["paddr"] for line in lines],
                         [0x80003000, 0x80002000])
        self.assertEqual(lines[0]["trace_first_relatives"], [130, 120])

    def test_rejects_mismatched_elf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.make_trace(root, "a.log", [(110, 0x80002000)])
            second = self.make_trace(
                root, "b.log", [(120, 0x80002000)], elf="9" * 64
            )
            with self.assertRaisesRegex(ValueError, "elf_sha256"):
                selector.select([first, second], "a" * 64, 100, 1)

    def test_rejects_too_few_stable_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.make_trace(root, "a.log", [(110, 0x80002000)])
            second = self.make_trace(root, "b.log", [(120, 0x80003000)])
            with self.assertRaisesRegex(ValueError, "only 0 stable"):
                selector.select([first, second], "a" * 64, 100, 1)


if __name__ == "__main__":
    unittest.main()
