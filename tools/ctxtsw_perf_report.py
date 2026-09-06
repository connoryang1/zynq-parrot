#!/usr/bin/env python3
"""One-pass context-switch waveform performance report.

This combines the common pieces of ctxtsw_delta_scan.py and
ctxtsw_icache_rate.py so routine benchmark analysis does not require several
multi-GB VCD passes or large row dumps.
"""

from __future__ import annotations

import argparse
import collections
import re
import subprocess


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.v", "dispatch_v"),
    ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v", "dispatch_ctxtsw"),
    ("be.scheduler.dispatch_pkt_cast_o.pc", "dispatch_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id", "dispatch_tid"),
    ("be.calculator.fast_ctxtsw_v_o", "fast_ctxtsw"),
    ("fe_ctxtsw_yumi_i", "sideband_yumi"),
    ("redirect_v_o", "redirect_v"),
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


def parse_int(value: str | None):
    if value is None:
        return None
    return int(value, 0)


def fmt(value):
    return "None" if value is None else f"0x{value:x}"


def pct(part: int, whole: int) -> str:
    return "n/a" if whole == 0 else f"{100.0 * part / whole:.1f}%"


def delta(start, end):
    return None if start is None or end is None else end - start


def hist(counter: collections.Counter) -> str:
    if not counter:
        return "(empty)"
    return " ".join(
        f"{key}:{count}"
        for key, count in sorted(counter.items(), key=lambda kv: (kv[0] is None, kv[0] or -1))
    )


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


