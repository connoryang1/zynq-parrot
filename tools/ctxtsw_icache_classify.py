#!/usr/bin/env python3
"""Classify context-switch timing by frontend/I-cache behavior in a BP VCD."""

from __future__ import annotations

import argparse
import collections
import re


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.v", "dispatch_v"),
    ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v", "dispatch_ctxtsw"),
    ("be.scheduler.dispatch_pkt_cast_o.pc", "dispatch_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id", "dispatch_tid"),
    ("be.calculator.fast_ctxtsw_v_o", "fast_ctxtsw"),
    ("fe_ctxtsw_yumi_i", "sideband_yumi"),
    ("redirect_npc_o", "redirect_npc"),
    ("fe.pc_gen.pc_if1_r", "pc_if1"),
    ("pc_if2_r", "pc_if2"),
    ("fe.icache.hit_v_o", "ic_hit"),
    ("fe.icache.miss_v_o", "ic_miss"),
    ("fe.icache.state_r", "ic_state"),
    ("fe.icache.abort_miss", "ic_abort_comb"),
    ("fe.icache.abort_miss_r", "ic_abort"),
    ("fe.icache.abort_complete", "ic_abort_done"),
    ("fe.icache.cache_req_yumi_i", "ic_req_yumi"),
    ("fe.icache.cache_req_critical_i", "ic_req_critical"),
    ("fe.icache.cache_req_last_i", "ic_req_last"),
    ("fe.controller.fe_queue_v_o", "feq_v"),
    ("be.scheduler.issue_queue.ack", "iq_ack"),
    ("be.scheduler.dispatch_pkt_cast_o.v", "first_dispatch_v"),
    ("be.calculator.commit_pkt_cast_o.ctxtsw$", "commit_ctxtsw"),
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
            suffix = fragment.endswith("$") and full.endswith(fragment[:-1])
            contains = not fragment.endswith("$") and fragment in full
            if (suffix or contains) and label not in found:
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


def delta(start, end):
    return None if start is None or end is None else end - start


def finish_active(active):
    if active is None:
        return None
    d_feq = delta(active["dispatch"], active["feq"])
    d_first = delta(active["dispatch"], active["first_dispatch"])
    d_next = delta(active["dispatch"], active["next_ctxtsw"])
    path = "unknown"
    if active["aborted"]:
        path = "abort_old_miss"
    elif active["if2_hit"] == 1 and (d_feq is not None and d_feq <= 4):
        path = "hot_hit"
    elif d_feq is not None and d_feq > 8:
        path = "target_or_source_miss"
    elif d_next is not None and d_next <= 5:
        path = "overlapped_next_ctxtsw"
    return {
        **active,
        "d_feq": d_feq,
        "d_first": d_first,
        "d_next": d_next,
        "path": path,
    }


