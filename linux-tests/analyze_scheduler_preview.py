#!/usr/bin/env python3
"""Validate a scheduler-preview transcript and summarize paired handoff intervals."""

import argparse
import json
import re
import statistics
from pathlib import Path


MODES = {0: "off", 1: "exact", 2: "stale"}
FIELDS = ("wake", "entry", "load", "roundtrip")


def analyze(path: Path, prefix: str) -> dict:
    text = path.read_text(errors="replace")
    pattern = re.compile(
        rf"^{re.escape(prefix)} mode=(\d+) trial=(\d+) cpu=(\d+) "
        rf"wake=(\d+) entry=(\d+) load=(\d+) roundtrip=(\d+)$"
    )
    rows = {}
    for line in text.splitlines():
        match = pattern.fullmatch(line.strip())
        if not match:
            continue
        mode, trial, cpu, *intervals = map(int, match.groups())
        if trial in rows:
            raise ValueError(f"duplicate trial {trial}")
        rows[trial] = {"mode": mode, "cpu": cpu, **dict(zip(FIELDS, intervals))}

    if f"{prefix} PASS" not in text or "SCHED_PREVIEW_INIT_RESULT=0" not in text:
        raise ValueError("guest PASS or zero init result is missing")
    if sorted(rows) != list(range(1, 49)):
        raise ValueError(f"expected trials 1..48, found {len(rows)}")
    cpus = {row["cpu"] for row in rows.values()}
    if len(cpus) != 1:
        raise ValueError(f"trials used multiple CPUs: {sorted(cpus)}")

    blocks = []
    for first in range(1, 49, 3):
        block = {}
        for trial in range(first, first + 3):
            row = rows[trial]
            expected = ((trial - 1) + (trial - 1) // 3) % 3
            if row["mode"] != expected:
                raise ValueError(f"trial {trial} has mode {row['mode']}, expected {expected}")
            if row["load"] < row["entry"] or row["roundtrip"] < row["load"]:
                raise ValueError(f"trial {trial} has nonmonotonic target/roundtrip timestamps")
            row["load_after_entry"] = row["load"] - row["entry"]
            row["return_after_load"] = row["roundtrip"] - row["load"]
            block[row["mode"]] = row
        if set(block) != set(MODES):
            raise ValueError(f"block beginning at trial {first} lacks a control")
        blocks.append(block)

    metrics = (*FIELDS, "load_after_entry", "return_after_load")
    by_mode = {
        name: {
            metric: statistics.median(block[mode][metric] for block in blocks)
            for metric in metrics
        }
        for mode, name in MODES.items()
    }
    paired = {}
    for mode in (1, 2):
        paired[MODES[mode]] = {}
        for metric in ("entry", "load_after_entry", "return_after_load", "roundtrip"):
            differences = [block[mode][metric] - block[0][metric] for block in blocks]
            paired[MODES[mode]][metric] = {
                "median_delta_vs_off": statistics.median(differences),
                "faster_blocks": sum(delta < 0 for delta in differences),
                "slower_blocks": sum(delta > 0 for delta in differences),
            }

    return {
        "source": str(path),
        "unit": "ns" if prefix.endswith("_SOFT") else "cycles",
        "clock": "QEMU software" if prefix.endswith("_SOFT") else "BlackParrot guest CSR",
        "trials": len(rows),
        "balanced_blocks": len(blocks),
        "cpu": next(iter(cpus)),
        "mode_medians": by_mode,
        "paired_blocks": paired,
        # The waker can return from futex_wake after the peer enters, so wake
        # time is not always an interval before the measured peer work.
        "peer_entry_before_wake_return": {
            name: sum(block[mode]["entry"] < block[mode]["wake"] for block in blocks)
            for mode, name in MODES.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--prefix", choices=("SCHED_PREVIEW", "SCHED_PREVIEW_SOFT"),
                        default="SCHED_PREVIEW")
    args = parser.parse_args()
    try:
        result = analyze(args.transcript, args.prefix)
    except ValueError as exc:
        parser.exit(1, f"invalid scheduler-preview transcript: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
