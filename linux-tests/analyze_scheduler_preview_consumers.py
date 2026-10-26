#!/usr/bin/env python3
"""Validate consumer-PC rows against strict scheduler-preview removal evidence."""

import argparse
import json
import re
from pathlib import Path

from analyze_scheduler_preview_removals import EVENT, SUMMARY, analyze as analyze_removals


CONSUMER = re.compile(
    r"^SCHED_PREVIEW_CONSUMER mode=(\d+) trial=(\d+) index=(\d+) "
    r"valid=(\d+) thread=(\d+) pc=0x([0-9a-f]+) raw=0x([0-9a-f]+)$"
)
CLOCK = re.compile(
    r"^SCHED_PREVIEW_CLOCK mode=(\d+) trial=(\d+) entry=(\d+) load=(\d+)$"
)
PC_MASK = (1 << 39) - 1


def canonical_pc(pc: int) -> str:
    if pc & (1 << 38):
        pc |= ((1 << 64) - 1) ^ PC_MASK
    return f"0x{pc:x}"


def analyze(path: Path) -> dict:
    strict = analyze_removals(path)
    summaries, removals, consumers, clocks = {}, {}, {}, {}
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if match := SUMMARY.fullmatch(line):
            mode, trial, count, _ = map(int, match.groups())
            summaries[trial] = (mode, count)
        elif match := EVENT.fullmatch(line):
            mode, trial, index, cycle, reason = map(int, match.groups()[:5])
            key = (trial, index)
            if key in removals:
                raise ValueError(f"duplicate removal {key}")
            removals[key] = (mode, cycle, reason, int(match.group(6), 16))
        elif match := CONSUMER.fullmatch(line):
            mode, trial, index, valid, thread = map(int, match.groups()[:5])
            pc, raw = (int(word, 16) for word in match.groups()[5:])
            key = (trial, index)
            if key in consumers:
                raise ValueError(f"duplicate consumer {key}")
            if valid not in (0, 1) or thread not in (0, 1):
                raise ValueError(f"invalid consumer valid/thread {key}")
            if pc != (raw & PC_MASK) or valid != ((raw >> 40) & 1) or thread != ((raw >> 39) & 1):
                raise ValueError(f"consumer raw fields disagree {key}")
            if raw >> 41:
                raise ValueError(f"consumer raw has reserved bits {key}")
            consumers[key] = (mode, valid, thread, pc)
        elif match := CLOCK.fullmatch(line):
            mode, trial, entry, load = map(int, match.groups())
            if trial in clocks or entry > load:
                raise ValueError(f"invalid peer clock {trial}")
            clocks[trial] = (mode, entry, load)

    expected = {(trial, index) for trial, (_, count) in summaries.items()
                for index in range(count)}
    if set(consumers) != expected:
        missing = sorted(expected - set(consumers))
        extra = sorted(set(consumers) - expected)
        raise ValueError(f"consumer/removal count mismatch: missing={missing[:5]} extra={extra[:5]}")
    if set(clocks) != set(range(1, 49)):
        raise ValueError(f"expected 48 peer clocks, got {len(clocks)}")
    for trial, (mode, count) in summaries.items():
        if clocks[trial][0] != mode:
            raise ValueError(f"peer clock mode mismatch in trial {trial}")
        for index in range(count):
            key = (trial, index)
            if removals[key][0] != mode or consumers[key][0] != mode:
                raise ValueError(f"consumer/removal mode mismatch {key}")
            if removals[key][2] != 0 and consumers[key][1:] != (0, 0, 0):
                raise ValueError(f"non-consume removal has PC metadata {key}")

    exact = {}
    target_base = int(strict["target_physical_base"], 16)
    for trial_text, lanes in strict["exact_trials"].items():
        trial = int(trial_text)
        mode, entry, load = clocks[trial]
        if mode != 1:
            raise ValueError(f"exact trial {trial} has wrong clock mode")
        target_addresses = {int(lane["paddr"], 16) for lane in lanes}
        rows = []
        for index in range(summaries[trial][1]):
            key = (trial, index)
            remove_mode, cycle, reason, address = removals[key]
            consumer_mode, valid, thread, pc = consumers[key]
            if remove_mode != mode or consumer_mode != mode:
                raise ValueError(f"mode mismatch {key}")
            if address not in target_addresses or reason != 0:
                continue
            published = next((lane["published_cycle"] for lane in lanes
                              if int(lane["paddr"], 16) == address), None)
            if published is None or cycle < published:
                continue
            rows.append(dict(index=index, paddr=f"0x{address:x}", cycle=cycle,
                             before_entry=cycle < entry, pc_valid=bool(valid),
                             thread=thread if valid else None,
                             pc=canonical_pc(pc) if valid else None))
        exact[trial_text] = dict(entry_cycle=entry, load_cycle=load,
                                  target_consumers=rows)
    return dict(source=str(path), target_physical_base=f"0x{target_base:x}",
                consumer_rows=len(consumers), exact_trials=exact,
                strict_removals=strict)


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
