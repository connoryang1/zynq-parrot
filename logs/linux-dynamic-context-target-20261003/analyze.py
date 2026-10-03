#!/usr/bin/env python3
"""Analyze immediate and register-target context-switch samples."""
import json
import re
import statistics
from pathlib import Path

evidence = Path(__file__).resolve().parent
text = (evidence / "board.log").read_text(errors="replace").replace("\r", "")
names = ["immediate_resident", "immediate_nonresident",
         "register_resident", "register_nonresident"]
samples = {}
for name in names:
    match = re.search(rf"^{name} raw cycles \(256 switches each\):(.*)$", text, re.MULTILINE)
    assert match
    samples[name] = [int(value) for value in match.group(1).split()]
    assert len(samples[name]) == 128

medians = {name: statistics.median(values) / 256 for name, values in samples.items()}
result = {
    "aggregate_samples_per_mode": 128,
    "switches_per_aggregate": 256,
    "total_timed_handoffs": 4 * 128 * 256,
    "median_cycles_per_handoff": medians,
    "register_minus_immediate_cycles_per_handoff": {
        "resident": medians["register_resident"] - medians["immediate_resident"],
        "nonresident": medians["register_nonresident"] - medians["immediate_nonresident"],
    },
    "register_target_percent_overhead": {
        "resident": 100 * (medians["register_resident"] / medians["immediate_resident"] - 1),
        "nonresident": 100 * (medians["register_nonresident"] / medians["immediate_nonresident"] - 1),
    },
    "aggregate_min_median_max": {
        name: [min(values), statistics.median(values), max(values)]
        for name, values in samples.items()
    },
    "aggregates_over_2x_median": {
        name: sum(value > 2 * statistics.median(values) for value in values)
        for name, values in samples.items()
    },
    "scope": (
        "The register-target ID is already resident in a GPR before each timed ring. "
        "The result measures dynamic dispatch encoding and its register dependency, "
        "not the software policy needed to select a ready context."
    ),
}
(evidence / "analysis.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
