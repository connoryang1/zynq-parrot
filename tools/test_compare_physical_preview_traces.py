"""Validate exact selected-line comparison for physical-preview traces."""

import json
import tempfile
import unittest
from pathlib import Path

from compare_physical_preview_traces import compare


class PhysicalPreviewTraceComparisonTest(unittest.TestCase):
    def write_trace(self, path, instruction_addresses):
        records = [
            "TRACE_RECORD seq={} side=I index={} cycle={} relative={} "
            "message=0x0 paddr=0x{:09x} raw=0x0".format(
                index, index, 100 + index, index, address
            )
            for index, address in enumerate(instruction_addresses)
        ]
        path.write_text(
            "TRACE_HEADER path=pipe wake_to_entry=20 load_cycles=4 "
            "wake_to_load=24 i_count={} d_count=0 i_overflow=0 "
            "d_overflow=0 armed=0\n{}\nTRACE_PASS records={} elapsed=24\n".format(
                len(records), "\n".join(records), len(records)
            )
        )

    def test_selected_lines_disappear_only_from_enabled_demand_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            disabled = root / "disabled.log"
            enabled = root / "enabled.log"
            selection = root / "selection.json"
            self.write_trace(disabled, [0x80000000, 0x80000040])
            self.write_trace(enabled, [0x80000100])
            selection.write_text(json.dumps({
                "fixed_shared_prefix": {
                    "lines": [
                        {"rank": 0, "paddr": 0x80000000},
                        {"rank": 1, "paddr": 0x80000040},
                    ]
                }
            }))
            result = compare(disabled, enabled, selection)
            self.assertEqual(
                result["selected_summary"]["removed_from_demand_stream"], 2
            )
            self.assertTrue(
                result["selected_summary"]["all_selected_absent_enabled"]
            )

    def test_incomplete_trace_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / "bad.log"
            selection = root / "selection.json"
            trace.write_text(
                "TRACE_HEADER wake_to_entry=1 load_cycles=1 wake_to_load=2 "
                "i_count=1 d_count=0 i_overflow=0 d_overflow=0 armed=0\n"
                "TRACE_FAIL incomplete\n"
            )
            selection.write_text(json.dumps({
                "fixed_shared_prefix": {"lines": []}
            }))
            with self.assertRaisesRegex(ValueError, "did not pass"):
                compare(trace, trace, selection)


if __name__ == "__main__":
    unittest.main()
