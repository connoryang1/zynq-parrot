#!/usr/bin/env python3
"""Validate and summarize the fresh physical disabled/replay-enabled Linux A/B."""

import hashlib
import json
import random
import re
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SAMPLE = re.compile(
    r"^SAMPLE=(\d+)\s+TRACE_HEADER .*?elapsed=(\d+) i_count=(\d+)"
    r" d_count=(\d+) i_overflow=(\d+) d_overflow=(\d+)",
    re.MULTILINE,
)


def load(name):
    path = ROOT / "fpga" / name
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    rows = [tuple(map(int, match)) for match in SAMPLE.findall(text)]
    if [row[0] for row in rows] != list(range(1, 51)):
        raise SystemExit(f"{name}: expected numbered samples 1--50, found {len(rows)}")
    for marker in ("INFO:    CORE PASS", "Returning from ps_main with RC: 0", "INFO:    BSG PASS"):
        if marker not in text:
            raise SystemExit(f"{name}: missing terminal marker {marker!r}")
    elapsed = [row[1] for row in rows]
    quartiles = statistics.quantiles(elapsed, n=4, method="inclusive")
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "samples": len(rows),
        "elapsed": elapsed,
        "median": statistics.median(elapsed),
        "mean": statistics.mean(elapsed),
        "q1": quartiles[0],
        "q3": quartiles[2],
        "minimum": min(elapsed),
        "maximum": max(elapsed),
        "i_overflow_samples": sum(row[4] for row in rows),
        "d_overflow_samples": sum(row[5] for row in rows),
    }


def bootstrap(first, second, seed, resamples=100_000):
    """Return enabled-minus-disabled median uncertainty from independent boots."""
    rng = random.Random(seed)
    differences = []
    for _ in range(resamples):
        differences.append(
            statistics.median(rng.choices(first, k=len(first)))
            - statistics.median(rng.choices(second, k=len(second)))
        )
    differences.sort()
    return {
        "resamples": resamples,
        "difference_ci95": [differences[2_500], differences[97_499]],
        "fraction_enabled_faster": sum(value < 0 for value in differences) / resamples,
    }


enabled = load("prefix16-summary50.log")
disabled = load("disabled-summary50.log")
median_difference = enabled["median"] - disabled["median"]
result = {
    "purpose": (
        "Validate a fresh-board, exact-image physical comparison after completed-buffer "
        "residency suppression passed route, replay, and sustained Linux gates."
    ),
    "enabled_prefix16": enabled,
    "disabled": disabled,
    "comparison": {
        "median_difference_enabled_minus_disabled": median_difference,
        "median_ratio_enabled_over_disabled": enabled["median"] / disabled["median"],
        "point_reduction_percent": -100.0 * median_difference / disabled["median"],
        "bootstrap": bootstrap(enabled["elapsed"], disabled["elapsed"], 0xA556049E),
        "interpretation": (
            "The point estimate favors replay, but the independent-sample bootstrap "
            "interval crosses zero; this batch does not establish a speedup."
        ),
    },
}

print(json.dumps(result, indent=2))
