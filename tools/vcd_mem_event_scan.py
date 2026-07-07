#!/usr/bin/env python3
"""Scan VCD memory/translation events for selected PCs or addresses."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.pc$", "disp_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id$", "disp_tid"),
    ("be.calculator.reservation_r.pc$", "res_pc"),
    ("be.calculator.reservation_r.thread_id$", "res_tid"),
    ("be.calculator.reservation_r.isrc1$", "res_isrc1"),
    ("be.calculator.reservation_r.isrc2$", "res_isrc2"),
    ("be.calculator.pipe_mem.eaddr$", "mem_eaddr"),
    ("be.calculator.pipe_mem.trans_info_cast_i.translation_en$", "mem_trans_en"),
    ("be.calculator.pipe_mem.trans_info_cast_i.priv_mode$", "mem_priv"),
    ("be.calculator.pipe_mem.trans_info_cast_i.base_ppn$", "mem_base_ppn"),
    ("be.calculator.pipe_mem.dtlb_v_lo$", "mem_dtlb_v"),
    ("be.calculator.pipe_mem.dtlb_ptag_lo$", "mem_dtlb_ptag"),
    ("be.calculator.pipe_mem.dcache.v_tv_r$", "dc_v_tv"),
    ("be.calculator.pipe_mem.dcache.thread_id_tv_r$", "dc_tid_tv"),
    ("be.calculator.pipe_mem.dcache.paddr_tv_r$", "dc_paddr_tv"),
    ("be.calculator.pipe_mem.dcache.ptag_i$", "dc_ptag_i"),
    ("be.calculator.pipe_mem.dcache.ptag_v_i$", "dc_ptag_v"),
    ("be.calculator.pipe_mem.dcache.load_hit_tv$", "dc_load_hit"),
    ("be.calculator.pipe_mem.dcache.store_hit_tv$", "dc_store_hit"),
    ("be.calculator.pipe_mem.dcache.cache_hit_tv$", "dc_cache_hit"),
    ("be.calculator.pipe_mem.dcache.any_miss_tv$", "dc_any_miss"),
    ("be.calculator.pipe_mem.dcache.ld_data_dword_merged$", "dc_load_data"),
    ("be.calculator.pipe_mem.early_v_o$", "mem_early_v"),
    ("be.calculator.pipe_mem.early_data_o$", "mem_early_data"),
    ("be.calculator.pipe_mem.final_v_o$", "mem_final_v"),
    ("be.calculator.pipe_mem.final_data_o$", "mem_final_data"),
    ("be.calculator.pipe_mem.cache_replay_v_o$", "mem_replay"),
    ("be.calculator.cache_req_v_o$", "dc_req_v"),
    ("be.calculator.cache_req_yumi_i$", "dc_req_yumi"),
    ("be.calculator.pipe_mem.cache_req_cast_o.addr$", "dc_req_addr"),
    ("be.calculator.pipe_mem.cache_req_cast_o.data$", "dc_req_data"),
    ("be.calculator.commit_pkt_cast_o.pc$", "commit_pc"),
    ("be.calculator.commit_pkt_cast_o.vaddr$", "commit_vaddr"),
    ("be.calculator.commit_pkt_cast_o.instret$", "instret"),
    ("be.scheduler.current_thread_id_i$", "sched_cur_tid"),
    ("be.scheduler.retire_thread_id_i$", "sched_ret_tid"),
    ("be.scheduler.ptw.addr_o$", "ptw_addr"),
    ("be.scheduler.ptw.pte_o$", "ptw_pte"),
    ("be.scheduler.ptw.data_i$", "ptw_data"),
    ("be.scheduler.ptw.trans_info_cast_i.base_ppn$", "ptw_base_ppn"),
    ("be.scheduler.ptw.state_r$", "ptw_state"),
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
                    _width, code, raw = match.groups()
                    signals.append((code, ".".join(scopes + [raw.split()[0]])))
    return signals


def select(signals):
    selected: dict[str, list[str]] = {}
    found: dict[str, str] = {}
    for code, full in signals:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--pc", type=lambda x: int(x, 0), action="append", default=[])
    parser.add_argument("--addr", type=lambda x: int(x, 0), action="append", default=[])
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    labels = [label for _, label in WATCH if label in found]
    print("cycle reason " + " ".join(labels))

    pcs = set(args.pc)
    addrs = set(args.addr)
    values: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    emitted = 0
    last_row = None

    def maybe_emit():
        nonlocal emitted, last_row
        cycle = current_time // args.period
        if cycle < args.min_cycle:
            return False
        if args.max_cycle is not None and cycle > args.max_cycle:
            return True

        reasons = []
        for label in ("disp_pc", "res_pc", "commit_pc"):
            if values.get(label) in pcs:
                reasons.append(label)
        for label in ("mem_eaddr", "commit_vaddr", "dc_req_addr", "ptw_addr"):
            if values.get(label) in addrs:
                reasons.append(label)
        if not reasons:
            return False

        row_values = tuple(values.get(label) for label in labels)
        row = (cycle, ",".join(reasons), row_values)
        if row == last_row:
            return False
        print(f"{cycle} {row[1]} " + " ".join(fmt(value) for value in row_values))
        emitted += 1
        last_row = row
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
