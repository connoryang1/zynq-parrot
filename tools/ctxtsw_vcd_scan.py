#!/usr/bin/env python3
"""Small VCD scanner for BlackParrot ctxtsw debug.

This intentionally streams the VCD twice: once for the header and once for
transitions. It keeps only selected signal changes in memory.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict


DEFAULT_PATTERNS = [
    "ctxtsw",
    "current_thread_id",
    "fe_queue_roll",
    "npc_mismatch",
    "clear_iss",
    "suppress_iss",
    "commit_pkt",
    "br_pkt",
    "expected_npc",
    "npc_r",
    "pc_r",
    "fe_cmd",
    "state_r",
    "isd_status",
    "dispatch",
]


def parse_header(path: str):
    signals = {}
    scopes = []
    var_re = re.compile(r"\$var\s+\w+\s+(\d+)\s+(\S+)\s+(.+?)\s+\$end")
    scope_re = re.compile(r"\$scope\s+\w+\s+(\S+)")

    with open(path, "r", errors="replace", buffering=8 * 1024 * 1024) as f:
        for line in f:
            if "$enddefinitions" in line:
                break
            if "$scope" in line:
                match = scope_re.search(line)
                if match:
                    scopes.append(match.group(1))
                continue
            if "$upscope" in line:
                if scopes:
                    scopes.pop()
                continue
            if "$var" in line:
                match = var_re.search(line.rstrip())
                if match:
                    width, code, raw_name = match.groups()
                    name = raw_name.split()[0]
                    full = ".".join(scopes + [name])
                    signals[code] = (full, int(width))

    return signals


def matches(full: str, patterns: list[str]) -> bool:
    return any(pattern in full for pattern in patterns)


def cycle(time_ps: int, period_ps: int) -> int:
    return time_ps // period_ps


def value_text(value: str, width: int) -> str:
    if not value:
        return value
    if width > 4 and re.fullmatch(r"[01]+", value):
        return f"0x{int(value, 2):x}"
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--pattern", action="append", dest="patterns")
    parser.add_argument("--event-pattern", action="append", dest="event_patterns")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--max-time", type=int, default=2_000_000_000)
    parser.add_argument("--min-time", type=int, default=0)
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--window", type=int, default=12)
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()

    patterns = args.patterns or DEFAULT_PATTERNS
    signals = parse_header(args.vcd)
    selected = {
        code: (full, width)
        for code, (full, width) in signals.items()
        if matches(full, patterns)
    }

    print(f"signals total={len(signals)} selected={len(selected)}")
    for code, (full, width) in sorted(selected.items(), key=lambda kv: kv[1][0]):
        print(f"{code:>8s} {width:>3d} {full}")

    if args.list:
        return 0

    transitions = []
    current_time = 0
    in_values = False

    with open(args.vcd, "r", errors="replace", buffering=16 * 1024 * 1024) as f:
        for line in f:
            line = line.rstrip()
            if not in_values:
                if "$dumpvars" in line:
                    in_values = True
                continue
            if not line:
                continue
            if line[0] == "#":
                current_time = int(line[1:])
                if current_time > args.max_time:
                    break
                continue
            if current_time < args.min_time:
                continue
            if line[0] in "bB":
                parts = line.split()
                if len(parts) == 2 and parts[1] in selected:
                    transitions.append((current_time, parts[1], parts[0][1:]))
                continue
            if line[0] in "01xXzZ":
                code = line[1:]
                if code in selected:
                    transitions.append((current_time, code, line[0]))

    print(f"\ntransitions selected={len(transitions)} max_cycle={cycle(args.max_time, args.period)}")

    by_time = defaultdict(list)
    interesting = set()
    interesting_terms = args.event_patterns or (
        "ctxtsw",
        "npc_mismatch",
        "fe_queue_roll",
        "clear_iss",
        "commit_pkt",
        "current_thread_id",
    )
    for t, code, value in transitions:
        full = selected[code][0]
        by_time[t].append((full, value))
        if any(term in full for term in interesting_terms):
            interesting.add(t)

    ranges = []
    span = args.window * args.period
    for t in sorted(interesting):
        start, end = t - span, t + span
        if ranges and start <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))

    printed = 0
    for start, end in ranges:
        if printed >= args.limit:
            break
        print(f"\n=== cycles {cycle(start, args.period)}..{cycle(end, args.period)} ===")
        for t in sorted(k for k in by_time if start <= k <= end):
            entries = by_time[t]
            compact = []
            for full, value in sorted(entries):
                short = ".".join(full.split(".")[-3:])
                width = next(width for name, width in selected.values() if name == full)
                compact.append(f"{short}={value_text(value, width)}")
            print(f"cyc={cycle(t, args.period):8d} " + " ".join(compact))
            printed += 1
            if printed >= args.limit:
                break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
