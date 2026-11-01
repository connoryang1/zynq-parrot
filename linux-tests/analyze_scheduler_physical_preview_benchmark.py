#!/usr/bin/env python3
"""Summarize interleaved Linux physical-preview timing with paired block CIs."""

import argparse
import json
import random
import re
import statistics
from pathlib import Path


ROW = re.compile(r"PHYSICAL_BENCH trial=(\d+) mode=(\d+) hooks=(\d+) "
                 r"wake_to_entry=(\d+) load_cycles=(\d+) "
                 r"wake_to_load=(\d+) roundtrip=(\d+)")
METRICS = ("wake_to_entry", "load_cycles", "wake_to_load", "roundtrip")


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[round(fraction * (len(ordered) - 1))]


def summarize(rows):
    if len(rows) != 128 or [row["trial"] for row in rows] != list(range(128)):
        raise ValueError("expected exactly 128 ordered measured trials")
    for start in range(0, 128, 4):
        modes = [row["mode"] for row in rows[start:start + 4]]
        if modes != [0, 1, 1, 0]:
            raise ValueError(f"unbalanced trial block at {start}: {modes}")
    for row in rows:
        if row["mode"] == 1 and row["hooks"] == 0:
            raise ValueError(f"enabled trial {row['trial']} had no hook")
        if row["mode"] == 0 and row["hooks"] != 0:
            raise ValueError(f"disabled trial {row['trial']} had a hook")
        if row["wake_to_entry"] + row["load_cycles"] != row["wake_to_load"]:
            raise ValueError(f"inconsistent timing at trial {row['trial']}")
        if row["wake_to_load"] > row["roundtrip"]:
            raise ValueError(f"roundtrip ended before child load at trial {row['trial']}")

    rng = random.Random(0xB50)
    result = {"trials": len(rows), "trials_per_mode": 64,
              "paired_blocks": 32, "metrics": {}}
    for metric in METRICS:
        off = [row[metric] for row in rows if row["mode"] == 0]
        on = [row[metric] for row in rows if row["mode"] == 1]
        blocks = []
        for start in range(0, 128, 4):
            block = rows[start:start + 4]
            off_mean = (block[0][metric] + block[3][metric]) / 2
            on_mean = (block[1][metric] + block[2][metric]) / 2
            blocks.append(off_mean - on_mean)
        estimate = statistics.median(blocks)
        boots = [statistics.median(rng.choices(blocks, k=32)) for _ in range(20000)]
        result["metrics"][metric] = {
            "off_median_cycles": statistics.median(off),
            "on_median_cycles": statistics.median(on),
            "paired_median_saved_cycles": estimate,
            "paired_95pct_ci_saved_cycles": [percentile(boots, 0.025),
                                              percentile(boots, 0.975)],
            "off_range_cycles": [min(off), max(off)],
            "on_range_cycles": [min(on), max(on)],
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    text = args.transcript.read_text(errors="replace")
    if "PHYSICAL_BENCH_CHILD PASS" not in text or "PHYSICAL_BENCH_PARENT PASS" not in text:
        raise SystemExit("missing guest PASS markers")
    rows = []
    for match in ROW.finditer(text):
        values = [int(value) for value in match.groups()]
        rows.append(dict(zip(("trial", "mode", "hooks") + METRICS, values)))
    print(json.dumps(summarize(rows), indent=2))


if __name__ == "__main__":
    main()