def fmt(value):
    return "x" if value is None else f"0x{value:x}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--max-cycle", type=int)
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    missing = [label for _, label in WATCH if label not in found]
    if missing:
        print("missing: " + ", ".join(missing))

    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    active = None
    rows = []

    def finish_time():
        nonlocal active
        cycle = current_time // args.period
        if cycle < args.min_cycle:
            last.update(values)
            return

        dispatch_ctxtsw = rose(values, last, "dispatch_ctxtsw") and is_one(values, "dispatch_v")
        if dispatch_ctxtsw:
            row = finish_active(active)
            if row is not None:
                rows.append(row)
            active = {
                "dispatch": cycle,
                "pc": values.get("dispatch_pc"),
                "tid": values.get("dispatch_tid"),
                "dispatch_ic_state": values.get("ic_state"),
                "dispatch_ic_hit": values.get("ic_hit"),
                "sideband": None,
                "target": None,
                "pc_if1": None,
                "pc_if2": None,
                "if2_hit": None,
                "if2_ic_state": None,
                "feq": None,
                "first_dispatch": None,
                "next_ctxtsw": None,
                "commit": None,
                "aborted": False,
                "abort_done": None,
                "first_req_after_sideband": None,
                "critical_after_sideband": None,
                "last_after_sideband": None,
            }

        if active is not None:
            if active["sideband"] is None and rose(values, last, "sideband_yumi"):
                active["sideband"] = cycle
                active["target"] = values.get("redirect_npc")
            if active["sideband"] is not None and active["feq"] is None and is_one(values, "ic_abort_comb"):
                active["aborted"] = True
            if active["abort_done"] is None and active["sideband"] is not None and active["feq"] is None and rose(values, last, "ic_abort_done"):
                active["abort_done"] = cycle
            if active["first_req_after_sideband"] is None and active["sideband"] is not None and active["feq"] is None and rose(values, last, "ic_req_yumi"):
                active["first_req_after_sideband"] = cycle
            if active["critical_after_sideband"] is None and active["sideband"] is not None and active["feq"] is None and rose(values, last, "ic_req_critical"):
                active["critical_after_sideband"] = cycle
            if active["last_after_sideband"] is None and active["sideband"] is not None and active["feq"] is None and rose(values, last, "ic_req_last"):
                active["last_after_sideband"] = cycle
            if active["commit"] is None and rose(values, last, "commit_ctxtsw"):
                active["commit"] = cycle
            target = active["target"]
            if active["pc_if1"] is None and target is not None and values.get("pc_if1") == target:
                active["pc_if1"] = cycle
            if active["pc_if2"] is None and target is not None and values.get("pc_if2") == target:
                active["pc_if2"] = cycle
                active["if2_hit"] = values.get("ic_hit")
                active["if2_ic_state"] = values.get("ic_state")
            if active["feq"] is None and active["sideband"] is not None and rose(values, last, "feq_v") and is_one(values, "iq_ack"):
                active["feq"] = cycle
            elif (
                active["first_dispatch"] is None
                and active["sideband"] is not None
                and cycle > active["dispatch"]
                and rose(values, last, "first_dispatch_v")
            ):
                active["first_dispatch"] = cycle
            elif active["sideband"] is not None and cycle > active["dispatch"] and dispatch_ctxtsw:
                active["next_ctxtsw"] = cycle

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
            else:
                apply_line(line, selected, values)
        finish_time()
    row = finish_active(active)
    if row is not None:
        rows.append(row)

    path_counts = collections.Counter(row["path"] for row in rows)
    feq_counts = collections.Counter(row["d_feq"] for row in rows)
    first_counts = collections.Counter(row["d_first"] for row in rows)
    next_counts = collections.Counter(row["d_next"] for row in rows)

    print(f"events {len(rows)}")
    print("paths " + " ".join(f"{name}={count}" for name, count in sorted(path_counts.items())))
    print("d_feq " + " ".join(f"{k}:{v}" for k, v in sorted(feq_counts.items(), key=lambda kv: (kv[0] is None, kv[0] or -1))[:16]))
    print("d_first " + " ".join(f"{k}:{v}" for k, v in sorted(first_counts.items(), key=lambda kv: (kv[0] is None, kv[0] or -1))[:16]))
    print("d_next " + " ".join(f"{k}:{v}" for k, v in sorted(next_counts.items(), key=lambda kv: (kv[0] is None, kv[0] or -1))[:16]))
    print("idx cyc pc tid path d_feq d_first d_next sb if1 if2 if2_hit ic_state0 if2_state abort abort_done req crit last")
    for idx, row in enumerate(rows[: args.limit]):
        print(
            f"{idx:3d} {row['dispatch']:8d} {fmt(row['pc']):>10s} {fmt(row['tid']):>4s} "
            f"{row['path']:>20s} {str(row['d_feq']):>5s} {str(row['d_first']):>7s} {str(row['d_next']):>6s} "
            f"{str(row['sideband']):>8s} {str(row['pc_if1']):>8s} {str(row['pc_if2']):>8s} "
            f"{str(row['if2_hit']):>7s} {fmt(row['dispatch_ic_state']):>9s} {fmt(row['if2_ic_state']):>9s} "
            f"{str(int(row['aborted'])):>5s} {str(row['abort_done']):>10s} "
            f"{str(row['first_req_after_sideband']):>8s} {str(row['critical_after_sideband']):>8s} {str(row['last_after_sideband']):>8s}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
