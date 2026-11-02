"""Test strict disabled-versus-enabled pipe miss-trace comparison."""

import json
import tempfile
import unittest
from pathlib import Path

from analyze_scheduler_physical_preview_trace_pair import compare


def write_trace(path, preview, mode, load_cycles, cycles):
    """Write one minimal complete trace and matching runner status."""
    identity = {
        "nbf_sha256": "1" * 64,
        "transfer_sha256": "2" * 64,
        "elf_sha256": "3" * 64,
        "control_program_sha256": "4" * 64,
        "bitstream_sha256": "5" * 64,
    }
    lines = [
        f"TRACE_CONFIG path=pipe group=7 first_offset=1792 lines=4 "
        f"warmups=16 replay={preview} mode={mode}",
        f"TRACE_HEADER path=pipe group=7 warmups=16 start=1000 launch=1010 "
        f"entry=1100 after_load=1200 returned=1300 wake_to_entry=90 "
        f"load_cycles={load_cycles} wake_to_load={90 + load_cycles} "
        f"i_count=0 d_count={len(cycles)} i_overflow=0 d_overflow=0 armed=0 "
        "status=0x4",
    ]
    for index, (offset, cycle) in enumerate(zip(
            (0x700, 0x740, 0x780, 0x7c0), cycles)):
        lines.append(
            f"TRACE_RECORD seq={index} side=D index={index} cycle={cycle} "
            f"relative={cycle - 1000} message=0x0 "
            f"paddr=0x080000{offset:03x} raw=0x0"
        )
    lines.extend((f"TRACE_PASS records={len(cycles)} elapsed=200",
                  "CORE PASS", "BSG PASS"))
    path.write_text("\n".join(lines) + "\n")
    status = {
        "status": "PASS",
        **identity,
        "program": "physical-preview-pipe",
        "group": 7,
        "preview_mode": preview,
        "runner_exit": 0,
    }
    path.with_suffix(path.suffix + ".status.json").write_text(
        json.dumps(status) + "\n"
    )


class TracePairTest(unittest.TestCase):
    def test_target_demand_timing_and_load_delta(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            disabled = root / "disabled.log"
            enabled = root / "enabled.log"
            write_trace(disabled, "disabled", 0, 215, (1110, 1140, 1170, 1190))
            write_trace(
                enabled, "wake-early-data", 1, 183,
                (1120, 1145, 1170, 1195),
            )
            result = compare(disabled, enabled)
        self.assertEqual(result["load_cycles_enabled_minus_disabled"], -32)
        self.assertEqual(
            [row["cycles_after_entry"]
             for row in result["enabled"]["target_demand"]],
            [20, 45, 70, 95],
        )
        self.assertEqual(result["enabled"]["target_records_before_entry"], 0)

    def test_candidate_can_require_completed_target_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            disabled = root / "disabled.log"
            enabled = root / "enabled.log"
            write_trace(disabled, "disabled", 0, 215,
                        (1110, 1140, 1170, 1190))
            write_trace(enabled, "wake-early-data", 1, 12, ())
            result = compare(disabled, enabled, enabled_demand_count=0)
            self.assertEqual(
                result["enabled"]["target_demand_miss_count"], 0
            )
            self.assertIsNone(
                result["enabled"]["target_records_before_entry"]
            )
            with self.assertRaisesRegex(ValueError, "expected 4"):
                compare(disabled, enabled)


if __name__ == "__main__":
    unittest.main()
