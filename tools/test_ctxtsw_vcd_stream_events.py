#!/usr/bin/env python3
"""Check context ownership reporting against small current and historical VCDs."""

from pathlib import Path
import subprocess
import sys
import unittest


ANALYZER = Path(__file__).with_name("ctxtsw_vcd_stream_events.py")


def waveform(historical=False, target_wire=False):
    """Create one dispatch and one commit with deliberately different IDs."""
    signals = [
        ("scheduler.dispatch_pkt_cast_o.v", 1, 1),
        ("scheduler.dispatch_pkt_cast_o.pc", 39, 0x80000000),
        ("scheduler.dispatch_pkt_cast_o.thread_id", 1, 1),
        ("scheduler.dispatch_pkt_cast_o.ctxtsw_v", 1, 1),
        ("ctxtsw_target_virtual_context_id_li" if target_wire else
         "scheduler.dispatch_pkt_cast_o.ctxtsw_target_tid", 2, 2),
        ("calculator.commit_pkt_cast_o.ctxtsw", 1, 1),
        ("context_cache_state_r", 4, 1),
        ("context_cache_miss_v_li", 1, 1),
        ("context_cache_miss_virtual_context_id_li", 2, 2),
        ("context_cache_target_virtual_context_id_r", 2, 2),
        ("context_cache_victim_virtual_context_id_r", 2, 3),
        ("current_physical_thread_id_lo", 1, 1),
        ("current_virtual_context_id_r", 2, 3),
    ]
    header = ["$timescale 1ps $end", "$scope module TOP $end",
              "$scope module be $end"]
    values = []
    for index, (name, width, value) in enumerate(signals):
        if historical:
            name = name.replace("virtual_context_id", "context_id")
            name = name.replace("physical_thread_id", "thread_id")
            name = name.replace("scheduler.dispatch_pkt_cast_o", "dispatch_pkt")
            name = name.replace("calculator.commit_pkt_cast_o", "commit_pkt")
        *scopes, leaf = name.split(".")
        header.extend(f"$scope struct {scope} $end" for scope in scopes)
        header.append(f"$var wire {width} s{index} {leaf} $end")
        header.extend("$upscope $end" for _ in scopes)
        values.append(f"b{value:b} s{index}")
    return "\n".join(header + ["$upscope $end", "$upscope $end",
                              "$enddefinitions $end", "#0", "$dumpvars"]
                     + values + ["$end", "#50000", ""])


class ContextOwnershipTests(unittest.TestCase):
    def check_ownership(self, **trace_options):
        result = subprocess.run(
            [sys.executable, str(ANALYZER), "--pc", "0x80000000"],
            input=waveform(**trace_options), text=True, capture_output=True,
            check=True,
        )
        self.assertIn("dispatch pc=0x80000000 tid=1 ctxtsw=1 target_ctx=2",
                      result.stdout)
        self.assertIn("cache_state=1 current_ctx=3 current_tid=1 miss=1"
                      " miss_ctx=2 target_ctx=2 victim_ctx=3", result.stdout)
        self.assertIn("commit_ctxtsw cache_state=1 current=1/3", result.stdout)
        self.assertEqual(result.stdout.count(" dispatch "), 1)

    def test_current_packet_names(self):
        self.check_ownership()

    def test_current_logical_target_wire(self):
        self.check_ownership(target_wire=True)

    def test_historical_packet_names(self):
        self.check_ownership(historical=True)


if __name__ == "__main__":
    unittest.main()
