#!/usr/bin/env python3
"""Audit context-switch event counts inside a VCD cycle window."""

from __future__ import annotations

import argparse
import collections

import ctxtsw_perf_report as perf


def event_by_identity(values, last, valid_label, pc_label=None, tid_label=None):
    if not perf.is_one(values, valid_label):
        return False
    if not perf.is_one(last, valid_label):
        return True
    if pc_label is not None and values.get(pc_label) != last.get(pc_label):
        return True
    if tid_label is not None and values.get(tid_label) != last.get(tid_label):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--elf", required=True)
    parser.add_argument("--run-log", required=True)
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--start-pc", type=perf.parse_int)
    parser.add_argument("--start-cycle", type=int)
    parser.add_argument("--total-cycles", type=perf.parse_int)
    parser.add_argument("--max-events", type=int, default=12)
    args = parser.parse_args()

    asm = perf.load_disasm(args.elf)
    start_pc = args.start_pc if args.start_pc is not None else perf.find_start_pc_after_rdcycle(asm)
    total_cycles = args.total_cycles
    if total_cycles is None:
        total_cycles = perf.parse_total_cycles_from_log(args.run_log)

    selected, found = perf.select(perf.parse_header(args.vcd))
    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    window_start = args.start_cycle
    window_end = None if window_start is None else window_start + total_cycles

    counts = collections.Counter()
    by_tid = collections.defaultdict(collections.Counter)
    by_pc = collections.defaultdict(collections.Counter)
    examples: dict[str, list[str]] = collections.defaultdict(list)
    start_pc_events = []

    def record(kind, cycle):
        counts[kind] += 1
        by_tid[kind][values.get("dispatch_tid")] += 1
        by_pc[kind][values.get("dispatch_pc")] += 1
        if len(examples[kind]) < args.max_events:
            pc = values.get("dispatch_pc")
            tid = values.get("dispatch_tid")
            text = asm.get(pc, "")
            examples[kind].append(f"cyc={cycle} pc={perf.fmt(pc)} tid={perf.fmt(tid)} {text}")

    def finish_time():
        nonlocal window_start, window_end
        cycle = current_time // args.period
        dispatch_level = perf.is_one(values, "dispatch_ctxtsw") and perf.is_one(values, "dispatch_v")
        if window_start is None and dispatch_level and cycle >= 0 and values.get("dispatch_pc") == start_pc:
            window_start = cycle
            window_end = window_start + total_cycles
        if window_start is None or cycle < window_start or (window_end is not None and cycle > window_end):
            last.update(values)
            return

        if dispatch_level:
            record("dispatch_level_samples", cycle)
            if values.get("dispatch_pc") == start_pc and len(start_pc_events) < 128:
                start_pc_events.append((cycle, values.get("dispatch_tid")))
        if perf.rose(values, last, "dispatch_ctxtsw") and perf.is_one(values, "dispatch_v"):
            record("dispatch_rise_events", cycle)
        if event_by_identity(values, last, "dispatch_ctxtsw", "dispatch_pc", "dispatch_tid") and perf.is_one(values, "dispatch_v"):
            record("dispatch_identity_events", cycle)

        if perf.is_one(values, "commit_ctxtsw"):
            counts["commit_level_samples"] += 1
        if perf.rose(values, last, "commit_ctxtsw"):
            counts["commit_rise_events"] += 1

        last.update(values)

    with open(args.vcd, "r", errors="replace", buffering=16 * 1024 * 1024) as f:
        for raw in f:
            line = raw.rstrip()
            if not in_values:
                if "$dumpvars" in line:
                    in_values = True
                continue
            if not line:
                continue
            if line[0] == "#":
                finish_time()
                current_time = int(line[1:])
                cycle = current_time // args.period
                if window_end is not None and window_start is not None and cycle > window_end:
                    break
            else:
                perf.apply_line(line, selected, values)
        finish_time()

    print(f"vcd {args.vcd}")
    print(f"start_pc={perf.fmt(start_pc)} {asm.get(start_pc, '')}")
    print(f"window start={window_start} end={window_end} total_cycles={total_cycles}")
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    for kind in ("dispatch_level_samples", "dispatch_rise_events", "dispatch_identity_events"):
        print(f"{kind} by_tid " + " ".join(f"{perf.fmt(k)}:{v}" for k, v in sorted(by_tid[kind].items(), key=lambda kv: (-1 if kv[0] is None else kv[0]))))
        print(f"{kind} top_pc " + " ".join(f"{perf.fmt(k)}:{v}" for k, v in by_pc[kind].most_common(16)))
        for row in examples[kind]:
            print(f"  {kind} {row}")
    print("start_pc_level_events " + " ".join(f"{cycle}:{perf.fmt(tid)}" for cycle, tid in start_pc_events))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
