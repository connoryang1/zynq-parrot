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
RECORD_PATTERN = re.compile(
    r"^SCHED_PREVIEW_RECORD mode=(\d+) trial=(\d+) lane=(\d+) "
    r"index=(\d+) cycle=(\d+) paddr=0x([0-9a-f]+) msg=(\d+)$"
)


def target_index(trial: int, lane: int) -> int:
    return 4 * ((trial - 1) % 16) + lane


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    timing = analyze(args.transcript, "SCHED_PREVIEW")
    rows = {}
    records = {}
    for line in args.transcript.read_text(errors="replace").splitlines():
        match = PATTERN.fullmatch(line.strip())
        if not match:
            record = RECORD_PATTERN.fullmatch(line.strip())
            if record:
                mode, trial, lane, index, cycle, paddr, msg = record.groups()
                mode, trial, lane, index, cycle, msg = map(
                    int, (mode, trial, lane, index, cycle, msg))
                if not 1 <= trial <= 48 or not 0 <= lane < 4:
                    parser.error(f"invalid record trial/lane {trial}/{lane}")
                records.setdefault((trial, lane), []).append(
                    (mode, index, cycle, int(paddr, 16), msg))
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

    # CSR 0x805 records every D-cache miss between two snapshots. An interrupt
    # can add unrelated misses inside a lane's interval, so the raw count is
    # not itself a target-line count. Off trials establish the physical base
    # of the page containing all 64 target lines.
    bases = set()
    for trial in range(1, 49):
        mode, lane_counts, _ = rows[trial]
        for lane, count in enumerate(lane_counts):
            lane_records = records.get((trial, lane), [])
            if len(lane_records) != count:
                parser.error(f"record count differs from CSR count in trial {trial} lane {lane}")
            if any(rec[0] != mode for rec in lane_records):
                parser.error(f"record mode differs from miss mode in trial {trial}")
            if mode == 0:
                if count != 1:
                    parser.error(f"off control trial {trial} lane {lane} has {count} misses")
                bases.add(lane_records[0][3] - 64 * target_index(trial, lane))
    if len(bases) != 1:
        parser.error(f"off controls imply {len(bases)} target physical bases")
    target_base = bases.pop()
    target_rows = {}
    noise_by_mode = {mode: 0 for mode in range(3)}
    for trial, (mode, _, _) in rows.items():
        matched = []
        for lane in range(4):
            expected = target_base + 64 * target_index(trial, lane)
            count = sum(rec[3] == expected for rec in records.get((trial, lane), []))
            if count > 1:
                parser.error(f"target line missed repeatedly in trial {trial} lane {lane}")
            matched.append(count)
            noise_by_mode[mode] += len(records.get((trial, lane), [])) - count
        target_rows[trial] = (mode, tuple(matched), sum(matched))

    blocks = []
    for first in range(1, 49, 3):
        block = {}
        for trial in range(first, first + 3):
            mode, lane_counts, total = target_rows[trial]
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
        "target_physical_base": f"0x{target_base:x}",
        "non_target_recorder_misses": {
            name: noise_by_mode[mode]
            for mode, name in enumerate(("off", "exact", "stale"))
        },
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
