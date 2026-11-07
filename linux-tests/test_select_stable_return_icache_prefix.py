"""Test stable post-hint return-path instruction-prefix selection."""

import json
import tempfile
import unittest
from pathlib import Path

import select_stable_return_icache_prefix as selector


class StableReturnIcachePrefixTest(unittest.TestCase):
    def make_trace(self, root, name, records, hint=(20, 30), overflow=False,
                   elf="3" * 64):
        path = root / name
        status = {
            "status": "PASS", "mode": "instruction-explicit-roundtrip",
            "trace_icache_return_prefix_off": True,
            "nbf_sha256": "1" * 64, "transfer_sha256": "2" * 64,
            "elf_sha256": elf, "control_program_sha256": "4" * 64,
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
        boundary = (
            "" if hint is None else
            f"TAGGED_REPLAY_RETURN_HINT trial=0 enabled=0 "
            f"begin_relative={hint[0]} end_relative={hint[1]}\n"
        )
        path.write_text(
            f"TAGGED_REPLAY_ITRACE_HEADER trial=0 enabled=0 "
            f"i_count={len(records)} d_count=0 i_overflow={int(overflow)} "
            "d_overflow=0 armed=0 status=0x0000000000000000\n"
            + boundary + rows
            + f"TAGGED_REPLAY_ITRACE_PREFIX_PASS truncated={int(overflow)} "
              f"records={len(records)}\n"
            + "TAGGED_REPLAY trial=0 enabled=0 hooks=0 woken=1 "
              "hook_cycles=1 admitted=0 filtered=0 triggers=0 dropped=0 "
              "wake_to_entry=20 load_cycles=3 wake_to_load=23 roundtrip=40\n"
        )
        return path

    def make_prefix(self, root):
        path = root / "forward.json"
        path.write_text(json.dumps({
            "fixed_shared_prefix": {
                "lines": [{"paddr_hex": "0x0000000080001000"}]
            }
        }) + "\n")
        return path

    def test_selects_common_post_hint_lines_and_excludes_forward(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            traces = [
                self.make_trace(root, "a.log", [
                    (25, 0x80002000), (31, 0x80001000),
                    (40, 0x80002000), (60, 0x80003000),
                ], hint=(20, 30)),
                self.make_trace(root, "b.log", [
                    (35, 0x80002000), (45, 0x80001000),
                    (50, 0x80002000), (55, 0x80003000),
                ], hint=(30, 40)),
                self.make_trace(root, "c.log", [
                    (45, 0x80002000), (50, 0x80001000),
                    (70, 0x80003000),
                ], hint=(35, 45)),
            ]
            result = selector.select(traces, self.make_prefix(root), 2)
        lines = result["fixed_shared_prefix"]["lines"]
        self.assertEqual(
            [line["paddr"] for line in lines],
            [0x80002000, 0x80003000],
        )
        self.assertEqual(
            lines[0]["trace_relative_to_selection_floor"], [10, 10, 0]
        )

    def test_rejects_missing_hint_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            traces = [
                self.make_trace(root, f"{name}.log", [(40, 0x80002000)],
                                hint=None if name == "b" else (20, 30))
                for name in "abc"
            ]
            with self.assertRaisesRegex(ValueError, "boundary is absent"):
                selector.select(traces, self.make_prefix(root), 1)

    def test_rejects_truncated_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = [(40 + index, 0x80002000 + index * 64)
                       for index in range(256)]
            traces = [
                self.make_trace(root, f"{name}.log", records,
                                overflow=name == "c")
                for name in "abc"
            ]
            with self.assertRaisesRegex(ValueError, "truncated"):
                selector.select(traces, self.make_prefix(root), 1)

    def test_explicitly_accepts_truncated_prefix_for_positive_intersection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = [(40 + index, 0x80002000 + index * 64)
                       for index in range(256)]
            traces = [
                self.make_trace(root, f"{name}.log", records,
                                overflow=name == "c")
                for name in "abc"
            ]
            result = selector.select(
                traces, self.make_prefix(root), 1,
                allow_truncated=True,
            )
        self.assertTrue(result["selection"]["truncated_prefixes_allowed"])

    def test_aligns_selection_on_per_trace_switch_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            anchor = 0x80004000
            traces = [
                self.make_trace(root, "a.log", [
                    (40, 0x80002000), (100, anchor), (130, 0x80003000),
                ]),
                self.make_trace(root, "b.log", [
                    (50, 0x80002000), (200, anchor), (240, 0x80003000),
                ]),
                self.make_trace(root, "c.log", [
                    (60, 0x80002000), (300, anchor), (350, 0x80003000),
                ]),
            ]
            result = selector.select(
                traces, self.make_prefix(root), 2,
                anchor_paddr=anchor,
            )
        lines = result["fixed_shared_prefix"]["lines"]
        self.assertEqual(
            [line["paddr"] for line in lines], [anchor, 0x80003000]
        )
        self.assertEqual(
            result["selection"]["trace_anchor_relatives"], [100, 200, 300]
        )

    def test_rejects_missing_switch_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            traces = [
                self.make_trace(root, f"{name}.log", [(40, 0x80002000)])
                for name in "abc"
            ]
            with self.assertRaisesRegex(ValueError, "anchor .* is absent"):
                selector.select(
                    traces, self.make_prefix(root), 1,
                    anchor_paddr=0x80004000,
                )

    def test_rejects_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            traces = [
                self.make_trace(root, "a.log", [(40, 0x80002000)]),
                self.make_trace(root, "b.log", [(40, 0x80002000)]),
                self.make_trace(
                    root, "c.log", [(40, 0x80002000)], elf="9" * 64
                ),
            ]
            with self.assertRaisesRegex(ValueError, "elf_sha256"):
                selector.select(traces, self.make_prefix(root), 1)


if __name__ == "__main__":
    unittest.main()
