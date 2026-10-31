#!/usr/bin/env python3
"""Summarize matched disabled and 16-line Linux handoff timing batches."""

import json
import random
import re
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HEADER = re.compile(
    r"TRACE_HEADER .*?elapsed=(\d+) i_count=(\d+) d_count=(\d+)"
    r" i_overflow=(\d+)"
)


def read_batch(name):
    text = (ROOT / "raw" / name).read_text(errors="replace").replace("\x00", "")
    rows = [tuple(map(int, row)) for row in HEADER.findall(text)]
    if len(rows) != 50:
        raise SystemExit(f"{name}: expected 50 timing rows, found {len(rows)}")
    values = [row[0] for row in rows]
    icounts = [row[1] for row in rows]
    dcounts = [row[2] for row in rows]
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return {
        "samples": len(values),
        "elapsed": values,
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "q1": quartiles[0],
        "q3": quartiles[2],
        "minimum": min(values),
        "maximum": max(values),
        "i_count_median": statistics.median(icounts),
        "i_count_mean": statistics.mean(icounts),
        "d_count_median": statistics.median(dcounts),
        "d_count_mean": statistics.mean(dcounts),
        "i_overflows": sum(row[3] for row in rows),
    }


disabled = [
    read_batch("disabled-matched-summary50.log"),
    read_batch("disabled-rotated-summary50.log"),
]
prefix16 = [
    read_batch("conditional-prefix16-summary50.log"),
    read_batch("conditional-prefix16-rotated-summary50.log"),
]


def bootstrap_difference(enabled, control, rng, resamples=100_000):
    differences = []
    for _ in range(resamples):
        enabled_sample = rng.choices(enabled, k=len(enabled))
        control_sample = rng.choices(control, k=len(control))
        differences.append(statistics.median(enabled_sample)
                           - statistics.median(control_sample))
    differences.sort()
    return {
        "resamples": resamples,
        "difference_ci95": [differences[2_500], differences[97_499]],
        "fraction_enabled_faster": sum(value < 0 for value in differences) / resamples,
    }


rng = random.Random(0x16CACE)
replicate_bootstrap = [
    bootstrap_difference(prefix16[index]["elapsed"], disabled[index]["elapsed"], rng)
    for index in range(2)
]
pooled_disabled = disabled[0]["elapsed"] + disabled[1]["elapsed"]
pooled_prefix16 = prefix16[0]["elapsed"] + prefix16[1]["elapsed"]
pooled_bootstrap = bootstrap_difference(pooled_prefix16, pooled_disabled, rng)

stratified_differences = []
for _ in range(100_000):
    replicate_differences = []
    for index in range(2):
        enabled_sample = rng.choices(prefix16[index]["elapsed"], k=50)
        control_sample = rng.choices(disabled[index]["elapsed"], k=50)
        replicate_differences.append(statistics.median(enabled_sample)
                                     - statistics.median(control_sample))
    stratified_differences.append(statistics.mean(replicate_differences))
stratified_differences.sort()

result = {
    "purpose": "Compare a 16-line trace-derived instruction prefix with replay disabled on the same routed FPGA, kernel, and benchmark ELF.",
    "replicates": [
        {
            "disabled": disabled[index],
            "prefix16": prefix16[index],
            "enabled_minus_disabled_median": prefix16[index]["median"] - disabled[index]["median"],
            "enabled_over_disabled_ratio": prefix16[index]["median"] / disabled[index]["median"],
            "bootstrap": replicate_bootstrap[index],
        }
        for index in range(2)
    ],
    "pooled": {
        "disabled_median": statistics.median(pooled_disabled),
        "prefix16_median": statistics.median(pooled_prefix16),
        "enabled_minus_disabled_median": statistics.median(pooled_prefix16) - statistics.median(pooled_disabled),
        "enabled_over_disabled_ratio": statistics.median(pooled_prefix16) / statistics.median(pooled_disabled),
        "bootstrap": pooled_bootstrap,
    },
    "stratified_bootstrap": {
        "estimand": "mean of the two replicate median differences",
        "point_estimate": statistics.mean(prefix16[index]["median"] - disabled[index]["median"] for index in range(2)),
        "resamples": len(stratified_differences),
        "seed": "0x16cace",
        "difference_ci95": [stratified_differences[2_500], stratified_differences[97_499]],
        "fraction_enabled_faster": sum(value < 0 for value in stratified_differences) / len(stratified_differences),
    },
}

print(json.dumps(result, indent=2))
