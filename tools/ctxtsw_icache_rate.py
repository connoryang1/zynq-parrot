#!/usr/bin/env python3
"""Report I-cache signal rates and context-switch latency histograms from a VCD."""

from __future__ import annotations

import argparse
import collections
import re


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.v", "dispatch_v"),
    ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v", "dispatch_ctxtsw"),
    ("be.scheduler.dispatch_pkt_cast_o.pc", "dispatch_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id", "dispatch_tid"),
    ("fe_ctxtsw_yumi_i", "sideband_yumi"),
    ("redirect_npc_o", "redirect_npc"),
    ("fe.pc_gen.pc_if1_r", "pc_if1"),
    ("pc_if2_r", "pc_if2"),
    ("fetch_v_i", "fetch_v"),
    ("fe.icache.hit_v_o", "ic_hit"),
    ("fe.icache.miss_v_o", "ic_miss"),
    ("fe.icache.abort_miss", "ic_abort_comb"),
    ("fe.icache.abort_miss_r", "ic_abort"),
    ("fe.icache.abort_complete", "ic_abort_done"),
    ("fe.icache.cache_req_yumi_i", "ic_req_yumi"),
    ("fe.icache.cache_req_critical_i", "ic_req_critical"),
    ("fe.icache.cache_req_last_i", "ic_req_last"),
    ("fe.controller.fe_queue_v_o", "feq_v"),
    ("be.scheduler.issue_queue.ack", "iq_ack"),
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


def delta(start, end):
    return None if start is None or end is None else end - start


def pct(part: int, whole: int) -> str:
    return "n/a" if whole == 0 else f"{(100.0 * part / whole):.1f}%"


def fmt_hist(counter: collections.Counter) -> str:
    if not counter:
        return "(empty)"
    return " ".join(
        f"{key}:{count}"
        for key, count in sorted(counter.items(), key=lambda kv: (kv[0] is None, kv[0] or -1))
    )


def fmt(value):
    return "x" if value is None else f"0x{value:x}"


def new_counts():
    return collections.Counter(
        {
            "cycles": 0,
            "fetch": 0,
            "hit": 0,
            "miss": 0,
            "fetch_hit": 0,
            "fetch_miss": 0,
            "abort": 0,
            "abort_done": 0,
            "req": 0,
            "critical": 0,
            "last": 0,
        }
    )


def add_cycle_counts(counts, values, last):
    counts["cycles"] += 1
    if is_one(values, "fetch_v"):
        counts["fetch"] += 1
        if is_one(values, "ic_hit"):
            counts["fetch_hit"] += 1
        if is_one(values, "ic_miss"):
            counts["fetch_miss"] += 1
    if is_one(values, "ic_hit"):
        counts["hit"] += 1
    if is_one(values, "ic_miss"):
        counts["miss"] += 1
    if is_one(values, "ic_abort_comb") or is_one(values, "ic_abort"):
        counts["abort"] += 1
    if rose(values, last, "ic_abort_done"):
        counts["abort_done"] += 1
    if rose(values, last, "ic_req_yumi"):
        counts["req"] += 1
    if rose(values, last, "ic_req_critical"):
        counts["critical"] += 1
    if rose(values, last, "ic_req_last"):
        counts["last"] += 1


