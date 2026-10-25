#!/usr/bin/env python3
"""Validate one Linux guest's physical preview-stage snapshots."""

import argparse
import json
import re
import statistics
from pathlib import Path


PATTERN = re.compile(
    r"^SCHED_PREVIEW_EVENTS mode=(\d+) trial=(\d+) "
    r"entry=(\d+),(\d+),(\d+),(\d+) "
    r"demand=(\d+),(\d+),(\d+),(\d+) "
    r"load=(\d+),(\d+),(\d+),(\d+) "
    r"post=(\d+),(\d+),(\d+),(\d+)$"
)
STAGES = ("physical", "admitted", "issued", "published")
SNAPSHOTS = ("entry", "demand", "load", "post")


def analyze(path: Path) -> dict:
    rows = {}
    for line in path.read_text(errors="replace").splitlines():
        match = PATTERN.fullmatch(line.strip())
        if not match:
            continue
        values = tuple(map(int, match.groups()))
        mode, trial = values[:2]
        if trial in rows:
            raise ValueError(f"duplicate event trial {trial}")
        if mode != ((trial - 1) + (trial - 1) // 3) % 3:
            raise ValueError(f"unexpected mode {mode} for trial {trial}")
        snapshots = dict(zip(SNAPSHOTS,
                             (values[i:i + 4] for i in range(2, 18, 4))))
        for stage in range(4):
            series = [snapshots[name][stage] for name in SNAPSHOTS]
            if max(series) >= 255:
                raise ValueError(f"saturated {STAGES[stage]} count in trial {trial}")
            if series != sorted(series):
                raise ValueError(f"reversed {STAGES[stage]} count in trial {trial}")
        rows[trial] = {"mode": mode, "snapshots": snapshots}
    if sorted(rows) != list(range(1, 49)):
        raise ValueError(f"expected event trials 1..48, found {len(rows)}")

    by_mode = {}
    for mode, name in enumerate(("off", "exact", "stale")):
        selected = [rows[trial]["snapshots"] for trial in sorted(rows)
                    if rows[trial]["mode"] == mode]
        by_mode[name] = {
            snapshot: {
                stage: {
                    "total": sum(row[snapshot][index] for row in selected),
                    "median": statistics.median(row[snapshot][index]
                                                 for row in selected),
                }
                for index, stage in enumerate(STAGES)
            }
            for snapshot in SNAPSHOTS
        }
    return {"source": str(path), "events_by_mode": by_mode,
            "trials": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.transcript), indent=2, sort_keys=True))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
