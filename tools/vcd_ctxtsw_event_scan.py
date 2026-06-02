#!/usr/bin/env python3
"""Scan a zynq-parrot context-switch VCD for sparse debug events."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.v$", "disp_v"),
    ("be.scheduler.dispatch_pkt_cast_o.pc$", "disp_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id$", "disp_tid"),
    ("be.calculator.reservation_r.v$", "res_v"),
    ("be.calculator.reservation_r.pc$", "res_pc"),
    ("be.calculator.reservation_r.thread_id$", "res_tid"),
    ("be.calculator.pipe_mem.eaddr$", "mem_eaddr"),
    ("be.calculator.pipe_mem.final_v_o$", "mem_final_v"),
    ("be.calculator.pipe_mem.final_data_o$", "mem_final_data"),
    ("be.calculator.pipe_mem.cache_replay_v_o$", "mem_replay"),
    ("be.calculator.pipe_mem.dcache_busy_lo$", "mem_busy"),
    ("be.calculator.pipe_mem.dcache.uncached_tv_r$", "dc_uncached"),
    ("be.calculator.pipe_mem.dcache.nonblocking_req$", "dc_nb_req"),
    ("be.calculator.pipe_mem.dcache.nonblocking_sent$", "dc_nb_sent"),
    ("be.calculator.pipe_mem.dcache.cache_req_v_o$", "dcache_req_v"),
    ("be.calculator.cache_req_yumi_i$", "dc_req_yumi"),
    ("be.calculator.pipe_mem.cache_req_cast_o.addr$", "dc_req_addr"),
    ("be.calculator.pipe_mem.cache_req_cast_o.data$", "dc_req_data"),
    ("blackparrot.dcache_uce.cache_req_v_i$", "uce_req_v"),
    ("blackparrot.dcache_uce.cache_req_yumi_o$", "uce_req_yumi"),
    ("blackparrot.dcache_uce.credit_count_lo$", "uce_credit"),
    ("be.calculator.commit_pkt_cast_o.pc$", "commit_pc"),
    ("be.calculator.commit_pkt_cast_o.vaddr$", "commit_vaddr"),
    ("be.calculator.commit_pkt_cast_o.instret$", "instret"),
    ("be.scheduler.current_thread_id_i$", "sched_cur_tid"),
    ("be.scheduler.retire_thread_id_i$", "sched_ret_tid"),
]


def parse_header(path: str):
    scopes: list[str] = []
    signals = []
    scope_re = re.compile(r"\$scope\s+\w+\s+(\S+)")
    var_re = re.compile(r"\$var\s+\w+\s+(\d+)\s+(\S+)\s+(.+?)\s+\$end")
    with open(path, "r", errors="replace", buffering=8 * 1024 * 1024) as f:
        for line in f:
            if "$enddefinitions" in line:
                break
            if "$scope" in line:
                match = scope_re.search(line)
                if match:
                    scopes.append(match.group(1))
            elif "$upscope" in line:
                if scopes:
                    scopes.pop()
            elif "$var" in line:
                match = var_re.search(line.rstrip())
                if match:
                    width, code, raw = match.groups()
                    signals.append((code, ".".join(scopes + [raw.split()[0]]), int(width)))
    return signals


def select(signals):
    selected: dict[str, list[str]] = {}
    found: dict[str, str] = {}
    for code, full, _width in signals:
        for fragment, label in WATCH:
            match = full.endswith(fragment[:-1]) if fragment.endswith("$") else fragment in full
            if match and label not in found:
                selected.setdefault(code, []).append(label)
                found[label] = full
    return selected, found


def parse_value(value: str):
    if not value or any(ch not in "01" for ch in value):
        return None
    return int(value, 2)


def apply_line(line: str, selected, values):
    if not line:
        return
    if line[0] in "bB":
        parts = line.split()
        if len(parts) != 2:
            return
        value, code = parts[0][1:], parts[1]
    elif line[0] in "01xXzZ":
        value, code = line[0], line[1:]
    else:
        return
    if code not in selected:
        return
    parsed = parse_value(value)
    for label in selected[code]:
        values[label] = parsed


def fmt(value):
    if value is None:
        return "x"
    return f"0x{value:x}" if value > 9 else str(value)


def interesting(values, watch_addr, test_va, pcs, include_uce, progress_only):
    reasons = []
    dc_addr = values.get("dc_req_addr")
    if dc_addr == watch_addr:
        reasons.append("progress_store")
    if progress_only:
        return ",".join(reasons)

    mem_eaddr = values.get("mem_eaddr")
    commit_vaddr = values.get("commit_vaddr")
    for label in ("disp_pc", "res_pc", "commit_pc"):
        if values.get(label) in pcs:
            reasons.append(label)
    if dc_addr == test_va or mem_eaddr == test_va or commit_vaddr == test_va:
        reasons.append("test_va")
    if include_uce and (values.get("dc_nb_req") or values.get("dc_nb_sent") or values.get("uce_req_v") or values.get("uce_req_yumi")):
        reasons.append("uce")
    return ",".join(reasons)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--watch-addr", type=lambda x: int(x, 0), default=0x80007000)
    parser.add_argument("--test-va", type=lambda x: int(x, 0), default=0x40000000)
    parser.add_argument("--pc", type=lambda x: int(x, 0), action="append", default=[])
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--include-uce", action="store_true")
    parser.add_argument("--progress-only", action="store_true")
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    labels = [label for _, label in WATCH if label in found]
    print("cycle reason " + " ".join(labels))

    values: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    emitted = 0
    last_row = None
    pcs = set(args.pc)

    def maybe_emit():
        nonlocal emitted, last_row
        cycle = current_time // args.period
        if cycle < args.min_cycle:
            return False
        if args.max_cycle is not None and cycle > args.max_cycle:
            return True
        reason = interesting(
            values,
            args.watch_addr,
            args.test_va,
            pcs,
            args.include_uce,
            args.progress_only,
        )
        if not reason:
            return False
        row_values = tuple(values.get(label) for label in labels)
        row_key = (reason, values.get("dc_req_addr"), values.get("dc_req_data")) if args.progress_only else (cycle, reason, row_values)
        row = (cycle, reason, row_values)
        if row == last_row:
            return False
        if row_key == last_row:
            return False
        print(f"{cycle} {reason} " + " ".join(fmt(value) for value in row[2]))
        emitted += 1
        last_row = row_key
        return emitted >= args.limit

    with open(args.vcd, "r", errors="replace", buffering=16 * 1024 * 1024) as f:
        start_time = max(0, (args.min_cycle - 8) * args.period)
        for raw in f:
            line = raw.rstrip()
            if not in_values:
                if "$dumpvars" in line:
                    in_values = True
                continue
            if line.startswith("#"):
                if maybe_emit():
                    break
                current_time = int(line[1:])
            else:
                if current_time < start_time:
                    continue
                apply_line(line, selected, values)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
