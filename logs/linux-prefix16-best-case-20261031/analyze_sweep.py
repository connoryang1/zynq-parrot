#!/usr/bin/env python3
"""Summarize the accepted larger-prefix and post-trigger-tail FPGA batches."""

import hashlib
import json
import random
import re
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SAMPLED_HEADER = re.compile(
    r"^SAMPLE=(\d+)\s+TRACE_HEADER .*?elapsed=(\d+) i_count=(\d+)"
    r" d_count=(\d+) i_overflow=(\d+)",
    re.MULTILINE,
)


def sampled_batch(name):
    path = ROOT / name
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    rows = [tuple(map(int, match)) for match in SAMPLED_HEADER.findall(text)]
    if [row[0] for row in rows] != list(range(1, 51)):
        raise SystemExit(f"{name}: expected numbered samples 1--50, found {len(rows)}")
    elapsed = [row[1] for row in rows]
    icount = [row[2] for row in rows]
    dcount = [row[3] for row in rows]
    quartiles = statistics.quantiles(elapsed, n=4, method="inclusive")
    return {
        "path": name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "samples": len(rows),
        "elapsed": elapsed,
        "median": statistics.median(elapsed),
        "mean": statistics.mean(elapsed),
        "q1": quartiles[0],
        "q3": quartiles[2],
        "minimum": min(elapsed),
        "maximum": max(elapsed),
        "i_count_median": statistics.median(icount),
        "i_count_mean": statistics.mean(icount),
        "d_count_median": statistics.median(dcount),
        "d_count_mean": statistics.mean(dcount),
        "i_overflows": sum(row[4] for row in rows),
    }


def bootstrap(first, second, seed, resamples=100_000):
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
        "fraction_first_faster": sum(value < 0 for value in differences) / resamples,
    }


original = json.loads((ROOT / "results.json").read_text())
disabled = [
    value
    for replicate in original["replicates"]
    for value in replicate["disabled"]["elapsed"]
]
prefix16 = [
    value
    for replicate in original["replicates"]
    for value in replicate["prefix16"]["elapsed"]
]
prefix8 = sampled_batch("prefix8-summary50.log")
tail14 = sampled_batch("prefix14-tail-summary50.log")


def comparison(batch, control, seed):
    return {
        "median_difference": batch["median"] - statistics.median(control),
        "median_ratio": batch["median"] / statistics.median(control),
        "bootstrap": bootstrap(batch["elapsed"], control, seed),
    }


result = {
    "purpose": (
        "Extend the accepted disabled/16-line comparison with an 8-line size point, "
        "a causally post-trigger 14-line table, and explicit rejected-run outcomes."
    ),
    "pooled_controls": {
        "disabled_samples": len(disabled),
        "disabled_median": statistics.median(disabled),
        "old_prefix16_samples": len(prefix16),
        "old_prefix16_median": statistics.median(prefix16),
    },
    "prefix8": {
        **prefix8,
        "versus_disabled": comparison(prefix8, disabled, 0x800),
        "versus_old_prefix16": comparison(prefix8, prefix16, 0x816),
    },
    "post_trigger_tail14": {
        **tail14,
        "versus_disabled": comparison(tail14, disabled, 0x1400),
        "versus_old_prefix16": comparison(tail14, prefix16, 0x1416),
    },
    "rejected_runs": {
        "prefix12": "target-runtime limit during guest ELF transfer; no timing samples",
        "prefix20": "errant physical write 0x17bea8 after four valid samples",
        "prefix32_first": "kernel init executables failed with error -80 before benchmark",
        "prefix32_retry": "guest prompt loss during ELF transfer; no timing samples",
    },
}

print(json.dumps(result, indent=2))
