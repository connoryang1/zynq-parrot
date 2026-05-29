#!/usr/bin/env python3
"""Trace I-cache miss request/response timing around context-switch sidebands."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.v", "dispatch_v"),
    ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v", "dispatch_ctxtsw"),
    ("be.scheduler.dispatch_pkt_cast_o.pc", "dispatch_pc"),
    ("fe_ctxtsw_yumi_i", "sideband"),
    ("fe.icache.force_i", "force"),
    ("fe.icache.cache_req_yumi_i", "ic_req_yumi"),
    ("fe.icache.cache_req_cast_o.addr", "ic_req_addr"),
    ("fe.icache.abort_miss", "ic_abort"),
    ("fe.icache.abort_complete", "ic_abort_done"),
    ("icache_uce.fsm_fwd_v_lo", "uce_fwd_v"),
    ("icache_uce.fsm_fwd_ready_then_li", "uce_fwd_ready"),
    ("icache_uce.fsm_fwd_last_lo", "uce_fwd_last"),
    ("icache_uce.fsm_fwd_header_lo.addr", "uce_fwd_addr"),
    ("icache_uce.fsm_fwd_addr_lo", "uce_fwd_beat_addr"),
    ("icache_uce.fsm_rev_v_li", "uce_rev_v"),
    ("icache_uce.fsm_rev_addr_li", "uce_rev_addr"),
    ("icache_uce.fsm_rev_critical_li", "uce_rev_critical"),
    ("icache_uce.fsm_rev_last_li", "uce_rev_last"),
    ("icache_uce.primary_resp_li", "uce_primary_resp"),
    ("icache_uce.overlap_resp_li", "uce_overlap_resp"),
    ("fe.controller.fe_queue_v_o", "feq_v"),
    ("be.scheduler.issue_queue.ack", "iq_ack"),
]


def parse_header(path: str):
    scopes: list[str] = []
    selected: dict[str, list[tuple[str, int]]] = {}
    found: dict[str, str] = {}
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
                if not match:
                    continue
                width_s, code, raw = match.groups()
                full = ".".join(scopes + [raw.split()[0]])
                for fragment, label in WATCH:
                    if fragment in full and label not in found:
                        selected.setdefault(code, []).append((label, int(width_s)))
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
    if value is None:
        return "None"
    return hex(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--window-before", type=int, default=20)
    parser.add_argument("--window-after", type=int, default=140)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    selected, found = parse_header(args.vcd)
    missing = [label for _, label in WATCH if label not in found]
    if missing:
        print("missing: " + ", ".join(missing))

    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    events: list[dict] = []
    active: dict | None = None
    recent_reqs: list[dict] = []
    recent_fwds: list[dict] = []
    current_time = 0
    in_values = False

    def finish_active():
        nonlocal active
        if active is not None:
            events.append(active)
            active = None

    def finish_time():
        nonlocal active, recent_reqs, recent_fwds
        cycle = current_time // args.period

        if rose(values, last, "ic_req_yumi"):
            recent_reqs.append({"cycle": cycle, "addr": values.get("ic_req_addr")})
            recent_reqs = [r for r in recent_reqs if cycle - r["cycle"] <= args.window_before]

        fwd_fire = is_one(values, "uce_fwd_v") and is_one(values, "uce_fwd_ready") and is_one(values, "uce_fwd_last")
        fwd_event = None
        if fwd_fire and last.get("_last_fwd_cycle") != cycle:
            fwd_event = {
                "cycle": cycle,
                "addr": values.get("uce_fwd_addr"),
                "beat_addr": values.get("uce_fwd_beat_addr"),
            }
            recent_fwds.append(fwd_event)
            recent_fwds = [f for f in recent_fwds if cycle - f["cycle"] <= args.window_before]
            last["_last_fwd_cycle"] = cycle

        if rose(values, last, "dispatch_ctxtsw") and is_one(values, "dispatch_v"):
            finish_active()
            old_req = recent_reqs[-1] if recent_reqs else None
            old_fwd = None
            if old_req is not None:
                for fwd in reversed(recent_fwds):
                    if fwd["addr"] == old_req["addr"]:
                        old_fwd = fwd
                        break
            active = {
                "dispatch": cycle,
                "pc": values.get("dispatch_pc"),
                "sideband": None,
                "old_req": old_req,
                "target_req": None,
                "old_fwd": old_fwd,
                "target_fwd": None,
                "old_first_rev": None,
                "old_last_rev": None,
                "target_first_rev": None,
                "target_last_rev": None,
                "abort": None,
                "abort_done": None,
                "feq": None,
            }

        if active is None:
            last.update(values)
            return

        if cycle > active["dispatch"] + args.window_after:
            finish_active()
            last.update(values)
            return

        if active["sideband"] is None and rose(values, last, "sideband"):
            active["sideband"] = cycle

        if active["sideband"] is not None and active["abort"] is None and is_one(values, "ic_abort"):
            active["abort"] = cycle
        if active["abort_done"] is None and rose(values, last, "ic_abort_done"):
            active["abort_done"] = cycle

        if rose(values, last, "ic_req_yumi"):
            req = {"cycle": cycle, "addr": values.get("ic_req_addr")}
            if active["sideband"] is None:
                active["old_req"] = req
            elif active["target_req"] is None:
                active["target_req"] = req

        if fwd_event is not None:
            fwd = fwd_event
            old_req = active["old_req"]
            target_req = active["target_req"]
            if old_req is not None and fwd["addr"] == old_req["addr"] and active["old_fwd"] is None:
                active["old_fwd"] = fwd
            elif target_req is not None and fwd["addr"] == target_req["addr"] and active["target_fwd"] is None:
                active["target_fwd"] = fwd

        if rose(values, last, "uce_rev_v") or (is_one(values, "uce_rev_v") and values.get("uce_rev_addr") != last.get("uce_rev_addr")):
            addr = values.get("uce_rev_addr")
            old_req = active["old_req"]
            target_req = active["target_req"]
            if old_req is not None and addr is not None and (addr >> 6) == (old_req["addr"] >> 6):
                active["old_first_rev"] = active["old_first_rev"] or cycle
                if is_one(values, "uce_rev_last"):
                    active["old_last_rev"] = cycle
            if target_req is not None and addr is not None and (addr >> 6) == (target_req["addr"] >> 6):
                active["target_first_rev"] = active["target_first_rev"] or cycle
                if is_one(values, "uce_rev_last"):
                    active["target_last_rev"] = cycle

        if active["feq"] is None and active["sideband"] is not None and rose(values, last, "feq_v") and is_one(values, "iq_ack"):
            active["feq"] = cycle

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
            else:
                apply_line(line, selected, values)
        finish_time()
    finish_active()

    printed = 0
    print("idx dispatch pc sideband old_req old_fwd target_req target_fwd old_rev target_rev abort abort_done feq")
    for i, event in enumerate(events):
        if event["sideband"] is None:
            continue
        old_req = event["old_req"] or {}
        target_req = event["target_req"] or {}
        old_fwd = event["old_fwd"] or {}
        target_fwd = event["target_fwd"] or {}
        d = event["dispatch"]
        print(
            f"{i:3d} {d:8d} {fmt(event['pc']):>10} "
            f"{event['sideband'] - d if event['sideband'] is not None else 'None':>4} "
            f"{old_req.get('cycle', None) - d if old_req else 'None':>7} {fmt(old_req.get('addr')):>10} "
            f"{old_fwd.get('cycle', None) - d if old_fwd else 'None':>7} "
            f"{target_req.get('cycle', None) - d if target_req else 'None':>9} {fmt(target_req.get('addr')):>10} "
            f"{target_fwd.get('cycle', None) - d if target_fwd else 'None':>9} "
            f"{event['old_first_rev'] - d if event['old_first_rev'] is not None else 'None':>7}/"
            f"{event['old_last_rev'] - d if event['old_last_rev'] is not None else 'None':<4} "
            f"{event['target_first_rev'] - d if event['target_first_rev'] is not None else 'None':>7}/"
            f"{event['target_last_rev'] - d if event['target_last_rev'] is not None else 'None':<4} "
            f"{event['abort'] - d if event['abort'] is not None else 'None':>5} "
            f"{event['abort_done'] - d if event['abort_done'] is not None else 'None':>10} "
            f"{event['feq'] - d if event['feq'] is not None else 'None':>5}"
        )
        printed += 1
        if printed >= args.limit:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
