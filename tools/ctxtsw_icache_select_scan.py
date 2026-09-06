#!/usr/bin/env python3
"""Check I-cache hit/data-select one-hot behavior in a BP VCD."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("fe.icache.hit_v_o", "hit"),
    ("fe.icache.hit_v_tv_r", "raw_hit"),
    ("fe.icache.hit_way_one_hot_tv", "hit_way"),
    ("fe.icache.ld_data_way_select_tv", "data_select"),
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
            if fragment in full and label not in found:
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


def popcount(value):
    if value is None:
        return None
    return bin(int(value)).count("1")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--min-cycle", type=int)
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--fail-on-bad-select", action="store_true")
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    missing = [label for _, label in WATCH if label not in found]
    if missing:
        print("missing", " ".join(missing))
    for label, full in sorted(found.items()):
        print(f"{label}: {full}")

    values = {label: None for _, label in WATCH}
    cycle = 0
    samples = 0
    hit_samples = 0
    raw_multihit = 0
    bad_data_select = 0
    examples = []

    def in_window(cyc):
        if args.min_cycle is not None and cyc < args.min_cycle:
            return False
        if args.max_cycle is not None and cyc > args.max_cycle:
            return False
        return True

    def sample(cyc):
        nonlocal samples, hit_samples, raw_multihit, bad_data_select
        if not in_window(cyc):
            return
        data_select = values.get("data_select")
        raw_hit = values.get("raw_hit")
        hit = values.get("hit")
        if data_select is None and raw_hit is None:
            return

        samples += 1
        raw_count = popcount(raw_hit)
        select_count = popcount(data_select)
        if raw_count is not None and raw_count > 1:
            raw_multihit += 1
        if hit == 1:
            hit_samples += 1
            if select_count != 1:
                bad_data_select += 1
                if len(examples) < args.limit:
                    examples.append((cyc, raw_hit, values.get("hit_way"), data_select))

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

    print(f"samples={samples} hit_samples={hit_samples}")
    print(f"raw_multihit_samples={raw_multihit}")
    print(f"bad_data_select_on_hit={bad_data_select}")
    for cyc, raw_hit, hit_way, data_select in examples:
        raw_fmt = "None" if raw_hit is None else f"0x{raw_hit:x}"
        hit_way_fmt = "None" if hit_way is None else f"0x{hit_way:x}"
        data_fmt = "None" if data_select is None else f"0x{data_select:x}"
        print(
            f"bad cyc={cyc} raw_hit={raw_fmt} "
            f"hit_way={hit_way_fmt} data_select={data_fmt}"
        )
    return 1 if args.fail_on_bad_select and bad_data_select else 0


if __name__ == "__main__":
    raise SystemExit(main())
