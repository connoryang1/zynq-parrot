#!/usr/bin/env python3
"""Find selected dispatch/commit PCs in a BlackParrot context-switch VCD."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.v", "dispatch_v"),
    ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v", "dispatch_ctxtsw"),
    ("be.scheduler.dispatch_pkt_cast_o.pc", "dispatch_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id", "dispatch_tid"),
    ("be.scheduler.issue_ctxtsw_v", "issue_ctxtsw"),
    ("be.scheduler.issue_queue.preissue_v", "preissue_v"),
    ("be.scheduler.issue_queue.ack", "iq_ack"),
    ("be.scheduler.fe_queue_ready_and_o", "iq_ready"),
    ("be.calculator.commit_pkt_cast_o.ctxtsw$", "commit_ctxtsw"),
    ("be.calculator.commit_pkt_cast_o.instret$", "commit_instret"),
    ("be.calculator.commit_pkt_cast_o.pc$", "commit_pc"),
    ("be.calculator.commit_pkt_cast_o.thread_id$", "commit_tid"),
    ("be.calculator.fast_ctxtsw_v_o", "fast_ctxtsw"),
    ("ctxtsw_launch_lo", "launch"),
    ("fe_ctxtsw_v_o", "sideband_v"),
    ("fe_ctxtsw_yumi_i", "sideband_yumi"),
    ("fe_ctxtsw_npc_o", "sideband_npc"),
    ("redirect_v_o", "redirect_v"),
    ("redirect_npc_o", "redirect_npc"),
    ("fe.pc_gen.pc_if1_r", "pc_if1"),
    ("pc_if2_r", "pc_if2"),
    ("fe.icache.hit_v_o", "ic_hit"),
    ("fe.icache.miss_v_o", "ic_miss"),
    ("fe.controller.fetch_yumi_o", "fetch_yumi"),
    ("fe.controller.fe_queue_v_o", "feq_v"),
    ("pending_ctxtsw_v_r", "pending_v"),
    ("pending_ctxtsw_sent_r", "sent"),
    ("current_thread_id_lo", "cur_tid"),
]


DEFAULT_PCS = {
    0x800006AC: "warm_t0_to_t1",
    0x800013B8: "warm_t1_to_t0",
    0x80000D2A: "timed_t0_to_t1",
    0x800011AC: "timed_t1_to_t0",
    0x80000F80: "t1_entry_ld",
    0x80000F84: "t1_entry_rdcycle",
    0x80000F88: "t1_stream_start",
}


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
    selected = {}
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


def bit(values, label: str) -> str:
    value = values.get(label)
    return "." if value is None else str(value)


def hx(values, label: str) -> str:
    value = values.get(label)
    return "." if value is None else f"0x{value:x}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--pc", action="append", type=lambda text: int(text, 0))
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()

    pcs = {pc: DEFAULT_PCS.get(pc, f"pc_{pc:x}") for pc in (args.pc or DEFAULT_PCS)}
    selected, found = select(parse_header(args.vcd))
    missing = [label for _, label in WATCH if label not in found]
    if missing:
        print("missing: " + ", ".join(missing))

    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    count = 0

    def finish_time():
        nonlocal count
        cycle = current_time // args.period
        if cycle < args.min_cycle:
            last.update(values)
            return
        dispatch_pc = values.get("dispatch_pc")
        commit_pc = values.get("commit_pc")
        dispatch_hit = values.get("dispatch_v") == 1 and dispatch_pc in pcs
        commit_hit = values.get("commit_instret") == 1 and commit_pc in pcs
        ctxtsw_edge = values.get("dispatch_ctxtsw") == 1 and last.get("dispatch_ctxtsw") != 1
        sideband_edge = values.get("sideband_yumi") == 1 and last.get("sideband_yumi") != 1
        if dispatch_hit or commit_hit or ctxtsw_edge or sideband_edge:
            if count == 0:
                print(
                    "cycle event pc name tid d_v d_ctxt issue fast launch sb_v sb_y "
                    "redir if1 if2 hit miss fyumi feq ack ready pending sent cur_tid "
                    "c_pc c_tid c_ctxt c_inst"
                )
            event = "dispatch" if dispatch_hit else "commit" if commit_hit else "ctxtsw_edge" if ctxtsw_edge else "sideband"
            pc = dispatch_pc if dispatch_hit or ctxtsw_edge else commit_pc
            print(
                f"{cycle} {event} {hx({'pc': pc}, 'pc')} {pcs.get(pc, '-')} "
                f"{bit(values, 'dispatch_tid')} {bit(values, 'dispatch_v')} "
                f"{bit(values, 'dispatch_ctxtsw')} {bit(values, 'issue_ctxtsw')} "
                f"{bit(values, 'fast_ctxtsw')} {bit(values, 'launch')} "
                f"{bit(values, 'sideband_v')} {bit(values, 'sideband_yumi')} "
                f"{bit(values, 'redirect_v')} {hx(values, 'pc_if1')} {hx(values, 'pc_if2')} "
                f"{bit(values, 'ic_hit')} {bit(values, 'ic_miss')} {bit(values, 'fetch_yumi')} "
                f"{bit(values, 'feq_v')} {bit(values, 'iq_ack')} {bit(values, 'iq_ready')} "
                f"{bit(values, 'pending_v')} {bit(values, 'sent')} {bit(values, 'cur_tid')} "
                f"{hx(values, 'commit_pc')} {bit(values, 'commit_tid')} "
                f"{bit(values, 'commit_ctxtsw')} {bit(values, 'commit_instret')}"
            )
            count += 1
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
                if args.max_cycle is not None and cycle > args.max_cycle:
                    break
                if count >= args.limit:
                    break
            else:
                apply_line(line, selected, values)
        finish_time()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
