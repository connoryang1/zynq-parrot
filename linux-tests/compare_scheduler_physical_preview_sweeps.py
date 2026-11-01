#!/usr/bin/env python3
"""Compare two complete physical-preview sweeps with an independent bootstrap."""

import argparse
import gzip
import json
import random
import re
import statistics
from pathlib import Path

from analyze_scheduler_physical_preview_benchmark import (
    METRICS,
    TIMING_MODES,
    percentile,
)
from analyze_scheduler_physical_preview_sweep import block_differences, parse_segments


EXPECTED_CELLS = {
    (timing, group)
    for timing in ("early", "late")
    for group in range(8)
}


def read_transcript(path):
    """Read retained plain-text or gzip-compressed board evidence."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", errors="replace") as stream:
            return stream.read()
    return path.read_text(errors="replace")


def load_cells(paths, label, expected_cells=EXPECTED_CELLS):
    """Require one complete, board-passing matrix and retain its raw rows."""
    cells = {}
    board_text = ""
    for path in paths:
        text = read_transcript(path)
        board_text += text
        for key, rows, _result in parse_segments(
                text, path, summarize_cells=False):
            if key in cells:
                raise ValueError(f"{label}: duplicate timing/group cell: {key}")
            cells[key] = rows
    if set(cells) != expected_cells:
        missing = sorted(expected_cells - set(cells))
        extra = sorted(set(cells) - expected_cells)
        raise ValueError(
            f"{label}: incomplete sweep; missing={missing}, extra={extra}"
        )
    if not re.search(r"\bCORE(?:\[0\])? PASS\b", board_text):
        raise ValueError(f"{label}: missing final board CORE PASS marker")
    if not re.search(r"\bBSG PASS\b", board_text):
        raise ValueError(f"{label}: missing final board BSG PASS marker")
    return cells


def resampled_median(blocks_by_group, rng):
    """Preserve each cache-set stratum while resampling paired trial blocks."""
    values = []
    for blocks in blocks_by_group.values():
        values.extend(rng.choices(blocks, k=len(blocks)))
    return statistics.median(values)


def compare_timing_pairs(control_paths, candidate_paths, timing_pairs,
                         samples=20000):
    """Compare predeclared control/candidate timing effects across boots."""
    control_expected = {
        (control_timing, group)
        for control_timing, _candidate_timing in timing_pairs
        for group in range(8)
    }
    candidate_expected = {
        (candidate_timing, group)
        for _control_timing, candidate_timing in timing_pairs
        for group in range(8)
    }
    control = load_cells(control_paths, "control", control_expected)
    candidate = load_cells(candidate_paths, "candidate", candidate_expected)
    rng = random.Random(0x1_CA_C4_E)
    output = {"bootstrap_samples": samples, "timings": {}, "timing_pairs": {}}
    for control_timing, candidate_timing in timing_pairs:
        label = (candidate_timing if candidate_timing == control_timing else
                 f"{candidate_timing}_minus_{control_timing}")
        output["timings"][label] = {}
        output["timing_pairs"][label] = {
            "control": control_timing,
            "candidate": candidate_timing,
        }
        for metric in METRICS:
            control_blocks = {
                group: block_differences(
                    control[(control_timing, group)], metric
                )
                for group in range(8)
            }
            candidate_blocks = {
                group: block_differences(
                    candidate[(candidate_timing, group)], metric
                )
                for group in range(8)
            }
            control_point = statistics.median(
                value for blocks in control_blocks.values() for value in blocks
            )
            candidate_point = statistics.median(
                value for blocks in candidate_blocks.values() for value in blocks
            )
            boot = [
                resampled_median(candidate_blocks, rng)
                - resampled_median(control_blocks, rng)
                for _ in range(samples)
            ]
            output["timings"][label][metric] = {
                "control_saved_cycles": control_point,
                "candidate_saved_cycles": candidate_point,
                "candidate_minus_control_saved_cycles": (
                    candidate_point - control_point
                ),
                "candidate_minus_control_95pct_ci": [
                    percentile(boot, 0.025),
                    percentile(boot, 0.975),
                ],
            }
    return output


def compare(control_paths, candidate_paths, samples=20000,
            timings=("early", "late")):
    """Return candidate-minus-control differences between matching timings."""
    return compare_timing_pairs(
        control_paths,
        candidate_paths,
        tuple((timing, timing) for timing in timings),
        samples,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", nargs="+", required=True, type=Path)
    parser.add_argument("--candidate", nargs="+", required=True, type=Path)
    parser.add_argument("--timing", choices=tuple(TIMING_MODES),
                        help="compare one predeclared timing instead of both")
    parser.add_argument("--control-timing", choices=tuple(TIMING_MODES),
                        help="control timing for a cross-mode comparison")
    parser.add_argument("--candidate-timing", choices=tuple(TIMING_MODES),
                        help="candidate timing for a cross-mode comparison")
    parser.add_argument("--samples", type=int, default=20000)
    args = parser.parse_args()
    if args.samples <= 0:
        parser.error("bootstrap samples must be positive")
    try:
        cross_mode = (
            args.control_timing is not None
            or args.candidate_timing is not None
        )
        if cross_mode:
            if (args.timing is not None or args.control_timing is None
                    or args.candidate_timing is None):
                parser.error(
                    "cross-mode comparison requires both --control-timing and "
                    "--candidate-timing, without --timing"
                )
            result = compare_timing_pairs(
                args.control,
                args.candidate,
                ((args.control_timing, args.candidate_timing),),
                args.samples,
            )
        else:
            timings = (args.timing,) if args.timing else ("early", "late")
            result = compare(args.control, args.candidate, args.samples, timings)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
