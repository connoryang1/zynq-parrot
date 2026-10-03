#!/usr/bin/env python3
"""Analyze the retained physical-cycle samples from the scheduler probe."""
import json
import random
import re
import statistics
from pathlib import Path

root = Path(__file__).resolve().parent
samples = {}
for line in (root / "board.log").read_text(errors="replace").splitlines():
    match = re.search(r"SAMPLES metric=(\S+) (.*)$", line)
    if match:
        samples[match.group(1)] = [int(value) for value in match.group(2).split()]

expected = {
    "cycle_read_pair", "gettid_syscall", "sched_yield_no_user_peer",
    "handoff_to_main", "handoff_to_worker",
}
assert samples.keys() == expected
assert all(len(values) == 512 for values in samples.values())

rng = random.Random(20261003)

def bootstrap_median_difference(left, right, draws=100_000):
    differences = []
    for _ in range(draws):
        left_median = statistics.median(rng.choices(left, k=len(left)))
        right_median = statistics.median(rng.choices(right, k=len(right)))
        differences.append(left_median - right_median)
    differences.sort()
    return {
        "draws": draws,
        "median": statistics.median(differences),
        "ci95": [differences[int(draws * 0.025)], differences[int(draws * 0.975)]],
    }

medians = {name: statistics.median(values) for name, values in samples.items()}
result = {
    "samples_per_metric": 512,
    "medians_physical_cycles": medians,
    "derived_physical_cycles": {
        "gettid_minus_counter": medians["gettid_syscall"] - medians["cycle_read_pair"],
        "no_peer_yield_minus_counter": medians["sched_yield_no_user_peer"] - medians["cycle_read_pair"],
        "yield_scheduler_path_beyond_gettid": medians["sched_yield_no_user_peer"] - medians["gettid_syscall"],
        "handoff_to_main_beyond_no_peer_yield": medians["handoff_to_main"] - medians["sched_yield_no_user_peer"],
        "handoff_to_worker_beyond_no_peer_yield": medians["handoff_to_worker"] - medians["sched_yield_no_user_peer"],
    },
    "independent_bootstrap_difference_of_medians": {
        "main_handoff_minus_no_peer_yield": bootstrap_median_difference(
            samples["handoff_to_main"], samples["sched_yield_no_user_peer"]),
        "worker_handoff_minus_no_peer_yield": bootstrap_median_difference(
            samples["handoff_to_worker"], samples["sched_yield_no_user_peer"]),
    },
    "interpretation_limit": (
        "Differences are matched-path bounds, not instruction-level kernel attribution. "
        "The handoff delta includes task selection, switch_to, and return through the alternate thread."
    ),
}
(root / "analysis.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
