"""Test fail-closed comparison of matched entry-bounded I-miss traces."""

import json
import tempfile
import unittest
from pathlib import Path

import analyze_tagged_icache_trace_pair as analyzer


class TaggedIcacheTracePairTest(unittest.TestCase):
    def make_trace(self, root, name, mode, enabled, lines, overflow=False,
                   trial=1, explicit_off=False, return_window=False,
                   data_overflow=False, enabled_first=False):
        path = root / name
        status = {
            "status": "PASS", "mode": mode,
            "trace_icache": True, "trace_icache_entry_prefix": True,
            "nbf_sha256": "1" * 64, "transfer_sha256": "2" * 64,
            "elf_sha256": "3" * 64, "control_program_sha256": "4" * 64,
            "bitstream_sha256": "5" * 64,
        }
        if explicit_off:
            status["trace_icache_entry_prefix"] = False
            status["trace_icache_entry_prefix_off"] = True
        if enabled_first:
            status["trace_icache_entry_prefix"] = False
            status["trace_icache_entry_prefix_first"] = True
        if return_window:
            status["trace_icache_entry_prefix"] = False
            status["trace_icache_entry_prefix_off"] = False
            status["trace_icache_return_prefix"] = not explicit_off
            status["trace_icache_return_prefix_off"] = explicit_off
        path.with_suffix(path.suffix + ".status.json").write_text(
            json.dumps(status) + "\n"
        )
        records = "".join(
            f"TAGGED_REPLAY_ITRACE_RECORD index={index} relative={100 + index} "
            f"paddr=0x{line:09x} raw=0x{index:016x}\n"
            for index, line in enumerate(lines)
        )
        path.write_text(
            f"TAGGED_REPLAY_ITRACE_HEADER trial={trial} enabled={enabled} "
            f"i_count={len(lines)} d_count=1 i_overflow={int(overflow)} "
            f"d_overflow={int(data_overflow)} armed=0 "
            "status=0x0000000000000000\n"
            + records
            + f"TAGGED_REPLAY_ITRACE_PREFIX_PASS truncated={int(overflow)} "
              f"records={len(lines)}\n"
            + f"TAGGED_REPLAY trial={trial} enabled={enabled} hooks={enabled} "
              "woken=1 hook_cycles=1 admitted=0 filtered=0 triggers=0 dropped=0 "
              "wake_to_entry=20 load_cycles=3 wake_to_load=23 roundtrip=40\n"
        )
        return path

    def make_prefix(self, root):
        path = root / "prefix.json"
        path.write_text(json.dumps({
            "fixed_shared_prefix": {"lines": [
                {"paddr_hex": "0x0000000080001000"},
                {"paddr_hex": "0x0000000080002000"},
            ]}
        }) + "\n")
        return path

    def test_reports_configured_line_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            off = self.make_trace(root, "off.log", "off", 0,
                                  [0x80001000, 0x80002000, 0x80002000])
            on = self.make_trace(root, "on.log", "instruction-wake", 1,
                                 [0x80002000, 0x80003000])
            result = analyzer.analyze(off, on, self.make_prefix(root))
            self.assertEqual(result["configured_lines"]["net_distinct_reduction"], 1)
            self.assertEqual(result["configured_lines"]["net_event_reduction"], 2)
            self.assertEqual(result["set_comparison"]["common_unique_lines"], 1)

    def test_accepts_explicit_disabled_and_enabled_arms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            off = self.make_trace(
                root, "off.log", "instruction-explicit", 0,
                [0x80001000, 0x80002000], trial=0, explicit_off=True,
            )
            on = self.make_trace(
                root, "on.log", "instruction-explicit", 1,
                [0x80002000], trial=1,
            )
            result = analyzer.analyze(off, on, self.make_prefix(root))
        self.assertEqual(result["configured_lines"]["net_distinct_reduction"], 1)

    def test_accepts_independently_recovered_enabled_first_arm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            off = self.make_trace(
                root, "off.log", "instruction-explicit", 0,
                [0x80001000, 0x80002000], trial=0, explicit_off=True,
            )
            on = self.make_trace(
                root, "on.log", "instruction-explicit", 1,
                [0x80002000], trial=0, enabled_first=True,
            )
            result = analyzer.analyze(off, on, self.make_prefix(root))
        self.assertEqual(result["pairing"], "independently-recovered-trial-zero")
        self.assertEqual(result["configured_lines"]["net_distinct_reduction"], 1)
        self.assertIn(
            "observational differences",
            " ".join(result["interpretation_limits"]),
        )

    def test_accepts_explicit_roundtrip_return_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            off = self.make_trace(
                root, "off.log", "instruction-explicit-roundtrip", 0,
                [0x80001000, 0x80002000], trial=0, explicit_off=True,
                return_window=True,
            )
            on = self.make_trace(
                root, "on.log", "instruction-explicit-roundtrip", 1,
                [0x80002000], trial=1, return_window=True,
            )
            result = analyzer.analyze(off, on, self.make_prefix(root))
        self.assertEqual(result["window"], "return")
        self.assertEqual(result["configured_lines"]["net_distinct_reduction"], 1)

    def test_accepts_direction_selected_entry_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            off = self.make_trace(
                root, "off.log", "instruction-explicit-directed", 0,
                [0x80001000, 0x80002000], trial=0, explicit_off=True,
            )
            on = self.make_trace(
                root, "on.log", "instruction-explicit-directed", 1,
                [0x80002000], trial=1,
            )
            result = analyzer.analyze(off, on, self.make_prefix(root))
        self.assertEqual(result["window"], "entry")
        self.assertEqual(result["configured_lines"]["net_distinct_reduction"], 1)

    def test_interpretation_names_truncated_arm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            off = self.make_trace(
                root, "off.log", "instruction-explicit", 0,
                [0x80001000], trial=0, explicit_off=True,
            )
            on = self.make_trace(
                root, "on.log", "instruction-explicit", 1,
                [0x80001000] * 256, overflow=True,
            )
            result = analyzer.analyze(off, on, self.make_prefix(root))
        self.assertIn("replay-on trace", result["interpretation_limits"][0])
        coverage = result["configured_lines"]["absence_coverage"]
        self.assertFalse(coverage["replay_on_is_complete"])
        self.assertTrue(
            coverage["retained_on_prefix_reaches_off_configured_horizon"]
        )
        self.assertEqual(
            coverage["latest_replay_off_configured_relative"], 100
        )
        self.assertEqual(coverage["replay_on_last_relative"], 355)

    def test_accepts_unconsumed_data_recorder_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.make_trace(
                root, "off.log", "instruction-explicit-roundtrip", 0,
                [0x80001000], trial=0, explicit_off=True,
                return_window=True, data_overflow=True,
            )
            result = analyzer.load_trace(
                trace, "instruction-explicit-roundtrip", 0, 0, "return"
            )
        self.assertTrue(result["data_truncated"])

    def test_rejects_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            off = self.make_trace(root, "off.log", "off", 0, [0x80001000])
            on = self.make_trace(root, "on.log", "instruction-wake", 1,
                                 [0x80001000])
            status_path = on.with_suffix(on.suffix + ".status.json")
            status = json.loads(status_path.read_text())
            status["elf_sha256"] = "9" * 64
            status_path.write_text(json.dumps(status) + "\n")
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                analyzer.analyze(off, on, self.make_prefix(root))

    def test_rejects_false_truncation_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            off = self.make_trace(root, "off.log", "off", 0, [0x80001000])
            text = off.read_text().replace("truncated=0", "truncated=1")
            off.write_text(text)
            with self.assertRaisesRegex(ValueError, "prefix PASS"):
                analyzer.load_trace(off, "off", 0)


if __name__ == "__main__":
    unittest.main()
