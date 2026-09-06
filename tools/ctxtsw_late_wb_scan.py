#!/usr/bin/env python3
"""Scan ctxtsw/flush windows for late writeback and regfile side effects."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.calculator.commit_pkt_cast_o.ctxtsw$", "commit_ctxtsw"),
    ("be.calculator.commit_pkt_cast_o.npc_w_v$", "commit_npc_w"),
    ("be.calculator.commit_pkt_cast_o.pc$", "commit_pc"),
    ("be.calculator.pipe_flush_v$", "pipe_flush"),
    ("current_thread_id_lo", "cur_tid"),
    ("pending_ctxtsw_v_r", "pending_v"),
    ("be.calculator.pipe_mem.dcache_v_r", "pmem_dcv_r"),
    ("be.calculator.pipe_mem.dcache_ret_r", "pmem_ret_r"),
    ("be.calculator.pipe_mem.dcache_late_r", "pmem_late_r"),
    ("be.calculator.pipe_mem.dcache_ptw_r", "pmem_ptw_r"),
    ("be.calculator.pipe_mem.dcache_int_r", "pmem_int_r"),
    ("be.calculator.pipe_mem.dcache_float_r", "pmem_float_r"),
    ("be.calculator.pipe_mem.dcache_rd_addr_r", "pmem_rd_r"),
    ("be.calculator.pipe_mem.dcache_thread_id_r", "pmem_tid_r"),
    ("be.calculator.pipe_mem.late_wb_v_o", "pmem_late_wb"),
    ("be.calculator.pipe_mem_late_wb_v", "calc_pmem_late_wb"),
    ("be.calculator.late_wb_v_o", "calc_late_wb"),
    ("be.calculator.late_wb_force_o", "calc_late_force"),
    ("be.calculator.late_wb_pkt_cast_o.thread_id", "calc_late_tid"),
    ("be.calculator.late_wb_pkt_cast_o.rd_addr", "calc_late_rd"),
    ("be.calculator.late_wb_pkt_cast_o.ird_w_v", "calc_late_iw"),
    ("be.calculator.late_wb_pkt_cast_o.frd_w_v", "calc_late_fw"),
    ("be.scheduler.late_wb_yumi_o", "sched_late_yumi"),
    ("be.scheduler.writeback_v", "sched_writeback"),
    ("be.scheduler.int_regfile.rd_w_v_i", "irf_w"),
    ("be.scheduler.int_regfile.rd_thread_id_i", "irf_tid"),
    ("be.scheduler.int_regfile.rd_addr_i", "irf_rd"),
    ("be.detector.clear_int_v_li", "det_clear_i"),
    ("be.detector.clear_rd_li", "det_clear_rd"),
]


def parse_header(path: str):
    signals = []
    scopes: list[str] = []
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
    found = {}
    for code, full, width in signals:
        for fragment, label in WATCH:
            suffix_match = fragment.endswith("$") and full.endswith(fragment[:-1])
            contains_match = not fragment.endswith("$") and fragment in full
            if (suffix_match or contains_match) and label not in found:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--until-cycle", type=int)
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--max-events", type=int, default=200)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    if args.list:
        for label, full in sorted(found.items()):
            print(f"{label:18s} {full}")
        missing = [label for _, label in WATCH if label not in found]
        if missing:
            print("missing: " + ", ".join(missing))
        return 0

    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    interesting_until = -1
    events = 0

    def emit(line: str):
        nonlocal events
        if events < args.max_events:
            print(line, flush=True)
            events += 1

    def finish_time():
        nonlocal interesting_until
        cycle = current_time // args.period
        commit = yes(values, "commit_ctxtsw") and not yes(last, "commit_ctxtsw")
        flush = yes(values, "pipe_flush") and not yes(last, "pipe_flush")
        late = yes(values, "calc_late_wb") and not yes(last, "calc_late_wb")
        pmem_late = yes(values, "pmem_late_wb") and not yes(last, "pmem_late_wb")
        irf = yes(values, "irf_w") and not yes(last, "irf_w")
        det_clear = yes(values, "det_clear_i") and not yes(last, "det_clear_i")
        if commit or flush:
            interesting_until = max(interesting_until, cycle + args.window)
            emit(
                f"cycle={cycle} event={'commit_ctxtsw' if commit else 'flush'} "
                f"pc={hexv(values, 'commit_pc')} cur_tid={hexv(values, 'cur_tid')} "
                f"pending={hexv(values, 'pending_v')} npc_w={hexv(values, 'commit_npc_w')}"
            )
        if cycle <= interesting_until and (late or pmem_late or irf or det_clear):
            emit(
                f"  cycle={cycle} late={hexv(values, 'calc_late_wb')} "
                f"pmem_late={hexv(values, 'pmem_late_wb')} force={hexv(values, 'calc_late_force')} "
                f"yumi={hexv(values, 'sched_late_yumi')} wb={hexv(values, 'sched_writeback')} "
                f"pmem_tid={hexv(values, 'pmem_tid_r')} pmem_rd={hexv(values, 'pmem_rd_r')} "
                f"pkt_tid={hexv(values, 'calc_late_tid')} pkt_rd={hexv(values, 'calc_late_rd')} "
                f"iw={hexv(values, 'calc_late_iw')} fw={hexv(values, 'calc_late_fw')} "
                f"irf_w={hexv(values, 'irf_w')} irf_tid={hexv(values, 'irf_tid')} "
                f"irf_rd={hexv(values, 'irf_rd')} clear={hexv(values, 'det_clear_i')} "
                f"clear_rd={hexv(values, 'det_clear_rd')}"
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
                if args.until_cycle is not None and current_time // args.period > args.until_cycle:
                    break
            else:
                apply_line(line, selected, values)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
