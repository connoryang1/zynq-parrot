#!/usr/bin/env python3
"""Compare direct U-mode context handoffs with the matched Linux scheduler data."""
import json
import re
import statistics
from pathlib import Path

evidence = Path(__file__).resolve().parent
repo = evidence.parents[1]
text = (evidence / "board.log").read_text(errors="replace").replace("\r", "")

def raw_cycles(name):
    match = re.search(rf"^{name} raw cycles \(256 switches each\):(.*)$", text, re.MULTILINE)
    assert match
    values = [int(value) for value in match.group(1).split()]
    assert len(values) == 128
    return values

resident = raw_cycles("resident")
nonresident = raw_cycles("nonresident")
scheduler = json.loads((repo / "logs/linux-hot-scheduler-breakdown-20261003/analysis.json").read_text())
scheduler_medians = scheduler["medians_physical_cycles"]
resident_per_switch = statistics.median(resident) / 256
nonresident_per_switch = statistics.median(nonresident) / 256

result = {
    "aggregate_samples_per_mode": 128,
    "switches_per_aggregate": 256,
    "total_timed_switches": 128 * 256 * 2,
    "direct_handoff_physical_cycles": {
        "resident_median_per_switch": resident_per_switch,
        "nonresident_median_per_switch": nonresident_per_switch,
        "resident_aggregate_min_median_max": [min(resident), statistics.median(resident), max(resident)],
        "nonresident_aggregate_min_median_max": [min(nonresident), statistics.median(nonresident), max(nonresident)],
        "resident_aggregates_over_2x_median": sum(value > 2 * statistics.median(resident) for value in resident),
        "nonresident_aggregates_over_2x_median": sum(value > 2 * statistics.median(nonresident) for value in nonresident),
    },
    "linux_handoff_medians_physical_cycles": {
        "to_main": scheduler_medians["handoff_to_main"],
        "to_worker": scheduler_medians["handoff_to_worker"],
        "no_peer_yield": scheduler_medians["sched_yield_no_user_peer"],
    },
    "linux_over_direct_latency_ratio": {
        "handoff_to_main_over_resident": scheduler_medians["handoff_to_main"] / resident_per_switch,
        "handoff_to_worker_over_resident": scheduler_medians["handoff_to_worker"] / resident_per_switch,
        "handoff_to_main_over_nonresident": scheduler_medians["handoff_to_main"] / nonresident_per_switch,
        "handoff_to_worker_over_nonresident": scheduler_medians["handoff_to_worker"] / nonresident_per_switch,
        "no_peer_yield_over_resident": scheduler_medians["sched_yield_no_user_peer"] / resident_per_switch,
        "no_peer_yield_over_nonresident": scheduler_medians["sched_yield_no_user_peer"] / nonresident_per_switch,
    },
    "scope": (
        "Direct measurements are hot assembly rings within one Linux process. "
        "They include loop overhead and asynchronous interrupts but exclude runtime policy, "
        "context ownership, wakeup bookkeeping, and cross-address-space switching."
    ),
}
(evidence / "analysis.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
