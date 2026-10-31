#!/usr/bin/env python3
"""Summarize the cross-process completed-data oracle with paired block CIs."""

import argparse
import json
import random
import re
import statistics
from pathlib import Path


ROW = re.compile(
    r"DATA_ORACLE trial=(\d+) footprint=(\d+) shape=(\w+) mode=(\d+) "
    r"oracle_cost=(\d+) wake_to_entry=(\d+) load_cycles=(\d+) "
    r"wake_to_load=(\d+) roundtrip=(\d+)"
)
FAULT = re.compile(r"DATA_ORACLE_FAULTS footprint=(\d+) shape=(\w+) faults=(\d+)")
METRICS = ("wake_to_entry", "load_cycles", "wake_to_load", "roundtrip")
CONDITIONS = ((16, "independent"), (16, "dependent"),
              (32, "independent"), (32, "dependent"))


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[round(fraction * (len(ordered) - 1))]


def summarize_condition(rows, seed):
    if len(rows) != 128 or [row["trial"] for row in rows] != list(range(128)):
        raise ValueError("expected exactly 128 ordered measured trials")
    for start in range(0, 128, 4):
        modes = [row["mode"] for row in rows[start:start + 4]]
        if modes != [0, 1, 1, 0]:
            raise ValueError(f"unbalanced trial block at {start}: {modes}")
    for row in rows:
        if row["wake_to_entry"] + row["load_cycles"] != row["wake_to_load"]:
            raise ValueError(f"inconsistent timing at trial {row['trial']}")
        if row["wake_to_load"] > row["roundtrip"]:
            raise ValueError(f"roundtrip ended before child load at trial {row['trial']}")

    rng = random.Random(seed)
    result = {
        "trials": len(rows),
        "trials_per_mode": 64,
        "paired_blocks": 32,
        "oracle_cost_median_cycles": statistics.median(
            row["oracle_cost"] for row in rows if row["mode"] == 1
        ),
        "metrics": {},
    }
    for metric in METRICS:
        cold = [row[metric] for row in rows if row["mode"] == 0]
        oracle = [row[metric] for row in rows if row["mode"] == 1]
        blocks = []
        for start in range(0, 128, 4):
            block = rows[start:start + 4]
            cold_mean = (block[0][metric] + block[3][metric]) / 2
            oracle_mean = (block[1][metric] + block[2][metric]) / 2
            blocks.append(cold_mean - oracle_mean)
        estimate = statistics.median(blocks)
        boots = [statistics.median(rng.choices(blocks, k=32))
                 for _ in range(20000)]
        cold_median = statistics.median(cold)
        oracle_median = statistics.median(oracle)
        result["metrics"][metric] = {
            "cold_median_cycles": cold_median,
            "oracle_median_cycles": oracle_median,
            "median_ratio_cold_over_oracle": cold_median / oracle_median,
            "paired_median_saved_cycles": estimate,
            "paired_95pct_ci_saved_cycles": [percentile(boots, 0.025),
                                               percentile(boots, 0.975)],
            "cold_range_cycles": [min(cold), max(cold)],
            "oracle_range_cycles": [min(oracle), max(oracle)],
        }
    return result


def summarize(text):
    if "DATA_ORACLE_CHILD PASS" not in text or "DATA_ORACLE_PARENT PASS" not in text:
        raise ValueError("missing guest PASS markers")
    if "INFO:    CORE PASS" not in text or "INFO:    BSG PASS" not in text:
        raise ValueError("missing board PASS markers")

    rows = {condition: [] for condition in CONDITIONS}
    for match in ROW.finditer(text):
        values = match.groups()
        condition = (int(values[1]), values[2])
        if condition not in rows:
            raise ValueError(f"unexpected condition: {condition}")
        rows[condition].append({
            "trial": int(values[0]),
            "mode": int(values[3]),
            "oracle_cost": int(values[4]),
            "wake_to_entry": int(values[5]),
            "load_cycles": int(values[6]),
            "wake_to_load": int(values[7]),
            "roundtrip": int(values[8]),
        })

    faults = {(int(match.group(1)), match.group(2)): int(match.group(3))
              for match in FAULT.finditer(text)}
    if set(faults) != set(CONDITIONS):
        raise ValueError("missing condition fault counts")
    if any(faults.values()):
        raise ValueError(f"measured minor faults are not zero: {faults}")

    return {
        "purpose": "Completed-cache-state upper bound; oracle issue cost is excluded from handoff timing.",
        "conditions": {
            f"{footprint}_{shape}": summarize_condition(
                rows[(footprint, shape)], 0xDA7A + footprint + index
            )
            for index, (footprint, shape) in enumerate(CONDITIONS)
        },
        "minor_faults": {f"{footprint}_{shape}": faults[(footprint, shape)]
                         for footprint, shape in CONDITIONS},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.transcript.read_text(errors="replace")), indent=2))


if __name__ == "__main__":
    main()
