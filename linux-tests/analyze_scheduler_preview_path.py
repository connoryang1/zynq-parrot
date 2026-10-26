#!/usr/bin/env python3
"""Validate physical Linux scheduler-path guard observations."""

import argparse
import json
import lzma
import re
from pathlib import Path


ROWS = re.compile(
    r"^PREVIEW_PATH mode=(\d+) trial=(\d+) selected=(\d+) idle=(\d+) "
    r"different_mm=(\d+) descriptor=(\d+) empty=(\d+) hook=(\d+) "
    r"stable=(\d+) pure=(\d+)$"
)
SUMMARY = re.compile(
    r"^PREVIEW_PATH_RESULT same=(\d+) idle=(\d+) different_mm=(\d+) of=(\d+)$"
)
MODES = {0: "same", 1: "idle", 2: "different_mm"}
REPETITIONS = 8


def analyze(path: Path) -> dict:
    if path.suffix == ".xz":
        with lzma.open(path, "rt", errors="replace") as stream:
            text = stream.read()
    else:
        text = path.read_text(errors="replace")
    rows = {}
    row_copies = {}
    summaries = []
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\0")
        if match := ROWS.fullmatch(line):
            mode, trial, selected, idle, other_mm, descriptor, empty, hook, stable, pure = (
                map(int, match.groups())
            )
            key = (mode, trial)
            if mode not in MODES or not 1 <= trial <= REPETITIONS:
                raise ValueError(f"invalid mode/trial {key}")
            if stable not in (0, 1) or pure not in (0, 1):
                raise ValueError(f"invalid stable/pure bits {key}")
            expected_pure = int(
                stable == 1 and selected == 1 and idle == (mode == 1)
                and other_mm == (mode == 2) and descriptor == 0
                and empty == 0 and hook == (mode == 0)
            )
            if pure != expected_pure:
                raise ValueError(f"misclassified row {key}")
            row = {"selected": selected, "idle": idle,
                   "different_mm": other_mm, "descriptor": descriptor,
                   "empty": empty, "hook": hook, "stable": stable,
                   "pure": pure}
            if key in rows and rows[key] != row:
                raise ValueError(f"conflicting repeated row {key}")
            rows[key] = row
            row_copies[key] = row_copies.get(key, 0) + 1
        elif match := SUMMARY.fullmatch(line):
            summaries.append(tuple(map(int, match.groups())))

    expected = {(mode, trial) for mode in MODES
                for trial in range(1, REPETITIONS + 1)}
    if set(rows) != expected:
        raise ValueError(f"expected {len(expected)} unique rows, got {len(rows)}")
    # The serialized runner prints the live guest stream and its retained
    # transcript. Accept only complete, identical copies of every row.
    copies = set(row_copies.values())
    if len(copies) != 1 or len(summaries) != next(iter(copies)):
        raise ValueError("partial or inconsistent transcript copies")
    if len(set(summaries)) != 1:
        raise ValueError("conflicting repeated summaries")
    summary = summaries[0]
    counts = {name: sum(rows[mode, trial]["pure"]
                        for trial in range(1, REPETITIONS + 1))
              for mode, name in MODES.items()}
    if summary != (counts["same"], counts["idle"],
                   counts["different_mm"], REPETITIONS):
        raise ValueError("guest summary disagrees with classified rows")
    if not all(counts.values()):
        raise ValueError("a controlled predecessor has no conclusive sample")
    for marker in ("PREVIEW_PATH_INIT_START", "PREVIEW_PATH PASS",
                   "PREVIEW_PATH_INIT_RESULT=0", "CORE PASS", "BSG PASS",
                   "RUNNER_EXIT=0"):
        if marker not in text:
            raise ValueError(f"missing terminal marker {marker}")

    return {"source": str(path), "transcript_copies": len(summaries),
            "trials_per_mode": REPETITIONS,
            "conclusive": counts,
            "multiple_selections": {
                name: sum(rows[mode, trial]["selected"] > 1
                          for trial in range(1, REPETITIONS + 1))
                for mode, name in MODES.items()
            },
            "unstable_snapshots": {
                name: sum(rows[mode, trial]["stable"] == 0
                          for trial in range(1, REPETITIONS + 1))
                for mode, name in MODES.items()
            }}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.transcript), indent=2, sort_keys=True))
    except ValueError as exc:
        parser.exit(1, f"invalid scheduler-path transcript: {exc}\n")


if __name__ == "__main__":
    main()
