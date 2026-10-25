#!/usr/bin/env python3
"""Validate four-line scheduler-preview miss counts from one raw guest log."""

import argparse
import json
import re
import statistics
from pathlib import Path

from analyze_scheduler_preview import analyze


PATTERN = re.compile(
    r"^SCHED_PREVIEW_MISS4 mode=(\d+) trial=(\d+) "
    r"d0=(\d+) d1=(\d+) d2=(\d+) d3=(\d+) "
    r"total=(\d+) armed=(\d+) overflow=(\d+)$"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    timing = analyze(args.transcript, "SCHED_PREVIEW")
    rows = {}
    for line in args.transcript.read_text(errors="replace").splitlines():
        match = PATTERN.fullmatch(line.strip())
        if not match:
            continue
        mode, trial, d0, d1, d2, d3, total, armed, overflow = map(int, match.groups())
        if trial in rows:
            parser.error(f"duplicate miss trial {trial}")
        if total != d0 + d1 + d2 + d3:
            parser.error(f"inconsistent target miss sum in trial {trial}")
        if armed != 1 or overflow != 0:
            parser.error(f"recorder unavailable or overflowed in trial {trial}")
        rows[trial] = (mode, (d0, d1, d2, d3), total)
    if sorted(rows) != list(range(1, 49)):
        parser.error(f"expected miss trials 1..48, found {len(rows)}")

    blocks = []
    for first in range(1, 49, 3):
        block = {}
        for trial in range(first, first + 3):
            mode, lane_counts, total = rows[trial]
            expected = ((trial - 1) + (trial - 1) // 3) % 3
            if mode != expected:
                parser.error(f"trial {trial} has mode {mode}, expected {expected}")
            block[mode] = (lane_counts, total)
        blocks.append(block)

    by_mode = {}
    for mode, name in enumerate(("off", "exact", "stale")):
        counts = [block[mode][1] for block in blocks]
        by_mode[name] = {
            "total_demand_misses": sum(counts),
            "median_misses_per_trial": statistics.median(counts),
            "zero_miss_trials": sum(count == 0 for count in counts),
            "per_lane_misses": [
                sum(block[mode][0][lane] for block in blocks) for lane in range(4)
            ],
        }
    paired = {}
    for mode, name in ((1, "exact"), (2, "stale")):
        differences = [block[mode][1] - block[0][1] for block in blocks]
        paired[name] = {
            "median_demand_miss_delta_vs_off": statistics.median(differences),
            "fewer_than_off_blocks": sum(delta < 0 for delta in differences),
            "same_as_off_blocks": sum(delta == 0 for delta in differences),
            "more_than_off_blocks": sum(delta > 0 for delta in differences),
        }
    print(json.dumps({
        "source": str(args.transcript),
        "timing": timing,
        "demand_misses": by_mode,
        "paired_demand_misses": paired,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
