#!/usr/bin/env python3
"""Expose chronology and arm-position effects in one complete preview sweep."""

import argparse
import json
import random
import re
import statistics
from pathlib import Path

from analyze_scheduler_physical_preview_benchmark import METRICS, percentile
from compare_scheduler_physical_preview_sweeps import load_cells, read_transcript


WINDOWS = {
    "quarter_1": (0, 32),
    "quarter_2": (32, 64),
    "quarter_3": (64, 96),
    "quarter_4": (96, 128),
    "half_1": (0, 64),
    "half_2": (64, 128),
    "complete": (0, 128),
}
REPLAY_STATE = re.compile(
    r"PHYSICAL_BENCH_CONFIG[^\n]* replay_state=(persistent|isolated)"
)


def position_contrasts(rows, metric, start, end):
    """Return named contrasts for balanced [off,on,on,off] block positions."""
    result = {name: [] for name in (
        "paired_saved",
        "off0_minus_on1",
        "off3_minus_on2",
        "off3_minus_off0",
        "on2_minus_on1",
    )}
    for block_index in range(start, end):
        off0, on1, on2, off3 = rows[4 * block_index:4 * block_index + 4]
        result["paired_saved"].append(
            ((off0[metric] + off3[metric])
             - (on1[metric] + on2[metric])) / 2
        )
        result["off0_minus_on1"].append(off0[metric] - on1[metric])
        result["off3_minus_on2"].append(off3[metric] - on2[metric])
        result["off3_minus_off0"].append(off3[metric] - off0[metric])
        result["on2_minus_on1"].append(on2[metric] - on1[metric])
    return result


def stratified_median(values_by_group, rng, samples):
    point = statistics.median(
        value for values in values_by_group.values() for value in values
    )
    boot = []
    for _ in range(samples):
        values = []
        for group_values in values_by_group.values():
            values.extend(rng.choices(group_values, k=len(group_values)))
        boot.append(statistics.median(values))
    return {
        "median_cycles": point,
        "stratified_95pct_ci_cycles": [
            percentile(boot, 0.025), percentile(boot, 0.975)
        ],
    }


def analyze(paths, timing, samples=2000):
    expected = {(timing, group) for group in range(8)}
    cells = load_cells(paths, "chronology", expected)
    state_markers = [
        match.group(1)
        for path in paths
        for match in REPLAY_STATE.finditer(read_transcript(path))
    ]
    if state_markers and (len(state_markers) != 8
                          or len(set(state_markers)) != 1):
        raise ValueError("mixed or incomplete replay-state markers")
    replay_state = (state_markers[0] if state_markers
                    else "historical-persistent")
    rng = random.Random(0xC4_770)
    output = {
        "timing": timing,
        "replay_state": replay_state,
        "bootstrap_samples": samples,
        "contrast_signs": {
            "paired_saved": "positive means enabled is faster",
            "off0_minus_on1": "positive means first enabled is faster",
            "off3_minus_on2": "positive means second enabled is faster",
            "off3_minus_off0": "negative means trailing disabled is faster",
            "on2_minus_on1": "negative means second enabled is faster",
        },
        "windows": {},
    }
    for window, (start, end) in WINDOWS.items():
        output["windows"][window] = {
            "block_range": [start, end],
            "metrics": {},
        }
        for metric in METRICS:
            grouped = {
                group: position_contrasts(
                    cells[(timing, group)], metric, start, end
                )
                for group in range(8)
            }
            output["windows"][window]["metrics"][metric] = {
                contrast: stratified_median(
                    {group: values[contrast]
                     for group, values in grouped.items()},
                    rng,
                    samples,
                )
                for contrast in next(iter(grouped.values()))
            }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", nargs="+", type=Path)
    parser.add_argument("--timing", required=True,
                        choices=("early", "late", "instruction", "counter",
                                 "trigger", "wake-trigger", "wake-data",
                                 "wake-early-data"))
    parser.add_argument(
        "--samples", type=int, default=2000,
        help=("exploratory bootstrap count; the primary pooled effect keeps "
              "the separate analyzer's 20,000-sample acceptance interval"),
    )
    args = parser.parse_args()
    if args.samples <= 0:
        parser.error("bootstrap samples must be positive")
    try:
        result = analyze(args.transcript, args.timing, args.samples)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
