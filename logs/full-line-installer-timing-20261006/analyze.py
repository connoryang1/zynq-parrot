#!/usr/bin/env python3
"""Measure full-line installer active intervals from retained VCDs."""

import collections
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUTS = {
    "direct_installer": ROOT
    / "logs/prefetch-sustained-coverage-20260924/final-trace/k10-m2/final-installer.vcd",
    "concurrent_response_buffer": ROOT
    / "logs/clock-pipeline-20260929/full-line-lat40-sweep-120/fill-buffer-concurrent"
    / "trace-k3-m3-n33/analysis/installer.vcd",
}
BANKED_MINIMAL = ROOT / "logs/banked-full-line-timing-20261006/results.json"
BANKED_MAIN64 = ROOT / "logs/banked-full-line-timing-20261006/results-main64.json"


def measure(path):
    state_id = None
    clock_ids = set()
    definitions_done = False
    timestamp = None
    state = None
    state_changes = []
    rising_edges = []
    clock_values = {}

    for line in path.read_text().splitlines():
        if not definitions_done:
            if line.startswith("$var"):
                parts = line.split()
                identifier = parts[3]
                name = parts[4]
                if name == "prefetch_install_state_r":
                    state_id = identifier
                if name == "clk_i":
                    clock_ids.add(identifier)
            elif line.startswith("$enddefinitions"):
                definitions_done = True
            continue
        if line.startswith("#"):
            timestamp = int(line[1:])
            continue
        if timestamp is None:
            continue
        if line.startswith("b"):
            bits, identifier = line.split()
            if identifier == state_id:
                value = int(bits[1:], 2)
                if value != state:
                    state_changes.append((timestamp, value))
                    state = value
            continue
        value, identifier = line[0], line[1:]
        if identifier in clock_ids and value in "01":
            old = clock_values.get(identifier)
            clock_values[identifier] = value
            if value == "1" and old == "0":
                rising_edges.append(timestamp)

    if state_id is None or len(rising_edges) < 2:
        raise ValueError(f"{path}: missing state or clock")
    clock_period = int(statistics.median(
        b - a for a, b in zip(rising_edges, rising_edges[1:]) if b > a
    ))
    starts = []
    intervals = []
    for when, value in state_changes:
        if value != 0 and (not starts or starts[-1][1] is not None):
            starts.append([when, None])
        if value == 0 and starts and starts[-1][1] is None:
            starts[-1][1] = when
            intervals.append((when - starts[-1][0]) / clock_period)
    counts = collections.Counter(intervals)
    return {
        "path": str(path.relative_to(ROOT)),
        "clock_period_vcd_ticks": clock_period,
        "installations": len(intervals),
        "cycles": intervals,
        "distribution": {str(int(k)): v for k, v in sorted(counts.items())},
        "minimum_cycles": min(intervals),
        "median_cycles": statistics.median(intervals),
        "mean_cycles": statistics.mean(intervals),
        "maximum_cycles": max(intervals),
    }


def main():
    banked_minimal = json.loads(BANKED_MINIMAL.read_text())
    banked_main64 = json.loads(BANKED_MAIN64.read_text())
    implementations = {name: measure(path) for name, path in INPUTS.items()}
    implementations["banked_minimal_32bit"] = {
        "path": str(BANKED_MINIMAL.relative_to(ROOT)),
        "benchmark_cycles": banked_minimal["window"]["cycles"],
        **banked_minimal["latency_cycles"]["installer_active"],
    }
    implementations["banked_full_64bit"] = {
        "path": str(BANKED_MAIN64.relative_to(ROOT)),
        "benchmark_cycles": banked_main64["window"]["cycles"],
        **banked_main64["latency_cycles"]["installer_active"],
    }
    result = {
        "method": (
            "Count core-clock cycles from prefetch_install_state_r leaving idle "
            "until it returns to idle in retained accepted waveforms; import the "
            "independently decoded banked-wrapper traces."
        ),
        "implementations": implementations,
        "limits": [
            "All measurements are RTL simulation waveforms, not physical FPGA timing.",
            "The 32-bit minimal wrapper is a test harness; the FPGA-facing full wrapper is 64 bits.",
            "Only the data-cache installer exists; an instruction-cache replay installer is projected.",
        ],
    }
    text = json.dumps(result, indent=2) + "\n"
    Path(__file__).with_name("results.json").write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
