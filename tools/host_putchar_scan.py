#!/usr/bin/env python3
"""Compare BE putchar MMIO stores with nonsynth host putchar accepts in a VCD."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.calculator.cache_req_v_o", "dc_req_v"),
    ("be.calculator.cache_req_yumi_i", "dc_req_yumi"),
    ("be.calculator.pipe_mem.cache_req_cast_o.addr", "dc_req_addr"),
    ("be.calculator.pipe_mem.cache_req_cast_o.data", "dc_req_data"),
    ("be.calculator.pipe_mem.cache_req_cast_o.msg_type", "dc_req_msg"),
    ("be.calculator.reservation_r.pc", "res_pc"),
    ("be.calculator.reservation_r.decode.dcache_w_v", "res_dcw"),
    ("be.calculator.commit_pkt_cast_o.ctxtsw", "commit_ctxtsw"),
    ("be.calculator.commit_pkt_cast_o.npc_w_v", "commit_npc_w"),
    ("bp_nonsynth_host.putchar_w_v_li", "host_putchar"),
    ("bp_nonsynth_host.data_lo", "host_data"),
    ("bp_nonsynth_host.addr_lo", "host_addr"),
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
    if not line:
        return
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


def ch(value):
    if value is None:
        return "x"
    byte = value & 0xff
    printable = chr(byte) if 32 <= byte < 127 else "."
    return f"0x{byte:02x}({printable})"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--host-addr", type=lambda x: int(x, 0), default=0x101000)
    parser.add_argument("--max-events", type=int, default=120)
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    if args.list:
        for label, full in sorted(found.items()):
            print(f"{label:16s} {full}")
        missing = [label for _, label in WATCH if label not in found]
        if missing:
            print("missing: " + ", ".join(missing))
        return 0

    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    events = 0

    def emit(line: str):
        nonlocal events
        if events < args.max_events:
            print(line, flush=True)
            events += 1

    def finish_time():
        cycle = current_time // args.period
        if cycle < args.min_cycle:
            return
        if args.max_cycle is not None and cycle > args.max_cycle:
            return

        dc_fire = yes(values, "dc_req_v") and yes(values, "dc_req_yumi")
        dc_putchar = dc_fire and values.get("dc_req_addr") == args.host_addr
        host_putchar = yes(values, "host_putchar") and not yes(last, "host_putchar")
        if dc_putchar or host_putchar:
            emit(
                f"cycle={cycle} "
                f"dc={int(dc_putchar)} host={int(host_putchar)} "
                f"res_pc={hexv(values, 'res_pc')} res_dcw={hexv(values, 'res_dcw')} "
                f"dc_addr={hexv(values, 'dc_req_addr')} dc_data={hexv(values, 'dc_req_data')} "
                f"dc_ch={ch(values.get('dc_req_data'))} msg={hexv(values, 'dc_req_msg')} "
                f"host_addr={hexv(values, 'host_addr')} host_data={hexv(values, 'host_data')} "
                f"host_ch={ch(values.get('host_data'))} "
                f"commit_ctxtsw={hexv(values, 'commit_ctxtsw')} "
                f"commit_npc_w={hexv(values, 'commit_npc_w')}"
            )

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
                if args.max_cycle is not None and current_time // args.period > args.max_cycle:
                    break
            else:
                apply_line(line, selected, values)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
