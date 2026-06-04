#!/usr/bin/env python3
"""Scan D-cache UCE credit accounting in a BP VCD."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("blackparrot.dcache_uce.reset_i$", "reset"),
    ("blackparrot.dcache_uce.state_r$", "state"),
    ("blackparrot.dcache_uce.cache_req_v_i$", "req_v"),
    ("blackparrot.dcache_uce.cache_req_yumi_o$", "req_yumi"),
    ("blackparrot.dcache_uce.cache_req_v_r$", "req_r_v"),
    ("blackparrot.dcache_uce.cache_req_done$", "req_done"),
    ("blackparrot.dcache_uce.cache_req_r.msg_type$", "req_type"),
    ("blackparrot.dcache_uce.cache_req_r.addr$", "req_addr"),
    ("blackparrot.dcache_uce.fsm_fwd_v_lo$", "fwd_v"),
    ("blackparrot.dcache_uce.fsm_fwd_ready_then_li$", "fwd_ready"),
    ("blackparrot.dcache_uce.fsm_fwd_new_lo$", "fwd_new"),
    ("blackparrot.dcache_uce.fsm_fwd_last_lo$", "fwd_last"),
    ("blackparrot.dcache_uce.fsm_rev_v_li$", "rev_v"),
    ("blackparrot.dcache_uce.fsm_rev_yumi_lo$", "rev_yumi"),
    ("blackparrot.dcache_uce.fsm_rev_last_li$", "rev_last"),
    ("blackparrot.dcache_uce.credit_count_lo$", "credit"),
    ("blackparrot.dcache_uce.cache_req_credits_empty_o$", "credit_empty"),
    ("blackparrot.dcache_uce.cache_req_credits_full_o$", "credit_full"),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--min-cycle", type=int)
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    missing = [label for _, label in WATCH if label not in found]
    if missing:
        print("missing", " ".join(missing))
    for label, full in sorted(found.items()):
        print(f"{label}: {full}")

    values = {label: None for _, label in WATCH}
    cycle = 0
    sampled = 0
    enq_count = 0
    deq_count = 0
    last_sampled_cycle = None
    rtl_underflows = []

    def in_window(cyc):
        if args.min_cycle is not None and cyc < args.min_cycle:
            return False
        if args.max_cycle is not None and cyc > args.max_cycle:
            return False
        return True

    def sample(cyc):
        nonlocal sampled, enq_count, deq_count, last_sampled_cycle
        if not in_window(cyc):
            return
        if last_sampled_cycle == cyc:
            return
        if values.get("credit") is None:
            return
        last_sampled_cycle = cyc
        sampled += 1
        enq = values.get("fwd_v") == 1 and values.get("fwd_new") == 1
        deq = values.get("rev_yumi") == 1 and values.get("rev_last") == 1
        if enq:
            enq_count += 1
        if deq:
            deq_count += 1

        rtl_credit = values.get("credit")
        if deq and rtl_credit == 0 and not enq and len(rtl_underflows) < args.limit:
            rtl_underflows.append((cyc, dict(values)))

    with open(args.vcd, "r", errors="replace", buffering=8 * 1024 * 1024) as f:
        for line in f:
            if not line:
                continue
            if line[0] == "#":
                sample(cycle)
                try:
                    cycle = int(line[1:]) // args.period
                except ValueError:
                    continue
                if args.max_cycle is not None and cycle > args.max_cycle:
                    break
                continue
            if args.min_cycle is not None and cycle < args.min_cycle:
                continue
            if args.max_cycle is not None and cycle > args.max_cycle:
                break
            stripped = line.strip()
            if stripped:
                apply_line(stripped, selected, values)
        sample(cycle)

    print(f"samples={sampled} first_forward_beats={enq_count} reverse_final_beats={deq_count}")
    print(f"rtl_underflows={len(rtl_underflows)}")
    for cyc, vals in rtl_underflows:
        print(
            "rtl_underflow "
            f"cycle={cyc} rtl_credit={vals.get('credit')} state={vals.get('state')} "
            f"req_v={vals.get('req_v')} req_yumi={vals.get('req_yumi')} "
            f"req_r_v={vals.get('req_r_v')} req_done={vals.get('req_done')} "
            f"req_type={vals.get('req_type')} req_addr=0x{vals.get('req_addr') or 0:x} "
            f"fwd={vals.get('fwd_v')}/{vals.get('fwd_ready')}/{vals.get('fwd_new')}/{vals.get('fwd_last')} "
            f"rev={vals.get('rev_v')}/{vals.get('rev_yumi')}/{vals.get('rev_last')} "
            f"empty={vals.get('credit_empty')} full={vals.get('credit_full')}"
        )
    return 1 if rtl_underflows else 0


if __name__ == "__main__":
    raise SystemExit(main())
