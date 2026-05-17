#!/usr/bin/env python3
"""Summarize context-switch timing deltas from a BlackParrot VCD."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.v", "dispatch_v"),
    ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v", "dispatch_ctxtsw"),
    ("be.scheduler.dispatch_pkt_cast_o.pc", "dispatch_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.instr.t.itype.opcode", "dispatch_opcode"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id", "dispatch_tid"),
    ("be.calculator.fast_ctxtsw_v_o", "fast_ctxtsw"),
    ("pending_ctxtsw_v_r", "pending_v"),
    ("ctxtsw_launch_lo", "launch"),
    ("fe_ctxtsw_v_o", "sideband_v"),
    ("fe_ctxtsw_yumi_i", "sideband_yumi"),
    ("redirect_v_o", "redirect_v"),
    ("redirect_npc_o", "redirect_npc"),
    ("fe.pc_gen.pc_if1_r", "pc_if1"),
    ("pc_if2_r", "pc_if2"),
    ("fe.icache.hit_v_o", "ic_hit"),
    ("fetch_v_i", "fetch_v"),
    ("fe.controller.fe_queue_v_o", "feq_v"),
    ("fe.controller.fetch_yumi_o", "fetch_yumi"),
    ("be.scheduler.issue_queue.ack", "iq_ack"),
    ("be.scheduler.issue_queue.preissue_v", "preissue_v"),
    ("be.scheduler.fe_queue_ready_and_o", "iq_ready"),
    ("be.scheduler.fe_queue_clr_li", "iq_clr"),
    ("be.scheduler.ctxtsw_queue_hold_li", "ctxtsw_hold"),
    ("be.scheduler.ctxtsw_issue_hold_r", "ctxtsw_hold_r"),
    ("be.calculator.commit_pkt_cast_o.ctxtsw$", "commit_ctxtsw"),
    ("be.calculator.commit_pkt_cast_o.instret$", "commit_instret"),
    ("be.calculator.pipe_flush_v$", "pipe_flush"),
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


def is_one(values, label: str) -> bool:
    return values.get(label) == 1


def rose(values, last, label: str) -> bool:
    return is_one(values, label) and last.get(label) != 1


def fmt(value):
    return "x" if value is None else f"0x{value:x}"


def delta(start, end):
    return "-" if start is None or end is None else str(end - start)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--timeline", type=int, metavar="CYCLE")
    parser.add_argument("--around", type=int, default=8)
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
    current_time = 0
    in_values = False
    rows = []
    active = None
    timeline_rows = []

    def finish_time():
        nonlocal active
        cycle = current_time // args.period
        if args.timeline is not None and args.timeline - args.around <= cycle <= args.timeline + args.around:
            timeline_rows.append(
                (
                    cycle,
                    {
                        label: values.get(label)
                        for label in [
                            "dispatch_v",
                            "dispatch_ctxtsw",
                            "dispatch_pc",
                            "fast_ctxtsw",
                            "pending_v",
                            "sideband_v",
                            "sideband_yumi",
                            "redirect_v",
                            "pc_if1",
                            "pc_if2",
                            "ic_hit",
                            "fetch_v",
                            "fetch_yumi",
                            "feq_v",
                            "iq_ack",
                            "iq_ready",
                            "iq_clr",
                            "ctxtsw_hold",
                            "ctxtsw_hold_r",
                            "commit_ctxtsw",
                            "commit_instret",
                            "pipe_flush",
                        ]
                    },
                )
            )
        if cycle < args.min_cycle:
            for label in found:
                last[label] = values.get(label)
            return

        dispatch_ctxtsw = rose(values, last, "dispatch_ctxtsw") and is_one(values, "dispatch_v")
        if dispatch_ctxtsw:
            if active is not None:
                active["next_ctxtsw"] = cycle
                rows.append(active)
            active = {
                "dispatch": cycle,
                "pc": values.get("dispatch_pc"),
                "tid": values.get("dispatch_tid"),
                "target": None,
                "fast": None,
                "sideband": None,
                "redirect": None,
                "pc_if1": None,
                "pc_if2": None,
                "feq": None,
                "first_dispatch": None,
                "next_ctxtsw": None,
                "commit": None,
            }
        if active is not None:
            if active["fast"] is None and rose(values, last, "fast_ctxtsw"):
                active["fast"] = cycle
            if active["sideband"] is None and rose(values, last, "sideband_yumi"):
                active["sideband"] = cycle
                active["target"] = values.get("redirect_npc")
            if active["redirect"] is None and rose(values, last, "redirect_v"):
                active["redirect"] = cycle
                if active["target"] is None:
                    active["target"] = values.get("redirect_npc")
            target = active["target"]
            if active["pc_if1"] is None and active["sideband"] is not None and values.get("pc_if1") == target:
                active["pc_if1"] = cycle
            if active["pc_if2"] is None and active["sideband"] is not None and values.get("pc_if2") == target:
                active["pc_if2"] = cycle
            if active["feq"] is None and active["sideband"] is not None and rose(values, last, "feq_v") and is_one(values, "iq_ack"):
                active["feq"] = cycle
            if active["first_dispatch"] is None and active["sideband"] is not None and rose(values, last, "dispatch_v"):
                active["first_dispatch"] = cycle
            if active["commit"] is None and rose(values, last, "commit_ctxtsw"):
                active["commit"] = cycle
            if active["first_dispatch"] is not None and active["commit"] is not None:
                rows.append(active)
                active = None

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
                cycle = current_time // args.period
                if args.timeline is not None and cycle > args.timeline + args.around:
                    break
                if args.max_cycle is not None and cycle > args.max_cycle:
                    break
                if args.timeline is None and len(rows) >= args.limit:
                    break
            else:
                apply_line(line, selected, values)
        finish_time()

    if args.timeline is not None:
        labels = [
            "cycle",
            "disp",
            "ctxt",
            "pc",
            "fast",
            "pend",
            "sb_v",
            "sb_y",
            "redir",
            "if1",
            "if2",
            "hit",
            "fetch",
            "fyumi",
            "feq",
            "ack",
            "ready",
            "clr",
            "hold",
            "hold_r",
            "c_ctxt",
            "c_inst",
            "flush",
        ]
        print(" ".join(f"{label:>8s}" for label in labels))
        for cycle, vals in timeline_rows:
            def bit(label):
                value = vals.get(label)
                return "." if value is None else str(value)

            print(
                f"{cycle:8d} "
                f"{bit('dispatch_v'):>8s} {bit('dispatch_ctxtsw'):>8s} {fmt(vals.get('dispatch_pc')):>8s} "
                f"{bit('fast_ctxtsw'):>8s} {bit('pending_v'):>8s} "
                f"{bit('sideband_v'):>8s} {bit('sideband_yumi'):>8s} {bit('redirect_v'):>8s} "
                f"{fmt(vals.get('pc_if1')):>8s} {fmt(vals.get('pc_if2')):>8s} "
                f"{bit('ic_hit'):>8s} {bit('fetch_v'):>8s} {bit('fetch_yumi'):>8s} "
                f"{bit('feq_v'):>8s} {bit('iq_ack'):>8s} {bit('iq_ready'):>8s} "
                f"{bit('iq_clr'):>8s} {bit('ctxtsw_hold'):>8s} {bit('ctxtsw_hold_r'):>8s} "
                f"{bit('commit_ctxtsw'):>8s} {bit('commit_instret'):>8s} {bit('pipe_flush'):>8s}"
            )
        return 0

    print(
        "idx dispatch pc tid fast sideband pc_if1 pc_if2 feq first next_ctxtsw commit "
        "d_fast d_side d_if1 d_if2 d_feq d_first d_next d_commit"
    )
    for idx, row in enumerate(rows[: args.limit]):
        start = row["dispatch"]
        print(
            f"{idx:3d} {start:8d} {fmt(row['pc']):>10s} {fmt(row['tid']):>4s} "
            f"{str(row['fast']):>8s} {str(row['sideband']):>8s} "
            f"{str(row['pc_if1']):>8s} {str(row['pc_if2']):>8s} "
            f"{str(row['feq']):>8s} {str(row['first_dispatch']):>8s} "
            f"{str(row['next_ctxtsw']):>10s} {str(row['commit']):>8s} "
            f"{delta(start, row['fast']):>6s} {delta(start, row['sideband']):>6s} "
            f"{delta(start, row['pc_if1']):>5s} {delta(start, row['pc_if2']):>5s} "
            f"{delta(start, row['feq']):>5s} {delta(start, row['first_dispatch']):>7s} "
            f"{delta(start, row['next_ctxtsw']):>6s} {delta(start, row['commit']):>8s}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
