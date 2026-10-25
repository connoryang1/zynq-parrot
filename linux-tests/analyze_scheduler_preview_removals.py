#!/usr/bin/env python3
"""Attribute preview-buffer removals to the Linux benchmark's target segments."""

import argparse
import json
import re
from pathlib import Path

from analyze_scheduler_preview_four import RECORD_PATTERN, target_index
from analyze_scheduler_preview_publications import PUBLICATIONS, analyze as analyze_publications
from analyze_scheduler_preview_events import analyze as analyze_events


SUMMARY = re.compile(
    r"^SCHED_PREVIEW_REMOVALS mode=(\d+) trial=(\d+) count=(\d+) overflow=(\d+)$"
)
EVENT = re.compile(
    r"^SCHED_PREVIEW_REMOVAL mode=(\d+) trial=(\d+) index=(\d+) "
    r"cycle=(\d+) reason=(\d+) paddr=0x([0-9a-f]+)$"
)
REASONS = ("consume", "store", "l1_hit", "replace")


def analyze(path: Path) -> dict:
    delivery = analyze_events(path)["trials"]
    publications = analyze_publications(path)
    summaries, events, pub_cycles, miss_cycles = {}, {}, {}, {}
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        match = SUMMARY.fullmatch(line)
        if match:
            mode, trial, count, overflow = map(int, match.groups())
            if trial in summaries or not 1 <= trial <= 48:
                raise ValueError(f"duplicate or invalid removal trial {trial}")
            if mode != delivery[trial]["mode"] or count > 16 or overflow:
                raise ValueError(f"removal mode, capacity, or overflow in trial {trial}")
            summaries[trial] = (mode, count)
            continue
        match = EVENT.fullmatch(line)
        if match:
            mode, trial, index, cycle, reason = map(int, match.groups()[:5])
            address = int(match.group(6), 16)
            if not 1 <= trial <= 48 or mode != delivery[trial]["mode"]:
                raise ValueError(f"invalid removal mode/trial {mode}/{trial}")
            if reason not in range(4) or address & 15 or address >= 1 << 34:
                raise ValueError(f"invalid removal reason/address in trial {trial}")
            events.setdefault(trial, []).append((index, cycle, reason, address))
            continue
        match = PUBLICATIONS.fullmatch(line)
        if match:
            trial = int(match.group(2))
            count = int(match.group(3))
            words = [int(word, 16) for word in match.group(5).split(",")]
            pub_cycles[trial] = {((word & ((1 << 30) - 1)) << 4): word >> 32
                                 for word in words[:count]}
            continue
        match = RECORD_PATTERN.fullmatch(line)
        if match:
            _, trial, lane, _, cycle, address, _ = match.groups()
            miss_cycles.setdefault((int(trial), int(lane)), []).append(
                (int(cycle), int(address, 16)))
    if sorted(summaries) != list(range(1, 49)):
        raise ValueError(f"expected 48 removal summaries, got {len(summaries)}")
    for trial, (_, count) in summaries.items():
        rows = events.get(trial, [])
        if len(rows) != count or [row[0] for row in rows] != list(range(count)):
            raise ValueError(f"removal records disagree with count in trial {trial}")
        if [row[1] for row in rows] != sorted(row[1] for row in rows):
            raise ValueError(f"unordered removal cycles in trial {trial}")

    target_base = int(publications["target_physical_base"], 16)
    exact = {}
    for trial, (mode, _) in summaries.items():
        if mode != 1:
            continue
        target_rows = []
        for lane in range(4):
            address = target_base + 64 * target_index(trial, lane)
            published = pub_cycles[trial].get(address)
            demand = [cycle for cycle, paddr in miss_cycles.get((trial, lane), [])
                      if paddr == address]
            removals = [dict(cycle=cycle, reason=REASONS[reason])
                        for _, cycle, reason, paddr in events.get(trial, [])
                        if paddr == address and published is not None
                        and cycle >= published]
            target_rows.append(dict(paddr=f"0x{address:x}", published_cycle=published,
                                    demand_miss_cycles=demand, removals=removals))
        exact[trial] = target_rows
    return dict(source=str(path), target_physical_base=f"0x{target_base:x}",
                removal_totals={str(mode): sum(count for row_mode, count in summaries.values()
                                               if row_mode == mode)
                                for mode in range(3)},
                exact_trials=exact,
                published_but_missed_trials=publications[
                    "exact_published_by_entry_but_missed_trials"])


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
