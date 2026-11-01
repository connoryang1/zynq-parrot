#!/usr/bin/env python3
"""Partition physical-preview roundtrip tails into child work and return handoff."""

import argparse
import json
import random
import re
import statistics
from pathlib import Path

from analyze_scheduler_physical_preview_benchmark import CONFIG, percentile
from analyze_scheduler_physical_preview_sweep import (
    block_differences,
    bootstrap_median,
    parse_segments,
)
from compare_scheduler_physical_preview_sweeps import read_transcript


TAIL = re.compile(
    r"PHYSICAL_BENCH_TAIL trial=(\d+) child_post_load=(\d+) "
    r"return_handoff=(\d+)"
)
TAIL_FIELDS = ("child_post_load", "return_handoff")
TAIL_METRICS = TAIL_FIELDS + ("post_load_total",)


def summarize_tail(rows, base_rows, group, timing):
    """Validate one cell and return paired-block tail estimates."""
    if len(rows) != 512 or [row["trial"] for row in rows] != list(range(512)):
        raise ValueError("expected exactly 512 ordered tail rows")
    combined = []
    for row, base in zip(rows, base_rows):
        if (row["child_post_load"] + row["return_handoff"]
                != base["roundtrip"] - base["wake_to_load"]):
            raise ValueError(f"tail partition mismatch at trial {row['trial']}")
        combined.append({
            **row,
            "post_load_total": row["child_post_load"] + row["return_handoff"],
            "mode": base["mode"],
        })
    result = {
        "l2_set_group": group,
        "preview_timing": timing,
        "trials": len(rows),
        "paired_blocks": len(rows) // 4,
        "metrics": {},
    }
    rng = random.Random(0x7A11)
    for metric in TAIL_METRICS:
        off = [row[metric] for row in combined if row["mode"] == 0]
        on = [row[metric] for row in combined if row["mode"] == 1]
        blocks = block_differences(combined, metric)
        boots = [
            statistics.median(rng.choices(blocks, k=len(blocks)))
            for _ in range(20000)
        ]
        result["metrics"][metric] = {
            "off_median_cycles": statistics.median(off),
            "on_median_cycles": statistics.median(on),
            "paired_median_saved_cycles": statistics.median(blocks),
            "paired_95pct_ci_saved_cycles": [
                percentile(boots, 0.025), percentile(boots, 0.975)
            ],
        }
    return combined, result


def load_cells(paths, timing, label="tail sweep"):
    """Load one complete timing replication and retain paired tail rows."""
    cells = {}
    board_text = ""
    for path in paths:
        text = read_transcript(path)
        board_text += text
        configs = list(CONFIG.finditer(text))
        parsed = parse_segments(text, path, summarize_cells=False)
        if len(configs) != len(parsed):
            raise ValueError(f"{path}: configuration parse mismatch")
        for index, ((key, base_rows, _base_result), match) in enumerate(
                zip(parsed, configs)):
            end = configs[index + 1].start() if index + 1 < len(configs) else len(text)
            if key[0] != timing:
                continue
            if key in cells:
                raise ValueError(f"{label}: duplicate timing/group cell: {key}")
            segment = text[match.start():end]
            tail_rows = [
                dict(zip(("trial",) + TAIL_FIELDS, map(int, item.groups())))
                for item in TAIL.finditer(segment)
            ]
            combined, result = summarize_tail(
                tail_rows, base_rows, key[1], key[0]
            )
            cells[key] = {"rows": combined, "summary": result}
    expected = {(timing, group) for group in range(8)}
    if set(cells) != expected:
        missing = sorted(expected - set(cells))
        extra = sorted(set(cells) - expected)
        raise ValueError(
            f"{label}: incomplete tail sweep; missing={missing}, extra={extra}"
        )
    if not re.search(r"\bCORE(?:\[0\])? PASS\b", board_text):
        raise ValueError(f"{label}: missing final board CORE PASS marker")
    if not re.search(r"\bBSG PASS\b", board_text):
        raise ValueError(f"{label}: missing final board BSG PASS marker")
    return cells


def analyze(paths, timing):
    """Require all eight groups for one timing and pool their tail effects."""
    cells = load_cells(paths, timing)

    rng = random.Random(0x7A11_5E7)
    output = {"timing": timing, "cells": {}, "pooled": {}}
    for key in sorted(cells):
        output["cells"][f"{timing}_{key[1]}"] = cells[key]["summary"]
    for metric in TAIL_METRICS:
        blocks = {
            group: block_differences(cells[(timing, group)]["rows"], metric)
            for group in range(8)
        }
        point, interval = bootstrap_median(blocks, rng)
        output["pooled"][metric] = {
            "stratified_median_saved_cycles": point,
            "stratified_95pct_ci_saved_cycles": interval,
        }
    return output


def pool_tail(replicate_paths, timing, samples=20000):
    """Pool tail effects across independent boots and cache-set groups."""
    replicates = [
        load_cells(paths, timing, f"replicate {index}")
        for index, paths in enumerate(replicate_paths)
    ]
    rng = random.Random(0x7A11_2)
    output = {
        "timing": timing,
        "replicate_count": len(replicates),
        "bootstrap_samples": samples,
        "metrics": {},
    }
    for metric in TAIL_METRICS:
        per_replicate = []
        pooled_blocks = {}
        for replicate_index, cells in enumerate(replicates):
            blocks_by_group = {
                group: block_differences(
                    cells[(timing, group)]["rows"], metric
                )
                for group in range(8)
            }
            point, interval = bootstrap_median(
                blocks_by_group,
                random.Random(0x7A11_2 + replicate_index),
                samples,
            )
            per_replicate.append({
                "saved_cycles": point,
                "95pct_ci_saved_cycles": interval,
            })
            for group, blocks in blocks_by_group.items():
                pooled_blocks[(replicate_index, group)] = blocks
        point, interval = bootstrap_median(pooled_blocks, rng, samples)
        output["metrics"][metric] = {
            "replicates": per_replicate,
            "pooled_saved_cycles": point,
            "pooled_95pct_ci_saved_cycles": interval,
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timing", choices=("early", "late", "instruction", "counter"),
                        required=True)
    parser.add_argument(
        "--replicate", nargs="+", action="append", type=Path,
        help="one complete replication, potentially split across log files",
    )
    parser.add_argument("--samples", type=int, default=20000)
    parser.add_argument("transcript", nargs="*", type=Path)
    args = parser.parse_args()
    if args.samples <= 0:
        parser.error("bootstrap samples must be positive")
    if args.replicate and args.transcript:
        parser.error("use either positional transcripts or --replicate, not both")
    if args.replicate and len(args.replicate) < 2:
        parser.error("at least two replications are required")
    if not args.replicate and not args.transcript:
        parser.error("at least one transcript is required")
    try:
        if args.replicate:
            result = pool_tail(args.replicate, args.timing, args.samples)
        else:
            result = analyze(args.transcript, args.timing)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
