#!/usr/bin/env python3
"""Summarize completed instruction/data cache-state upper bounds."""

import argparse
import json
import random
import re
import statistics
from pathlib import Path


ROW = re.compile(
    r"COMBINED_ORACLE trial=(\d+) mode=(\d+) prep_cost=(\d+) "
    r"wake_to_entry=(\d+) code_cycles=(\d+) data_cycles=(\d+) "
    r"useful_cycles=(\d+) wake_to_useful=(\d+) roundtrip=(\d+)"
)
FAULT = re.compile(r"COMBINED_ORACLE_FAULTS faults=(\d+)")
PATTERN = (0, 3, 1, 2, 2, 1, 3, 0)
MODE_NAMES = {0: "cold", 1: "instruction", 2: "data", 3: "combined"}
METRICS = ("wake_to_entry", "code_cycles", "data_cycles", "useful_cycles",
           "wake_to_useful", "roundtrip")


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[round(fraction * (len(ordered) - 1))]


def expected_mode(trial, schedule="rotated"):
    if schedule == "fixed":
        return PATTERN[trial & 7]
    original_trial = trial + 8
    return (PATTERN[original_trial & 7] + (original_trial >> 3)) & 3


def paired_comparison(rows, metric, alternative, rng):
    blocks = []
    for start in range(0, 256, 8):
        block = rows[start:start + 8]
        cold = [row[metric] for row in block if row["mode"] == 0]
        alt = [row[metric] for row in block if row["mode"] == alternative]
        blocks.append(statistics.mean(cold) - statistics.mean(alt))
    estimate = statistics.median(blocks)
    boots = [statistics.median(rng.choices(blocks, k=32))
             for _ in range(20000)]
    return {
        "paired_median_saved_cycles": estimate,
        "paired_95pct_ci_saved_cycles": [percentile(boots, 0.025),
                                           percentile(boots, 0.975)],
    }


def summarize(text, schedule="rotated"):
    for marker in ("COMBINED_ORACLE_CHILD PASS", "COMBINED_ORACLE_PARENT PASS",
                   "INFO:    CORE PASS", "INFO:    BSG PASS"):
        if marker not in text:
            raise ValueError(f"missing marker: {marker}")
    faults = [int(match.group(1)) for match in FAULT.finditer(text)]
    if faults != [0]:
        raise ValueError(f"expected one zero measured-fault count, got {faults}")

    rows = []
    for match in ROW.finditer(text):
        values = [int(value) for value in match.groups()]
        rows.append({
            "trial": values[0], "mode": values[1], "prep_cost": values[2],
            "wake_to_entry": values[3], "code_cycles": values[4],
            "data_cycles": values[5], "useful_cycles": values[6],
            "wake_to_useful": values[7], "roundtrip": values[8],
        })
    if len(rows) != 256 or [row["trial"] for row in rows] != list(range(256)):
        raise ValueError("expected exactly 256 ordered measured trials")
    for start in range(0, 256, 8):
        modes = tuple(row["mode"] for row in rows[start:start + 8])
        expected = tuple(expected_mode(trial, schedule)
                         for trial in range(start, start + 8))
        if modes != expected:
            raise ValueError(f"unbalanced trial block at {start}: {modes}")
    for row in rows:
        if row["code_cycles"] + row["data_cycles"] != row["useful_cycles"]:
            raise ValueError(f"inconsistent useful timing at trial {row['trial']}")
        if row["wake_to_entry"] + row["useful_cycles"] != row["wake_to_useful"]:
            raise ValueError(f"inconsistent wake timing at trial {row['trial']}")
        if row["wake_to_useful"] > row["roundtrip"]:
            raise ValueError(f"roundtrip ended before useful work at trial {row['trial']}")

    rng = random.Random(0x1DDA7A)
    metrics = {}
    for metric in METRICS:
        medians = {
            MODE_NAMES[mode]: statistics.median(
                row[metric] for row in rows if row["mode"] == mode
            ) for mode in MODE_NAMES
        }
        comparisons = {
            MODE_NAMES[mode]: paired_comparison(rows, metric, mode, rng)
            for mode in (1, 2, 3)
        }
        comparisons["combined"]["median_ratio_cold_over_combined"] = (
            medians["cold"] / medians["combined"]
        )
        metrics[metric] = {
            "median_cycles_by_mode": medians,
            "cold_minus_mode": comparisons,
        }

    return {
        "purpose": ("Completed-cache-state upper bound; all instruction/data "
                    "preparation cost is excluded from handoff timing."),
        "schedule": schedule,
        "trials": 256,
        "trials_per_mode": 64,
        "paired_blocks": 32,
        "prep_cost_median_cycles_by_mode": {
            MODE_NAMES[mode]: statistics.median(
                row["prep_cost"] for row in rows if row["mode"] == mode
            ) for mode in MODE_NAMES
        },
        "metrics": metrics,
        "minor_faults": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--schedule", choices=("rotated", "fixed"),
                        default="rotated")
    args = parser.parse_args()
    print(json.dumps(summarize(args.transcript.read_text(errors="replace"),
                               args.schedule), indent=2))


if __name__ == "__main__":
    main()
