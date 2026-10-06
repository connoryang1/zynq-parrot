#!/usr/bin/env python3
"""Bound aggregate I+D cold-resume replay against measured machine rates."""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHED = ROOT / "logs/linux-scheduler-resume-20261002/results.json"
INSTALL = ROOT / "logs/prefetch-sustained-coverage-20260924/final-trace/k10-m2/final-installer-audit.json"


def transport_cycles(lines, slots, latency, beats_per_line):
    # Optimistic work-conserving lower bound with a finite latency window and
    # one shared AXI R channel. Include the first-request latency and final burst.
    interval = max(float(beats_per_line), float(latency) / slots)
    return latency + max(0, lines - 1) * interval + beats_per_line


def main():
    sched = json.loads(SCHED.read_text())
    install = json.loads(INSTALL.read_text())
    derived = sched["derived_pooled_medians"]
    i_eq = sched["ifetch_sweep_refill_equivalents"]["by_footprint"]["32k"]["line_equivalents"]
    d_eq = sched["clean_data_sweep_refill_equivalents"]["by_footprint"]["128k"]["line_equivalents"]

    # Ceiling is intentionally conservative because the source values are
    # serialized-latency equivalents rather than literal miss counts.
    kernel_i_lines = math.ceil(i_eq)
    kernel_d_lines = math.ceil(d_eq)
    application_d_lines = 160
    install_cycles = install["max_install_cycles"]
    deadline = derived["yield_combined_hot_resume_cycles"]
    line_bytes = 64
    axi_bytes_per_beat = 8
    beats_per_line = line_bytes // axi_bytes_per_beat
    clock_hz = 18_000_000

    scenarios = {
        "kernel_only": {
            "i_lines": kernel_i_lines,
            "d_lines": kernel_d_lines,
        },
        "kernel_plus_application": {
            "i_lines": kernel_i_lines,
            "d_lines": kernel_d_lines + application_d_lines,
        },
    }

    for scenario in scenarios.values():
        total = scenario["i_lines"] + scenario["d_lines"]
        scenario["total_lines"] = total
        scenario["separate_install_completion_cycles"] = {
            str(latency): latency + beats_per_line
            + max(scenario["i_lines"], scenario["d_lines"]) * install_cycles
            for latency in (21, 41)
        }
        scenario["shared_install_completion_cycles"] = {
            str(latency): latency + beats_per_line + total * install_cycles
            for latency in (21, 41)
        }
        scenario["slot_sweep"] = {}
        for latency in (21, 41):
            rows = {}
            for slots in (1, 2, 3, 4, 5, 10):
                transport = transport_cycles(total, slots, latency, beats_per_line)
                separate_install = latency + beats_per_line \
                    + max(scenario["i_lines"], scenario["d_lines"]) * install_cycles
                completion = max(transport, separate_install)
                rows[str(slots)] = {
                    "transport_lower_bound_cycles": transport,
                    "separate_install_bound_cycles": separate_install,
                    "aggregate_completion_bound_cycles": completion,
                    "margin_to_hot_resume_cycles": deadline - completion,
                    "fits_hot_resume": completion <= deadline,
                }
            scenario["slot_sweep"][str(latency)] = rows

    total_lines = scenarios["kernel_plus_application"]["total_lines"]
    result = {
        "method": (
            "Aggregate feasibility bound. Convert measured Linux instruction/data penalties to "
            "conservative ceiling line-equivalents, add the measured 160-line application point, "
            "then bound a shared 64-bit AXI response channel and separate I/D cache installers."
        ),
        "inputs": {
            "scheduler_results": str(SCHED.relative_to(ROOT)),
            "installer_audit": str(INSTALL.relative_to(ROOT)),
            "hot_combined_resume_deadline_cycles": deadline,
            "instruction_line_equivalents": i_eq,
            "data_line_equivalents": d_eq,
            "kernel_instruction_lines_ceiling": kernel_i_lines,
            "kernel_data_lines_ceiling": kernel_d_lines,
            "application_data_lines": application_d_lines,
            "max_data_install_cycles_per_line": install_cycles,
            "line_bytes": line_bytes,
            "axi_bytes_per_beat": axi_bytes_per_beat,
            "clock_hz": clock_hz,
            "latency_endpoint": (
                "conditional request-to-first-response-beat scenario; the physical "
                "41-cycle measurement is critical load-to-use, not a measured full-line endpoint"
            ),
        },
        "scenarios": scenarios,
        "derived": {
            "kernel_plus_application_required_rate_MBps": total_lines * line_bytes * clock_hz / deadline / 1e6,
            "raw_64bit_axi_rate_MBps": axi_bytes_per_beat * clock_hz / 1e6,
            "four_slot_41cycle_projected_rate_MBps": (
                total_lines * line_bytes * clock_hz
                / scenarios["kernel_plus_application"]["slot_sweep"]["41"]["4"]["aggregate_completion_bound_cycles"]
                / 1e6
            ),
            "minimum_slots_at_41cycle_latency": next(
                slots
                for slots in (1, 2, 3, 4, 5, 10)
                if scenarios["kernel_plus_application"]["slot_sweep"]["41"][str(slots)]["fits_hot_resume"]
            ),
        },
        "limits": [
            "The instruction/data line values are refill-latency equivalents, not measured miss addresses or exact counts.",
            "The AXI calculation is a work-conserving lower bound and does not model DDR scheduling, arbitration bubbles, or useful-line ordering.",
            "Seventeen cycles is measured for the data-cache installer; an equivalent instruction-cache replay installer does not exist yet.",
            "All lines are required by first user dispatch in this deliberately strict bound; real deadlines are per-line and order dependent.",
            "Translation replay, dirty writebacks, capacity replacement, and scheduler-generated traffic are excluded.",
            "The 21/41-cycle latency scenarios are not physical measurements of detached 64-byte request-to-first-beat service.",
        ],
    }
    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
