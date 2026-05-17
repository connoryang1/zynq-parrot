#!/usr/bin/env python3
"""Scan a VCD for side-effect requests between ctxtsw issue and commit."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.scheduler.issue_ctxtsw_v", "issue_ctxtsw"),
    ("be.scheduler.dispatch_pkt_cast_o.v", "dispatch_v"),
    ("be.scheduler.dispatch_pkt_cast_o.pc", "dispatch_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id", "dispatch_tid"),
    ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v", "dispatch_ctxtsw"),
    ("be.calculator.fast_ctxtsw_v_o", "fast_ctxtsw"),
    ("be.calculator.reservation_r.v", "res_v"),
    ("be.calculator.reservation_r.pc", "res_pc"),
    ("be.calculator.reservation_r.decode.dcache_w_v", "res_dcw"),
    ("be.calculator.reservation_r.decode.dcache_r_v", "res_dcr"),
    ("be.calculator.cache_req_v_o", "dc_req_v"),
    ("be.calculator.cache_req_yumi_i", "dc_req_yumi"),
    ("be.calculator.pipe_mem.cache_req_cast_o.addr", "dc_req_addr"),
    ("be.calculator.pipe_mem.cache_req_cast_o.data", "dc_req_data"),
    ("be.calculator.pipe_mem.cache_req_cast_o.msg_type", "dc_req_msg"),
    ("blackparrot.core_minimal.be.commit_pkt.ctxtsw", "commit_ctxtsw"),
    ("blackparrot.core_minimal.be.commit_pkt.npc_w_v", "commit_npc_w"),
    ("blackparrot.core_minimal.be.commit_pkt.instret", "instret"),
    ("blackparrot.core_minimal.be.commit_pkt.pc", "commit_pc"),
    ("current_thread_id_lo", "cur_tid"),
    ("pending_ctxtsw_v_r", "pending_v"),
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
                    name = raw.split()[0]
                    signals.append((code, ".".join(scopes + [name]), int(width)))
    return signals


def select(signals):
    selected: dict[str, list[tuple[str, int]]] = {}
    found: dict[str, str] = {}
    for code, full, width in signals:
        for fragment, label in WATCH:
            if fragment in full and label not in found:
                selected.setdefault(code, []).append((label, width))
                found[label] = full
    return selected, found


def parse_value(value: str):
    if not value or any(ch not in "01" for ch in value):
        return None
    return int(value, 2)


def apply_line(line: str, selected, values):
    code = None
    value = None
    if line[0] in "bB":
        parts = line.split()
        if len(parts) == 2:
            value, code = parts[0][1:], parts[1]
    elif line[0] in "01xXzZ":
        value, code = line[0], line[1:]
    if code not in selected or value is None:
        return
    for label, _width in selected[code]:
        values[label] = parse_value(value)


def yes(values, label: str) -> bool:
    return values.get(label) == 1


def hexv(values, label: str) -> str:
    value = values.get(label)
    return "x" if value is None else f"0x{value:x}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--host-addr", type=lambda x: int(x, 0), default=0x101000)
    parser.add_argument("--max-events", type=int, default=40)
    parser.add_argument("--until-cycle", type=int)
    parser.add_argument(
        "--print-host",
        action="store_true",
        help="print all host MMIO stores, not only stores before ctxtsw commit",
    )
    parser.add_argument(
        "--host-window",
        type=int,
        default=20,
        help="cycles after each ctxtsw issue/commit to print host stores with --print-host",
    )
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    missing = [label for _, label in WATCH if label not in found]
    if args.list:
        for label, full in sorted(found.items()):
            print(f"{label:16s} {full}")
        if missing:
            print("missing: " + ", ".join(missing))
        return 0
    if missing:
        print("missing: " + ", ".join(missing))

    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    active = False
    window_start = None
    window_pc = None
    recent_ctxtsw_cycle = None
    recent_ctxtsw_pc = None
    windows = 0
    mmio_in_windows = 0
    events = 0
    current_time = 0
    in_values = False

    def finish_time():
        nonlocal active, window_start, window_pc, recent_ctxtsw_cycle, recent_ctxtsw_pc
        nonlocal windows, mmio_in_windows, events
        cycle = current_time // args.period
        issue_rise = yes(values, "issue_ctxtsw") and not yes(last, "issue_ctxtsw")
        commit_rise = yes(values, "commit_ctxtsw") and not yes(last, "commit_ctxtsw")
        dcache_fire = yes(values, "dc_req_v") and yes(values, "dc_req_yumi")
        addr = values.get("dc_req_addr")
        host_fire = dcache_fire and addr == args.host_addr

        if issue_rise and yes(values, "dispatch_v"):
            active = True
            window_start = cycle
            window_pc = values.get("dispatch_pc")
            recent_ctxtsw_cycle = cycle
            recent_ctxtsw_pc = values.get("dispatch_pc")
            windows += 1
            if events < args.max_events:
                print(
                    f"ctxtsw_issue cycle={cycle} pc={hexv(values, 'dispatch_pc')} "
                    f"tid={hexv(values, 'dispatch_tid')} cur_tid={hexv(values, 'cur_tid')}"
                    , flush=True
                )
                events += 1

        if active and host_fire:
            mmio_in_windows += 1
            if events < args.max_events:
                char = values.get("dc_req_data")
                ch = (char or 0) & 0xff
                printable = chr(ch) if 32 <= ch < 127 else "."
                print(
                    f"  host_store_before_commit cycle={cycle} "
                    f"window_start={window_start} ctxtsw_pc=0x{window_pc:x} "
                    f"res_pc={hexv(values, 'res_pc')} data={hexv(values, 'dc_req_data')} "
                    f"char=0x{ch:02x}({printable}) msg={hexv(values, 'dc_req_msg')}"
                    , flush=True
                )
                events += 1

        near_recent_ctxtsw = (
            recent_ctxtsw_cycle is not None
            and cycle - recent_ctxtsw_cycle <= args.host_window
        )
        if args.print_host and host_fire and near_recent_ctxtsw:
            if events < args.max_events:
                char = values.get("dc_req_data")
                ch = (char or 0) & 0xff
                printable = chr(ch) if 32 <= ch < 127 else "."
                print(
                    f"  host_store cycle={cycle} recent_ctxtsw={recent_ctxtsw_cycle} "
                    f"ctxtsw_pc="
                    f"{'x' if recent_ctxtsw_pc is None else hex(recent_ctxtsw_pc)} "
                    f"commit_ctxtsw={hexv(values, 'commit_ctxtsw')} "
                    f"commit_npc_w={hexv(values, 'commit_npc_w')} "
                    f"instret={hexv(values, 'instret')} "
                    f"commit_pc={hexv(values, 'commit_pc')} "
                    f"res_v={hexv(values, 'res_v')} res_pc={hexv(values, 'res_pc')} "
                    f"data={hexv(values, 'dc_req_data')} char=0x{ch:02x}({printable}) "
                    f"msg={hexv(values, 'dc_req_msg')}"
                    , flush=True
                )
                events += 1

        if active and commit_rise:
            recent_ctxtsw_cycle = cycle
            recent_ctxtsw_pc = values.get("commit_pc")
            if events < args.max_events:
                print(
                    f"ctxtsw_commit cycle={cycle} start={window_start} "
                    f"commit_pc={hexv(values, 'commit_pc')} cur_tid={hexv(values, 'cur_tid')}"
                    , flush=True
                )
                events += 1
            active = False
            window_start = None
            window_pc = None

        for label in found:
            last[label] = values.get(label)

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
                if args.until_cycle is not None and current_time // args.period > args.until_cycle:
                    break
            else:
                apply_line(line, selected, values)
        finish_time()

    print(
        f"summary windows={windows} host_stores_before_commit={mmio_in_windows} "
        f"host_addr=0x{args.host_addr:x}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
