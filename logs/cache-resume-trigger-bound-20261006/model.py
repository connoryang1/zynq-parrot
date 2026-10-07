#!/usr/bin/env python3
"""Bound replay coverage as a function of when the incoming context is known."""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH_RESULT = ROOT / "logs/cache-resume-shared-path-bound-20261006/results.json"
SCHED_RESULT = ROOT / "logs/linux-hot-scheduler-breakdown-20261003/analysis.json"


def max_transport_lines(window, slots, latency, beats_per_line):
    if window < latency + beats_per_line:
        return 0
    interval = max(float(beats_per_line), float(latency) / slots)
    return 1 + math.floor((window - latency - beats_per_line) / interval)


def main():
    path = json.loads(PATH_RESULT.read_text())
    sched = json.loads(SCHED_RESULT.read_text())
    inputs = path["inputs"]
    full = path["scenarios"]["kernel_plus_application"]
    kernel = path["scenarios"]["kernel_only"]

    latency = 41
    slots = 4
    beats_per_line = inputs["line_bytes"] // inputs["axi_bytes_per_beat"]
    install_cycles = inputs["banked_full64_installer_median_cycles"]
    hot_deadline = inputs["hot_combined_resume_deadline_cycles"]
    late_windows = sched["derived_physical_cycles"]
    generous_late_window = max(
        late_windows["handoff_to_main_beyond_no_peer_yield"],
        late_windows["handoff_to_worker_beyond_no_peer_yield"],
    )
    full_completion = max(
        full["slot_sweep"][str(latency)][str(slots)]["transport_lower_bound_cycles"],
        latency + beats_per_line + max(full["i_lines"], full["d_lines"]) * install_cycles,
    )
    kernel_completion = max(
        kernel["slot_sweep"][str(latency)][str(slots)]["transport_lower_bound_cycles"],
        latency + beats_per_line + max(kernel["i_lines"], kernel["d_lines"]) * install_cycles,
    )

    windows = {
        "yield_entry_to_hot_dispatch": hot_deadline,
        "generous_selection_switch_return_delta": generous_late_window,
        "worker_selection_switch_return_delta": late_windows["handoff_to_worker_beyond_no_peer_yield"],
        "resident_handoff_5_13": 5.13,
        "nonresident_handoff_9_26": 9.26,
    }
    coverage = {}
    for name, window in windows.items():
        transport = max_transport_lines(window, slots, latency, beats_per_line)
        per_cache_install = max(
            0, math.floor((window - latency - beats_per_line) / install_cycles)
        )
        two_cache_install = 2 * per_cache_install
        maximum = min(transport, two_cache_install)
        coverage[name] = {
            "window_cycles": window,
            "transport_line_capacity": transport,
            "per_cache_install_line_capacity": per_cache_install,
            "two_cache_install_line_capacity": two_cache_install,
            "aggregate_mixed_line_capacity": maximum,
            "fraction_of_479_line_target": maximum / full["total_lines"],
            "fraction_of_319_line_kernel_target": maximum / kernel["total_lines"],
        }

    result = {
        "method": (
            "Apply the conditional four-slot, 41-cycle shared-transport and separate measured-median 19-cycle I/D install bound "
            "to measured trigger windows. The Linux late-trigger window is deliberately generous: "
            "the whole alternate-thread delta is credited even though it includes task selection."
        ),
        "inputs": {
            "shared_path_results": str(PATH_RESULT.relative_to(ROOT)),
            "scheduler_breakdown": str(SCHED_RESULT.relative_to(ROOT)),
            "latency_cycles": latency,
            "outstanding_slots": slots,
            "beats_per_line": beats_per_line,
            "install_cycles_per_line": install_cycles,
            "full_target_lines": full["total_lines"],
            "kernel_target_lines": kernel["total_lines"],
            "hot_dispatch_deadline_cycles": hot_deadline,
            "full_target_completion_cycles": full_completion,
            "kernel_target_completion_cycles": kernel_completion,
        },
        "derived": {
            "latest_full_target_trigger_after_yield_entry_cycles": hot_deadline - full_completion,
            "latest_kernel_target_trigger_after_yield_entry_cycles": hot_deadline - kernel_completion,
            "late_trigger_max_lines": coverage["generous_selection_switch_return_delta"]["aggregate_mixed_line_capacity"],
            "late_trigger_full_target_shortfall_lines": full["total_lines"] - coverage["generous_selection_switch_return_delta"]["aggregate_mixed_line_capacity"],
        },
        "coverage": coverage,
        "limits": [
            "The alternate-thread delta is not a measured timestamp of task selection; treating all of it as post-selection replay time is an optimistic upper bound.",
            "Line capacities do not imply usefulness because actual miss addresses, order, and deadlines are unknown.",
            "The input line targets are refill-latency equivalents, not exact miss counts.",
            "The model excludes translation, dirty victims, capacity replacement, and arbitration bubbles.",
            "The 41-cycle scenario is not a measured detached full-line endpoint; physical demand load-to-use only supplies a proxy.",
            "The 17-cycle input is a direct-path sensitivity point; the primary banked FPGA-facing result uses its measured 19-cycle median and observes a 25-cycle maximum.",
            "The primary capacity rows use the FPGA-facing banked path's 19-cycle median; its observed 25-cycle maximum would be slower.",
        ],
    }
    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