def new_counts():
    return collections.Counter(
        {
            "samples": 0,
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


def add_counts(counts, values, last):
    counts["samples"] += 1
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


def finish_row(active, next_cycle):
    if active is None:
        return None
    row = dict(active)
    row["next_ctxtsw"] = next_cycle
    start = row["dispatch"]
    for key in ["fast", "sideband", "redirect", "pc_if1", "pc_if2", "feq", "first_dispatch", "commit", "next_ctxtsw"]:
        row["d_" + key] = delta(start, row.get(key))
    row["d_next"] = row["d_next_ctxtsw"]
    row["first_instr_dispatch"] = row["first_dispatch"] or row["next_ctxtsw"]
    row["d_first_instr_dispatch"] = delta(start, row["first_instr_dispatch"])
    return row


def classify(row, feq_tail_threshold: int):
    d_feq = row.get("d_feq")
    d_commit = row.get("d_commit")
    counts = row["counts"]
    if d_commit is not None and d_commit != 3:
        return "backend_commit_variant"
    if (d_feq is not None and d_feq >= feq_tail_threshold) or counts["abort"] or counts["abort_done"]:
        return "frontend_tail"
    if d_feq == 3:
        return "hot_feq_3"
    if d_feq == 4:
        return "hot_feq_4"
    return "other"


def load_disasm(path: str | None):
    if path is None:
        return {}
    output = subprocess.check_output(
        ["riscv64-unknown-elf-objdump", "-d", "-M", "no-aliases", path],
        text=True,
        errors="replace",
    )
    asm = {}
    for line in output.splitlines():
        if ":" not in line or "\t" not in line:
            continue
        left, rest = line.split(":", 1)
        left = left.strip()
        if not left:
            continue
        try:
            pc = int(left, 16)
        except ValueError:
            continue
        fields = rest.split("\t")
        if len(fields) >= 3:
            asm[pc] = " ".join(part.strip() for part in fields[2:] if part.strip())
    return asm


def find_start_pc_after_rdcycle(asm):
    pcs = sorted(asm)
    for idx, pc in enumerate(pcs):
        text = asm[pc]
        if "csrrs" not in text or "cycle" not in text:
            continue
        for next_pc in pcs[idx + 1 :]:
            next_text = asm[next_pc]
            if "csrrw" in next_text and "0x81" in next_text:
                return next_pc
            if "csrrs" in next_text and "cycle" in next_text:
                break
    return None


def parse_total_cycles_from_log(path: str | None):
    if path is None:
        return None
    total_re = re.compile(r"Total cycles:\s+0x([0-9a-fA-F]+)")
    with open(path, "r", errors="replace") as f:
        for line in f:
            match = total_re.search(line)
            if match:
                return int(match.group(1), 16)
    return None


def pc_label(pc, asm):
    text = asm.get(pc)
    return f"{fmt(pc)} {text}" if text else fmt(pc)


def row_summary(row, asm):
    counts = row["counts"]
    return (
        f"cyc={row['dispatch']} pc={pc_label(row['pc'], asm)} tid={fmt(row['tid'])} "
        f"d_feq={row.get('d_feq')} d_first_instr={row.get('d_first_instr_dispatch')} "
        f"d_commit={row.get('d_commit')} d_next_ctxtsw={row.get('d_next')} "
        f"fetch={counts['fetch']} hit={counts['hit']} miss={counts['miss']} "
        f"abort={counts['abort']} req={counts['req']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--elf", help="optional ELF for PC disassembly")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--start-cycle", type=int)
    parser.add_argument("--start-pc", type=parse_int)
    parser.add_argument("--total-cycles", type=parse_int)
    parser.add_argument("--run-log", help="parse Total cycles from simulator run.log")
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--tail-threshold", type=int, default=16)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--examples", type=int, default=3)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    asm = load_disasm(args.elf)
    if args.total_cycles is None:
        args.total_cycles = parse_total_cycles_from_log(args.run_log)
    if args.start_pc is None and args.start_cycle is None and asm:
        args.start_pc = find_start_pc_after_rdcycle(asm)
    selected, found = select(parse_header(args.vcd))
    missing = [label for _, label in WATCH if label not in found]
    if args.list:
        for label, full in sorted(found.items()):
            print(f"{label:18s} {full}")
        if missing:
            print("missing: " + ", ".join(missing))
        return 0

    values: dict[str, int | None] = {}
    last: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    window_start = args.start_cycle
    window_end = args.max_cycle
    if window_start is not None and args.total_cycles is not None and window_end is None:
        window_end = window_start + args.total_cycles
    active = None
    rows = []
    total = new_counts()

    def in_window(cycle):
        if window_start is None:
            return False
        if cycle < window_start:
            return False
        if window_end is not None and cycle > window_end:
            return False
        return True

    def start_active(cycle):
        return {
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
            "commit": None,
            "counts": new_counts(),
        }

    def finish_time():
        nonlocal active, window_start, window_end
        cycle = current_time // args.period

        # A fully unrolled benchmark can dispatch ctxtsw instructions on
        # consecutive cycles, keeping ctxtsw_v high. Count a new dispatch when
        # the valid ctxtsw level rises or when the dispatched instruction
        # identity changes; this avoids double-counting held dispatch signals.
        dispatch_ctxtsw_level = is_one(values, "dispatch_ctxtsw") and is_one(values, "dispatch_v")
        dispatch_ctxtsw = dispatch_ctxtsw_level and (
            not (is_one(last, "dispatch_ctxtsw") and is_one(last, "dispatch_v"))
            or values.get("dispatch_pc") != last.get("dispatch_pc")
            or values.get("dispatch_tid") != last.get("dispatch_tid")
        )
        if window_start is None and cycle >= args.min_cycle and dispatch_ctxtsw:
            if args.start_pc is None or values.get("dispatch_pc") == args.start_pc:
                window_start = cycle
                if args.total_cycles is not None and window_end is None:
                    window_end = window_start + args.total_cycles

        if not in_window(cycle):
            last.update(values)
            return

        if dispatch_ctxtsw:
            row = finish_row(active, cycle)
            if row is not None:
                rows.append(row)
            active = start_active(cycle)

        add_counts(total, values, last)
        if active is not None:
            add_counts(active["counts"], values, last)
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
            if active["pc_if1"] is None and target is not None and values.get("pc_if1") == target:
                active["pc_if1"] = cycle
            if active["pc_if2"] is None and target is not None and values.get("pc_if2") == target:
                active["pc_if2"] = cycle
            if active["feq"] is None and active["sideband"] is not None and rose(values, last, "feq_v") and is_one(values, "iq_ack"):
                active["feq"] = cycle
            if (
                active["first_dispatch"] is None
                and active["sideband"] is not None
                and cycle > active["dispatch"]
                and is_one(values, "dispatch_v")
            ):
                active["first_dispatch"] = cycle
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
                if window_end is not None and window_start is not None and cycle > window_end:
                    break
            else:
                apply_line(line, selected, values)
        finish_time()

    for row in rows:
        row["cause"] = classify(row, args.tail_threshold)

    d_next_ctxtsw = collections.Counter(row["d_next"] for row in rows)
    d_feq = collections.Counter(row["d_feq"] for row in rows)
    d_first_instr = collections.Counter(row["d_first_instr_dispatch"] for row in rows)
    d_commit = collections.Counter(row["d_commit"] for row in rows)
    causes = collections.Counter(row["cause"] for row in rows)
    pc_counts = collections.defaultdict(collections.Counter)
    throughput_bucket_pc_counts = collections.defaultdict(collections.Counter)
    for row in rows:
        pc_counts[row["cause"]][row["pc"]] += 1
        throughput_bucket_pc_counts[row["d_next"]][row["pc"]] += 1

    print(f"vcd {args.vcd}")
    if missing:
        print("missing " + " ".join(missing))
    print(f"window start={window_start} end={window_end} samples={total['samples']}")
    if args.total_cycles is not None:
        switches = len(rows) + 1 if rows else 0
        print(f"throughput total_cycles={args.total_cycles} switches~={switches} cycles/switch={args.total_cycles / switches:.3f}" if switches else f"throughput total_cycles={args.total_cycles}")
    if rows:
        feq_rows = [row for row in rows if row["d_feq"] is not None]
        first_rows = [row for row in rows if row["d_first_instr_dispatch"] is not None]
        next_rows = [row for row in rows if row["d_next"] is not None]
        print(f"intervals={len(rows)}")
        if feq_rows:
            print(f"hardware avg_d_feq={sum(row['d_feq'] for row in feq_rows) / len(feq_rows):.3f}")
        if first_rows:
            print(f"hardware avg_d_first_instr_dispatch={sum(row['d_first_instr_dispatch'] for row in first_rows) / len(first_rows):.3f}")
        if next_rows:
            print(f"throughput avg_d_next_ctxtsw={sum(row['d_next'] for row in next_rows) / len(next_rows):.3f}")
    print(f"icache fetch={total['fetch']} hit={total['hit']} miss={total['miss']} fetch_hit_rate={pct(total['fetch_hit'], total['fetch'])} fetch_miss_rate={pct(total['fetch_miss'], total['fetch'])}")
    print(f"icache abort_samples={total['abort']} abort_done={total['abort_done']} req={total['req']} critical={total['critical']} last={total['last']}")
    print("hardware hist d_feq " + hist(d_feq))
    print("hardware hist d_first_instr_dispatch " + hist(d_first_instr))
    print("hardware hist d_commit " + hist(d_commit))
    print("hardware causes " + " ".join(f"{name}:{count}" for name, count in sorted(causes.items())))
    print("throughput hist d_next_ctxtsw " + hist(d_next_ctxtsw))

    print("top PCs by cause")
    for cause, count in sorted(causes.items()):
        top = pc_counts[cause].most_common(args.top)
        print(f"  {cause} ({count})")
        for pc, pc_count in top:
            print(f"    {pc_count:5d} {pc_label(pc, asm)}")

    interesting_buckets = [bucket for bucket in sorted(d_next_ctxtsw) if bucket is not None and bucket != 4]
    if interesting_buckets:
        print("top PCs by non-4 throughput d_next_ctxtsw bucket")
        for bucket in interesting_buckets[: args.top]:
            print(f"  d_next_ctxtsw={bucket} ({d_next_ctxtsw[bucket]})")
            for pc, pc_count in throughput_bucket_pc_counts[bucket].most_common(args.top):
                print(f"    {pc_count:5d} {pc_label(pc, asm)}")

    print("examples")
    printed = collections.Counter()
    for row in rows:
        cause = row["cause"]
        if cause == "hot_feq_3":
            continue
        if printed[cause] >= args.examples:
            continue
        print(f"  {cause}: " + row_summary(row, asm))
        printed[cause] += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
