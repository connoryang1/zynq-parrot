#!/usr/bin/env python3
"""Dump FE/BE context-switch handoff signals for a small VCD cycle window."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.v$", "disp_v"),
    ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v$", "disp_ctxt"),
    ("be.scheduler.dispatch_pkt_cast_o.pc$", "disp_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id$", "disp_tid"),
    ("be.scheduler.issue_queue.ack$", "iq_ack"),
    ("be.scheduler.issue_queue.preissue_v$", "preissue_v"),
    ("be.scheduler.fe_queue_ready_and_o$", "iq_ready"),
    ("be.scheduler.fe_queue_clr_li$", "iq_clr"),
    ("be.scheduler.fe_queue_roll_li$", "iq_roll"),
    ("be.calculator.fast_ctxtsw_v_o$", "fast"),
    ("fe_ctxtsw_v_o$", "sb_v"),
    ("fe_ctxtsw_yumi_i$", "sb_yumi"),
    ("fe_ctxtsw_npc_o$", "sb_npc"),
    ("redirect_v_o$", "redir_v"),
    ("redirect_npc_o$", "redir_npc"),
    ("fe.pc_gen.pc_if1_r$", "pc_if1"),
    ("pc_if2_r$", "pc_if2"),
    ("fe.icache.v_tl_r$", "ic_v_tl"),
    ("fe.icache.v_tv_r$", "ic_v_tv"),
    ("fetch_v_i$", "fetch_v"),
    ("fe.icache.hit_v_o$", "ic_hit"),
    ("fe.icache.miss_v_o$", "ic_miss"),
    ("fe.icache.abort_miss$", "ic_abort"),
    ("fe.controller.fetch_yumi_o$", "fetch_yumi"),
    ("fe.controller.fe_queue_v_o$", "feq_v"),
    ("fe.controller.fe_queue_o.msg_type$", "feq_type"),
    ("fe.controller.fe_queue_o.pc$", "feq_pc"),
    ("be.calculator.commit_pkt_cast_o.pc$", "commit_pc"),
    ("be.calculator.commit_pkt_cast_o.ctxtsw$", "commit_ctxt"),
    ("be.calculator.commit_pkt_cast_o.instret$", "instret"),
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
    selected: dict[str, list[tuple[str, int]]] = {}
    found: dict[str, str] = {}
    for code, full, width in signals:
        for fragment, label in WATCH:
            match = full.endswith(fragment[:-1]) if fragment.endswith("$") else fragment in full
            if match and label not in found:
                selected.setdefault(code, []).append((label, width))
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
    for label, _width in selected[code]:
        values[label] = parsed


def fmt(value):
    if value is None:
        return "."
    return f"0x{value:x}" if value > 9 else str(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--min-cycle", type=int, required=True)
    parser.add_argument("--max-cycle", type=int, required=True)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    labels = [label for _, label in WATCH if label in found]
    if args.list:
        for label, full in sorted(found.items()):
            print(f"{label:12s} {full}")
        missing = [label for _, label in WATCH if label not in found]
        if missing:
            print("missing: " + ", ".join(missing))
        return 0

    print("cycle " + " ".join(labels))
    values: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    pending_cycle = None
    pending_row = None

    def capture():
        cycle = current_time // args.period
        if args.min_cycle <= cycle <= args.max_cycle:
            return cycle, f"{cycle} " + " ".join(fmt(values.get(label)) for label in labels)
        return None, None

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
                cycle, row = capture()
                if pending_row is not None and pending_cycle != cycle:
                    print(pending_row)
                pending_cycle, pending_row = cycle, row
                current_time = int(line[1:])
                if current_time // args.period > args.max_cycle:
                    break
            else:
                apply_line(line, selected, values)
        cycle, row = capture()
        if row is not None and cycle != pending_cycle:
            print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
