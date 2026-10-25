#!/usr/bin/env python3
"""Validate paired scheduler-preview demand-miss counts from one guest log."""

import argparse
import json
import re
from pathlib import Path

from analyze_scheduler_preview import analyze


PATTERN = re.compile(
    r"^SCHED_PREVIEW_MISS mode=(\d+) trial=(\d+) before=(\d+) "
    r"after=(\d+) dmiss=(\d+) armed=(\d+) overflow=(\d+)$"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    timing = analyze(args.transcript, "SCHED_PREVIEW")
    text = args.transcript.read_text(errors="replace")
    rows = {}
    for line in text.splitlines():
        match = PATTERN.fullmatch(line.strip())
        if not match:
            continue
        mode, trial, before, after, count, armed, overflow = map(int, match.groups())
        if trial in rows:
            parser.error(f"duplicate miss trial {trial}")
        if after < before or after - before != count:
            parser.error(f"inconsistent D-cache count in trial {trial}")
        if armed != 1 or overflow != 0:
            parser.error(f"recorder unavailable or overflowed in trial {trial}")
        rows[trial] = (mode, count)
    if sorted(rows) != list(range(1, 49)):
        parser.error(f"expected miss trials 1..48, found {len(rows)}")

    blocks = []
    for first in range(1, 49, 3):
        block = {}
        for trial in range(first, first + 3):
            mode, count = rows[trial]
            expected = ((trial - 1) + (trial - 1) // 3) % 3
            if mode != expected:
                parser.error(f"trial {trial} has mode {mode}, expected {expected}")
            block[mode] = count
        blocks.append(block)
    per_mode = {}
    for mode, name in enumerate(("off", "exact", "stale")):
        counts = [block[mode] for block in blocks]
        per_mode[name] = {
            "zero_demand_miss_trials": sum(count == 0 for count in counts),
            "one_demand_miss_trials": sum(count == 1 for count in counts),
            "multiple_demand_miss_trials": sum(count > 1 for count in counts),
            "total_demand_misses": sum(counts),
        }
    paired = {}
    for mode, name in ((1, "exact"), (2, "stale")):
        diffs = [block[mode] - block[0] for block in blocks]
        paired[name] = {
            "fewer_than_off_blocks": sum(diff < 0 for diff in diffs),
            "same_as_off_blocks": sum(diff == 0 for diff in diffs),
            "more_than_off_blocks": sum(diff > 0 for diff in diffs),
        }
    print(json.dumps({
        "source": str(args.transcript),
        "timing": timing,
        "demand_misses": per_mode,
        "paired_demand_misses": paired,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