def finish_interval(interval, end_cycle):
    if interval is None:
        return None
    row = dict(interval)
    row["next_ctxtsw"] = end_cycle
    row["d_next"] = delta(row["dispatch"], row["next_ctxtsw"])
    row["d_feq"] = delta(row["dispatch"], row["feq"])
    row["d_commit"] = delta(row["dispatch"], row["commit"])
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--limit", type=int, default=20)
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
    current_time = 0
    in_values = False
    total = new_counts()
    active = None
    rows = []

    def finish_time():
        nonlocal active
        cycle = current_time // args.period
        if cycle < args.min_cycle:
            last.update(values)
            return
        if args.max_cycle is not None and cycle > args.max_cycle:
            return

        dispatch_ctxtsw = rose(values, last, "dispatch_ctxtsw") and is_one(values, "dispatch_v")
        if dispatch_ctxtsw:
            row = finish_interval(active, cycle)
            if row is not None:
                rows.append(row)
            active = {
                "dispatch": cycle,
                "pc": values.get("dispatch_pc"),
                "tid": values.get("dispatch_tid"),
                "target": None,
                "sideband": None,
                "feq": None,
                "commit": None,
                "counts": new_counts(),
            }

        add_cycle_counts(total, values, last)
        if active is not None:
            add_cycle_counts(active["counts"], values, last)
            if active["sideband"] is None and rose(values, last, "sideband_yumi"):
                active["sideband"] = cycle
                active["target"] = values.get("redirect_npc")
            if active["feq"] is None and active["sideband"] is not None and rose(values, last, "feq_v") and is_one(values, "iq_ack"):
                active["feq"] = cycle
            if active["commit"] is None and rose(values, last, "commit_ctxtsw"):
                active["commit"] = cycle

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

    d_next = collections.Counter(row["d_next"] for row in rows)
    d_feq = collections.Counter(row["d_feq"] for row in rows)
    d_commit = collections.Counter(row["d_commit"] for row in rows)
    interval_fetch_hits = sum(row["counts"]["fetch_hit"] for row in rows)
    interval_fetches = sum(row["counts"]["fetch"] for row in rows)
    intervals_with_miss = sum(1 for row in rows if row["counts"]["miss"] or row["counts"]["fetch_miss"])
    intervals_with_abort = sum(1 for row in rows if row["counts"]["abort"] or row["counts"]["abort_done"])

    print(f"window cycles {args.min_cycle}..{args.max_cycle if args.max_cycle is not None else 'end'}")
    print(f"vcd samples {total['cycles']}")
    print(
        "icache samples "
        f"fetch={total['fetch']} hit={total['hit']} miss={total['miss']} "
        f"fetch_hit={total['fetch_hit']} fetch_miss={total['fetch_miss']}"
    )
    print(
        "icache rates "
        f"fetch_hit_rate={pct(total['fetch_hit'], total['fetch'])} "
        f"fetch_miss_rate={pct(total['fetch_miss'], total['fetch'])} "
        f"hit_signal_rate={pct(total['hit'], total['cycles'])} "
        f"miss_signal_rate={pct(total['miss'], total['cycles'])}"
    )
    print(
        "icache refill/abort "
        f"abort_cycles={total['abort']} abort_done={total['abort_done']} "
        f"req={total['req']} critical={total['critical']} last={total['last']}"
    )
    print(f"ctxtsw intervals {len(rows)}")
    print(f"interval fetch_hit_rate {pct(interval_fetch_hits, interval_fetches)}")
    print(f"intervals_with_miss {intervals_with_miss}/{len(rows)}")
    print(f"intervals_with_abort {intervals_with_abort}/{len(rows)}")
    print("hist d_next " + fmt_hist(d_next))
    print("hist d_feq " + fmt_hist(d_feq))
    print("hist d_commit " + fmt_hist(d_commit))
    print("idx dispatch pc tid d_next d_feq d_commit fetch hit miss abort req crit last")
    for idx, row in enumerate(rows[: args.limit]):
        counts = row["counts"]
        print(
            f"{idx:3d} {row['dispatch']:8d} {fmt(row['pc']):>10s} {fmt(row['tid']):>4s} "
            f"{str(row['d_next']):>6s} {str(row['d_feq']):>5s} {str(row['d_commit']):>8s} "
            f"{counts['fetch']:5d} {counts['hit']:3d} {counts['miss']:4d} "
            f"{counts['abort']:5d} {counts['req']:3d} {counts['critical']:4d} {counts['last']:4d}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
