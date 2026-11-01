#!/usr/bin/env python3
"""Pool predeclared physical-preview replications while preserving strata."""

import argparse
import json
import random
import re
import statistics
from pathlib import Path

from analyze_scheduler_physical_preview_benchmark import METRICS
from analyze_scheduler_physical_preview_sweep import (
    block_differences,
    bootstrap_median,
    parse_segments,
)
from compare_scheduler_physical_preview_sweeps import read_transcript


def load_replicate(paths, timing, label):
    """Load one complete eight-group timing replication from one or more logs."""
    cells = {}
    board_text = ""
    for path in paths:
        text = read_transcript(path)
        board_text += text
        for key, rows, _result in parse_segments(text, path):
            if key[0] != timing:
                continue
            if key in cells:
                raise ValueError(f"{label}: duplicate timing/group cell: {key}")
            cells[key] = rows
    expected = {(timing, group) for group in range(8)}
    if set(cells) != expected:
        missing = sorted(expected - set(cells))
        extra = sorted(set(cells) - expected)
        raise ValueError(
            f"{label}: incomplete {timing} replication; "
            f"missing={missing}, extra={extra}"
        )
    if not re.search(r"\bCORE(?:\[0\])? PASS\b", board_text):
        raise ValueError(f"{label}: missing final board CORE PASS marker")
    if not re.search(r"\bBSG PASS\b", board_text):
        raise ValueError(f"{label}: missing final board BSG PASS marker")
    return cells


def pool(replicate_paths, timing, samples=20000):
    """Pool paired effects across independent boots and cache-set groups."""
    replicates = [
        load_replicate(paths, timing, f"replicate {index}")
        for index, paths in enumerate(replicate_paths)
    ]
    rng = random.Random(0x5EED_2)
    output = {
        "timing": timing,
        "replicate_count": len(replicates),
        "bootstrap_samples": samples,
        "metrics": {},
    }
    for metric in METRICS:
        per_replicate = []
        pooled_blocks = {}
        for replicate_index, cells in enumerate(replicates):
            blocks_by_group = {
                group: block_differences(cells[(timing, group)], metric)
                for group in range(8)
            }
            point, interval = bootstrap_median(
                blocks_by_group, random.Random(0x5EED_2 + replicate_index),
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
    parser.add_argument("--timing", choices=("early", "late"), required=True)
    parser.add_argument(
        "--replicate", nargs="+", action="append", required=True, type=Path,
        help="one complete replication, potentially split across log files",
    )
    parser.add_argument("--samples", type=int, default=20000)
    args = parser.parse_args()
    if len(args.replicate) < 2:
        parser.error("at least two replications are required")
    if args.samples <= 0:
        parser.error("bootstrap samples must be positive")
    try:
        result = pool(args.replicate, args.timing, args.samples)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
