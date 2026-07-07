#!/usr/bin/env python3
"""Trace the I-cache miss return path around a slow ctxtsw event.

This is intentionally analysis-only. It reads a TRACE=1 VCD and reports when
the old miss, target miss, memory requests, memory responses, and FE queue
recovery happen relative to a context switch.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass


PERIOD_DEFAULT = 50_000


@dataclass(frozen=True)
class SignalSpec:
    label: str
    fragments: tuple[str, ...]
    excludes: tuple[str, ...] = ()


SIGNALS = [
    SignalSpec("dispatch_v", ("be.scheduler.dispatch_pkt_cast_o.v",)),
    SignalSpec("dispatch_ctxtsw", ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v",)),
    SignalSpec("dispatch_pc", ("be.scheduler.dispatch_pkt_cast_o.pc",)),
    SignalSpec("dispatch_tid", ("be.scheduler.dispatch_pkt_cast_o.thread_id",)),
    SignalSpec("sideband_yumi", ("fe_ctxtsw_yumi_i",)),
    SignalSpec("redirect_npc", ("redirect_npc_o",)),
    SignalSpec("pc_if1", ("fe.pc_gen.pc_if1_r",)),
    SignalSpec("pc_if2", ("pc_if2_r",)),
    SignalSpec("feq_v", ("fe.controller.fe_queue_v_o",)),
    SignalSpec("iq_ack", ("be.scheduler.issue_queue.ack",)),
    SignalSpec("ic_req_v", ("fe.icache.cache_req_v_o",)),
    SignalSpec("ic_req_yumi", ("fe.icache.cache_req_yumi_i",)),
    SignalSpec("ic_req_id", ("fe.icache.cache_req_id_i",)),
    SignalSpec("ic_req_critical", ("fe.icache.cache_req_critical_i",)),
    SignalSpec("ic_req_last", ("fe.icache.cache_req_last_i",)),
    SignalSpec("ic_miss_resp", ("fe.icache.miss_resp",)),
    SignalSpec("ic_abort_resp", ("fe.icache.abort_resp",)),
    SignalSpec("ic_abort", ("fe.icache.abort_miss_r",)),
    SignalSpec("ic_abort_done", ("fe.icache.abort_complete",)),
    SignalSpec("uce_state", ("blackparrot.icache_uce.state_r",)),
    SignalSpec("uce_req_yumi", ("blackparrot.icache_uce.cache_req_yumi_o",)),
    SignalSpec("uce_req_v_r", ("blackparrot.icache_uce.cache_req_v_r",)),
    SignalSpec("uce_req_addr", ("blackparrot.icache_uce.cache_req_r.addr",)),
    SignalSpec("uce_overlap_v", ("blackparrot.icache_uce.overlap_req_v_r",)),
    SignalSpec("uce_overlap_addr", ("blackparrot.icache_uce.overlap_req_r.addr",)),
    SignalSpec("uce_overlap_accept", ("blackparrot.icache_uce.overlap_accept_li",)),
    SignalSpec("uce_overlap_send", ("blackparrot.icache_uce.overlap_send_li",)),
    SignalSpec("uce_overlap_done", ("blackparrot.icache_uce.overlap_done_li",)),
    SignalSpec("uce_fwd_v", ("blackparrot.icache_uce.fsm_fwd_v_lo",)),
    SignalSpec("uce_fwd_ready", ("blackparrot.icache_uce.fsm_fwd_ready_then_li",)),
    SignalSpec("uce_fwd_addr", ("blackparrot.icache_uce.fsm_fwd_addr_lo",)),
    SignalSpec("uce_fwd_last", ("blackparrot.icache_uce.fsm_fwd_last_lo",)),
    SignalSpec("uce_rev_v", ("blackparrot.icache_uce.fsm_rev_v_li",)),
    SignalSpec("uce_rev_yumi", ("blackparrot.icache_uce.fsm_rev_yumi_lo",)),
    SignalSpec("uce_rev_addr", ("blackparrot.icache_uce.fsm_rev_addr_li",)),
    SignalSpec("uce_rev_new", ("blackparrot.icache_uce.fsm_rev_new_li",)),
    SignalSpec("uce_rev_critical", ("blackparrot.icache_uce.fsm_rev_critical_li",)),
    SignalSpec("uce_rev_last", ("blackparrot.icache_uce.fsm_rev_last_li",)),
    SignalSpec("uce_primary_resp", ("blackparrot.icache_uce.primary_resp_li",)),
    SignalSpec("uce_overlap_resp", ("blackparrot.icache_uce.overlap_resp_li",)),
    SignalSpec("uce_load_yumi", ("blackparrot.icache_uce.load_resp_yumi_lo",)),
    SignalSpec("mem_fwd_v", ("top_fpga_inst.mem2axil.mem_fwd_v_i",)),
    SignalSpec("mem_fwd_ready", ("top_fpga_inst.mem2axil.mem_fwd_ready_and_o",)),
    SignalSpec("mem_fwd_addr", ("top_fpga_inst.mem2axil.fsm_fwd_addr_li",)),
    SignalSpec("mem_fwd_yumi", ("top_fpga_inst.mem2axil.fsm_fwd_yumi_lo",)),
    SignalSpec("mem_fwd_new", ("top_fpga_inst.mem2axil.fsm_fwd_new_li",)),
    SignalSpec("mem_fwd_last", ("top_fpga_inst.mem2axil.fsm_fwd_last_li",)),
    SignalSpec("mem_fwd_type", ("top_fpga_inst.mem2axil.fsm_fwd_header_li.msg_type.fwd",)),
    SignalSpec("mem_fwd_size", ("top_fpga_inst.mem2axil.fsm_fwd_header_li.size",)),
    SignalSpec("mem_fwd_lce", ("top_fpga_inst.mem2axil.fsm_fwd_header_li.payload.lce_id",)),
    SignalSpec("mem_fwd_uncached", ("top_fpga_inst.mem2axil.fsm_fwd_header_li.payload.uncached",)),
    SignalSpec("mem_rev_v", ("top_fpga_inst.mem2axil.mem_rev_v_o",)),
    SignalSpec("mem_rev_ready", ("top_fpga_inst.mem2axil.mem_rev_ready_and_i",)),
    SignalSpec("mem_rev_addr", ("top_fpga_inst.mem2axil.fsm_rev_addr_li",)),
    SignalSpec("mem_rev_new", ("top_fpga_inst.mem2axil.fsm_rev_new_li",)),
    SignalSpec("mem_rev_critical", ("top_fpga_inst.mem2axil.fsm_rev_critical_li",)),
    SignalSpec("mem_rev_last", ("top_fpga_inst.mem2axil.fsm_rev_last_li",)),
    SignalSpec("mem_rev_type", ("top_fpga_inst.mem2axil.fsm_rev_header_lo.msg_type.rev",)),
    SignalSpec("mem_rev_size", ("top_fpga_inst.mem2axil.fsm_rev_header_lo.size",)),
    SignalSpec("mem_rev_lce", ("top_fpga_inst.mem2axil.fsm_rev_header_lo.payload.lce_id",)),
    SignalSpec("mem_rev_uncached", ("top_fpga_inst.mem2axil.fsm_rev_header_lo.payload.uncached",)),
    SignalSpec("meta_enq", ("top_fpga_inst.mem2axil.stream_pump.stream_fifo_v_li",)),
    SignalSpec("meta_deq", ("top_fpga_inst.mem2axil.stream_pump.stream_fifo_yumi_li",)),
    SignalSpec("meta_v", ("top_fpga_inst.mem2axil.stream_pump.stream_fifo_v_lo",)),
    SignalSpec("meta_head", ("top_fpga_inst.mem2axil.stream_pump.stream_fifo_data_lo",)),
    SignalSpec("axi_arvalid", ("top_fpga_inst.mem2axil.m_axil_arvalid_o",)),
    SignalSpec("axi_arready", ("top_fpga_inst.mem2axil.m_axil_arready_i",)),
    SignalSpec("axi_araddr", ("top_fpga_inst.mem2axil.m_axil_araddr_o",)),
    SignalSpec("axi_rvalid", ("top_fpga_inst.mem2axil.m_axil_rvalid_i",)),
    SignalSpec("axi_rready", ("top_fpga_inst.mem2axil.m_axil_rready_o",)),
]


def parse_value(value: str):
    if not value or any(ch not in "01" for ch in value):
        return None
    return int(value, 2)


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
    for spec in SIGNALS:
        for code, full, width in signals:
            if all(fragment in full for fragment in spec.fragments) and not any(ex in full for ex in spec.excludes):
                selected.setdefault(code, []).append((spec.label, width))
                found[spec.label] = full
                break
    return selected, found


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
    parsed = parse_value(value)
    for label, _width in selected[code]:
        values[label] = parsed


def is_one(values, label: str) -> bool:
    return values.get(label) == 1


def rose(values, last, label: str) -> bool:
    return is_one(values, label) and last.get(label) != 1


def find_events(path: str, selected, period: int):
    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    events = []
    active = None

    def finish_time():
        nonlocal active
        cycle = current_time // period
        if rose(values, last, "dispatch_ctxtsw") and is_one(values, "dispatch_v"):
            if active is not None:
                events.append(active)
            active = {
                "dispatch": cycle,
                "pc": values.get("dispatch_pc"),
                "tid": values.get("dispatch_tid"),
                "sideband": None,
                "target": None,
                "feq": None,
            }
        if active is not None:
            if active["sideband"] is None and rose(values, last, "sideband_yumi"):
                active["sideband"] = cycle
                active["target"] = values.get("redirect_npc")
            if active["sideband"] is not None and active["feq"] is None and rose(values, last, "feq_v") and is_one(values, "iq_ack"):
                active["feq"] = cycle
        last.update(values)

    with open(path, "r", errors="replace", buffering=16 * 1024 * 1024) as f:
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
            else:
                apply_line(line, selected, values)
        finish_time()
    if active is not None:
        events.append(active)
    for idx, event in enumerate(events):
        event["idx"] = idx
        event["d_feq"] = None if event["feq"] is None else event["feq"] - event["dispatch"]
    return events


def fmt_val(label: str, value):
    if value is None:
        return "x"
    if label.endswith("addr") or label in {"dispatch_pc", "redirect_npc", "pc_if1", "pc_if2", "target", "pc"}:
        return f"0x{value:x}"
    return str(value)


def dump_window(path: str, selected, period: int, start: int, end: int, target: int | None):
    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    current_time = 0
    in_values = False

    watch_labels = [
        "dispatch_ctxtsw", "sideband_yumi", "redirect_npc", "pc_if1", "pc_if2",
        "feq_v", "iq_ack", "ic_req_yumi", "ic_req_id", "ic_req_critical",
        "ic_req_last", "ic_miss_resp", "ic_abort_resp", "ic_abort_done",
        "uce_state", "uce_req_yumi", "uce_req_v_r", "uce_req_addr",
        "uce_overlap_v", "uce_overlap_addr", "uce_overlap_accept",
        "uce_overlap_send", "uce_overlap_done", "uce_fwd_v", "uce_fwd_addr",
        "uce_fwd_last", "uce_rev_v", "uce_rev_yumi", "uce_rev_addr",
        "uce_rev_new", "uce_rev_critical", "uce_rev_last", "uce_primary_resp",
        "uce_overlap_resp", "uce_load_yumi", "mem_fwd_v", "mem_fwd_ready",
        "mem_fwd_yumi", "mem_fwd_addr", "mem_fwd_new", "mem_fwd_last",
        "mem_fwd_type", "mem_fwd_size", "mem_fwd_lce", "mem_fwd_uncached",
        "mem_rev_v", "mem_rev_ready", "mem_rev_addr", "mem_rev_new",
        "mem_rev_critical", "mem_rev_last", "meta_enq", "meta_deq", "meta_v",
        "mem_rev_type", "mem_rev_size", "mem_rev_lce", "mem_rev_uncached",
        "axi_arvalid", "axi_arready", "axi_araddr", "axi_rvalid", "axi_rready",
    ]

    interesting = [
        "dispatch_ctxtsw", "sideband_yumi", "feq_v", "ic_req_yumi",
        "ic_req_critical", "ic_req_last", "ic_miss_resp", "ic_abort_resp",
        "ic_abort_done", "uce_overlap_accept", "uce_overlap_send",
        "uce_overlap_done", "uce_fwd_v", "uce_rev_v", "uce_rev_critical",
        "uce_rev_last", "uce_primary_resp", "uce_overlap_resp", "mem_fwd_yumi",
        "mem_rev_v", "mem_rev_critical", "mem_rev_last", "meta_enq", "meta_deq",
        "axi_arvalid", "axi_rvalid",
    ]

    def finish_time():
        cycle = current_time // period
        if cycle < start:
            last.update(values)
            return
        if cycle > end:
            raise StopIteration
        changed = [label for label in watch_labels if values.get(label) != last.get(label)]
        fired = [label for label in interesting if rose(values, last, label) or (label in {"uce_fwd_v", "uce_rev_v", "mem_rev_v"} and is_one(values, label))]
        target_seen = target is not None and (
            values.get("pc_if1") == target
            or values.get("pc_if2") == target
            or values.get("uce_req_addr") == target
            or values.get("uce_overlap_addr") == target
            or values.get("uce_fwd_addr") == target
            or values.get("uce_rev_addr") == target
            or values.get("mem_fwd_addr") == target
            or values.get("mem_rev_addr") == target
        )
        if changed and (fired or target_seen or start <= cycle <= start + 8):
            parts = [f"{cycle:8d}"]
            for label in watch_labels:
                if label in changed or label in fired or label in {"uce_state", "uce_req_addr", "uce_overlap_addr", "uce_fwd_addr", "uce_rev_addr", "mem_fwd_addr", "mem_rev_addr"}:
                    parts.append(f"{label}={fmt_val(label, values.get(label))}")
            print(" ".join(parts))
        last.update(values)

    try:
        with open(path, "r", errors="replace", buffering=16 * 1024 * 1024) as f:
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
                else:
                    apply_line(line, selected, values)
            finish_time()
    except StopIteration:
        return


def summarize_window(path: str, selected, period: int, start: int, end: int, target: int | None):
    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    markers: dict[str, int] = {}
    counts = {
        "old_mem_fwd_yumi_before_target": 0,
        "old_axi_ar_before_target": 0,
        "old_mem_rev_before_target": 0,
        "target_axi_ar_count": 0,
        "target_mem_rev_count": 0,
    }
    first_old_header = None
    first_target_header = None

    def same_block(value, base):
        if value is None or base is None:
            return False
        return (value >> 6) == (base >> 6)

    def mark(name: str, cycle: int):
        markers.setdefault(name, cycle)

    def finish_time():
        nonlocal first_old_header, first_target_header
        cycle = current_time // period
        if cycle < start:
            last.update(values)
            return
        if cycle > end:
            raise StopIteration

        if rose(values, last, "dispatch_ctxtsw") and is_one(values, "dispatch_v"):
            mark("dispatch", cycle)
        if rose(values, last, "sideband_yumi"):
            mark("sideband", cycle)
        if target is not None and values.get("pc_if1") == target:
            mark("pc_if1_target", cycle)
        if target is not None and values.get("pc_if2") == target:
            mark("pc_if2_target", cycle)
        if "sideband" in markers and target is not None and rose(values, last, "ic_req_yumi"):
            mark("icache_req_yumi", cycle)
        if rose(values, last, "uce_overlap_accept"):
            mark("uce_overlap_accept", cycle)
        if target is not None and is_one(values, "uce_overlap_send") and values.get("uce_fwd_addr") == target:
            mark("uce_overlap_send_target", cycle)
        if target is not None and is_one(values, "uce_fwd_v") and values.get("uce_fwd_addr") == target:
            mark("uce_fwd_v_target", cycle)

        mem_fwd_target = target is not None and values.get("mem_fwd_addr") == target
        axi_ar_target = target is not None and is_one(values, "axi_arvalid") and same_block(values.get("axi_araddr"), target)
        mem_rev_target_block = target is not None and same_block(values.get("mem_rev_addr"), target)
        uce_rev_target_block = target is not None and same_block(values.get("uce_rev_addr"), target)

        if is_one(values, "mem_fwd_yumi"):
            if mem_fwd_target:
                mark("mem2axil_fwd_yumi_target", cycle)
                if first_target_header is None:
                    first_target_header = (
                        values.get("mem_fwd_type"),
                        values.get("mem_fwd_size"),
                        values.get("mem_fwd_lce"),
                        values.get("mem_fwd_uncached"),
                    )
            elif "mem2axil_fwd_yumi_target" not in markers:
                counts["old_mem_fwd_yumi_before_target"] += 1
                if first_old_header is None:
                    first_old_header = (
                        values.get("mem_fwd_type"),
                        values.get("mem_fwd_size"),
                        values.get("mem_fwd_lce"),
                        values.get("mem_fwd_uncached"),
                    )
        if is_one(values, "axi_arvalid"):
            if axi_ar_target:
                mark("axil_ar_target", cycle)
                counts["target_axi_ar_count"] += 1
            elif "axil_ar_target" not in markers:
                counts["old_axi_ar_before_target"] += 1
        if is_one(values, "mem_rev_v"):
            if mem_rev_target_block:
                mark("mem2axil_rev_target_block", cycle)
                counts["target_mem_rev_count"] += 1
            elif "mem2axil_rev_target_block" not in markers:
                counts["old_mem_rev_before_target"] += 1
        if uce_rev_target_block and is_one(values, "uce_rev_v") and is_one(values, "uce_rev_critical"):
            mark("uce_target_critical", cycle)
        if "sideband" in markers and rose(values, last, "ic_req_critical"):
            mark("icache_critical", cycle)
        if rose(values, last, "ic_abort_done"):
            mark("icache_abort_done", cycle)
        if rose(values, last, "uce_overlap_done"):
            mark("uce_overlap_done", cycle)
        if rose(values, last, "ic_req_last"):
            mark("icache_last", cycle)
        if rose(values, last, "feq_v") and is_one(values, "iq_ack"):
            mark("feq_dispatchable", cycle)

        last.update(values)

    try:
        with open(path, "r", errors="replace", buffering=16 * 1024 * 1024) as f:
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
                else:
                    apply_line(line, selected, values)
            finish_time()
    except StopIteration:
        pass

    ref = markers.get("dispatch", start)
    ordered = [
        "dispatch",
        "sideband",
        "pc_if1_target",
        "pc_if2_target",
        "icache_req_yumi",
        "uce_overlap_accept",
        "uce_overlap_send_target",
        "uce_fwd_v_target",
        "mem2axil_fwd_yumi_target",
        "axil_ar_target",
        "mem2axil_rev_target_block",
        "uce_target_critical",
        "icache_critical",
        "icache_abort_done",
        "uce_overlap_done",
        "icache_last",
        "feq_dispatchable",
    ]
    print("marker cycle delta")
    for name in ordered:
        cycle = markers.get(name)
        print(f"{name:28s} {str(cycle):>8} {str(None if cycle is None else cycle - ref):>6}")
    print("counts")
    for name, value in counts.items():
        print(f"{name:34s} {value}")
    print("headers type size lce uncached")
    print(f"old_before_target                  {first_old_header}")
    print(f"target                             {first_target_header}")
    return markers, counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=PERIOD_DEFAULT)
    parser.add_argument("--event", type=int)
    parser.add_argument("--dispatch-cycle", type=int)
    parser.add_argument("--target", type=lambda s: int(s, 0))
    parser.add_argument("--min-d-feq", type=int, default=20)
    parser.add_argument("--pre", type=int, default=8)
    parser.add_argument("--post", type=int, default=140)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--show-paths", action="store_true")
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    missing = [spec.label for spec in SIGNALS if spec.label not in found]
    if missing:
        print("missing: " + ", ".join(missing))
    if args.show_paths:
        for label in sorted(found):
            print(f"{label}: {found[label]}")

    if args.dispatch_cycle is not None:
        event = {
            "idx": -1,
            "dispatch": args.dispatch_cycle,
            "sideband": None,
            "feq": None,
            "d_feq": None,
            "pc": None,
            "target": args.target,
        }
        print(f"manual event dispatch={event['dispatch']} target={fmt_val('target', event['target'])}")
        start = max(0, event["dispatch"] - args.pre)
        end = event["dispatch"] + args.post
        summarize_window(args.vcd, selected, args.period, start, end, event["target"])
        if args.verbose:
            dump_window(args.vcd, selected, args.period, start, end, event["target"])
        return 0

    events = find_events(args.vcd, selected, args.period)
    if args.list:
        print("idx dispatch sideband feq d_feq tid pc target")
        for event in events:
            print(
                f"{event['idx']:3d} {event['dispatch']:8d} {str(event['sideband']):>8}"
                f" {str(event['feq']):>8} {str(event['d_feq']):>5}"
                f" {str(event['tid']):>3} 0x{(event['pc'] or 0):x} 0x{(event['target'] or 0):x}"
            )
        return 0

    if args.event is not None:
        event = events[args.event]
    else:
        event = next((e for e in events if e["d_feq"] is not None and e["d_feq"] >= args.min_d_feq), None)
        if event is None:
            raise SystemExit(f"no event found with d_feq >= {args.min_d_feq}")

    print(
        f"event {event['idx']} dispatch={event['dispatch']} sideband={event['sideband']}"
        f" feq={event['feq']} d_feq={event['d_feq']}"
        f" pc=0x{(event['pc'] or 0):x} target=0x{(event['target'] or 0):x}"
    )
    start = max(0, event["dispatch"] - args.pre)
    end = (event["feq"] or event["dispatch"]) + args.post
    dump_window(args.vcd, selected, args.period, start, end, event["target"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
