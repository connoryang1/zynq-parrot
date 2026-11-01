#!/usr/bin/env python3
"""Analyze complete early/late physical-preview sweeps without set cherry-picking."""

import argparse
import json
import random
import re
import statistics
from pathlib import Path

from analyze_scheduler_physical_preview_benchmark import (
    CONFIG,
    METRICS,
    ROW,
    TIMING_MODES,
    percentile,
    summarize,
)


def block_differences(rows, metric):
    differences = []
    for start in range(0, len(rows), 4):
        block = rows[start:start + 4]
        off_mean = (block[0][metric] + block[3][metric]) / 2
        on_mean = (block[1][metric] + block[2][metric]) / 2
        differences.append(off_mean - on_mean)
    return differences


def parse_segments(text, source, summarize_cells=True, bootstrap_samples=20000):
    matches = list(CONFIG.finditer(text))
    segments = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.start():end]
        if "PHYSICAL_BENCH_CHILD PASS" not in segment or "PHYSICAL_BENCH_PARENT PASS" not in segment:
            raise ValueError(f"{source}: missing PASS marker after configuration {index}")
        group, first_offset, lines = map(int, match.groups()[:3])
        timing = match.group(4)
        mode = int(match.group(5))
        if (group > 7 or first_offset != group * 256 or lines != 4
                or mode != TIMING_MODES[timing]):
            raise ValueError(f"{source}: invalid configuration marker {match.group(0)}")
        rows = []
        for row_match in ROW.finditer(segment):
            values = [int(value) for value in row_match.groups()]
            rows.append(dict(zip(("trial", "mode", "hooks") + METRICS, values)))
        result = (summarize(rows, group, timing, bootstrap_samples)
                  if summarize_cells else None)
        segments.append(((timing, group), rows, result))
    return segments


def bootstrap_median(blocks_by_group, rng, samples=20000):
    point = statistics.median(value for blocks in blocks_by_group.values()
                              for value in blocks)
    boot = []
    for _ in range(samples):
        values = []
        for blocks in blocks_by_group.values():
            values.extend(rng.choices(blocks, k=len(blocks)))
        boot.append(statistics.median(values))
    return point, [percentile(boot, 0.025), percentile(boot, 0.975)]


def analyze(paths, allow_partial=False, bootstrap_samples=20000):
    cells = {}
    board_text = ""
    for path in paths:
        text = path.read_text(errors="replace")
        board_text += text
        for key, rows, result in parse_segments(
                text, path, bootstrap_samples=bootstrap_samples):
            if key in cells:
                raise ValueError(f"duplicate timing/group cell: {key}")
            cells[key] = {"rows": rows, "summary": result}
    observed_timings = {timing for timing, _group in cells}
    if (len(observed_timings) == 1
            and observed_timings <= {
                "instruction", "counter", "trigger", "wake-trigger",
                "wake-data", "wake-early-data",
            }):
        timing = next(iter(observed_timings))
        expected = {(timing, group) for group in range(8)}
    else:
        expected = {(timing, group) for timing in ("early", "late")
                    for group in range(8)}
    if not allow_partial and set(cells) != expected:
        missing = sorted(expected - set(cells))
        extra = sorted(set(cells) - expected)
        raise ValueError(f"incomplete sweep; missing={missing}, extra={extra}")
    core_pass = re.search(r"\bCORE(?:\[0\])? PASS\b", board_text)
    host_pass = re.search(r"\bBSG PASS\b", board_text)
    if not core_pass or not host_pass:
        raise ValueError("missing final board CORE/BSG PASS markers")

    rng = random.Random(0xB50_5E7)
    output = {"cells": {}, "pooled": {}, "late_minus_early": {}}
    for key in sorted(cells):
        timing, group = key
        output["cells"][f"{timing}_{group}"] = cells[key]["summary"]
    for timing in TIMING_MODES:
        timing_cells = {group: cells[(timing, group)] for group in range(8)
                        if (timing, group) in cells}
        if not timing_cells:
            continue
        output["pooled"][timing] = {}
        for metric in METRICS:
            blocks = {group: block_differences(cell["rows"], metric)
                      for group, cell in timing_cells.items()}
            point, interval = bootstrap_median(
                blocks, rng, samples=bootstrap_samples
            )
            output["pooled"][timing][metric] = {
                "stratified_median_saved_cycles": point,
                "stratified_95pct_ci_saved_cycles": interval,
            }
        best = max(timing_cells, key=lambda group: timing_cells[group]["summary"]
                   ["metrics"]["load_cycles"]["paired_median_saved_cycles"])
        output["pooled"][timing]["exploratory_best_load_group"] = best

    for group in range(8):
        if ("early", group) not in cells or ("late", group) not in cells:
            continue
        early = block_differences(cells[("early", group)]["rows"], "load_cycles")
        late = block_differences(cells[("late", group)]["rows"], "load_cycles")
        point = statistics.median(late) - statistics.median(early)
        boots = [statistics.median(rng.choices(late, k=len(late)))
                 - statistics.median(rng.choices(early, k=len(early)))
                 for _ in range(bootstrap_samples)]
        output["late_minus_early"][str(group)] = {
            "saved_cycle_effect_difference": point,
            "95pct_ci": [percentile(boots, 0.025), percentile(boots, 0.975)],
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", nargs="+", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    try:
        result = analyze(args.transcript, args.allow_partial)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
