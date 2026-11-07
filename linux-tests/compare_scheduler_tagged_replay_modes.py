#!/usr/bin/env python3
"""Compare full-table and direction-selected replay on one exact image."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import METRICS, percentile
from compare_scheduler_tagged_replay_routes import block_differences, load


CONTROL_MODE = "instruction-explicit-roundtrip"
CANDIDATE_MODE = "instruction-explicit-directed"


def _without_mode(config):
    """Return workload knobs that must remain fixed across the mode split."""
    return {
        key: value for key, value in config.items()
        if key not in ("mode", "icache_ranges")
    }


def compare(control_paths, candidate_paths, bootstrap_samples=20000):
    """Measure directional-minus-full A/B benefit across fresh boot strata."""
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    if isinstance(control_paths, (str, Path)):
        control_paths = [Path(control_paths)]
    if isinstance(candidate_paths, (str, Path)):
        candidate_paths = [Path(candidate_paths)]
    if not control_paths or not candidate_paths:
        raise ValueError("each replay mode requires at least one transcript")

    controls = [load(path) for path in control_paths]
    candidates = [load(path) for path in candidate_paths]
    if any(result["config"]["mode"] != CONTROL_MODE
           for result, _rows in controls):
        raise ValueError(f"control transcripts must use {CONTROL_MODE}")
    if any(result["config"]["mode"] != CANDIDATE_MODE
           for result, _rows in candidates):
        raise ValueError(f"candidate transcripts must use {CANDIDATE_MODE}")

    reference = controls[0][0]
    workload = _without_mode(reference["config"])
    for result, _rows in controls[1:] + candidates:
        if _without_mode(result["config"]) != workload:
            raise ValueError("mode comparison workload configurations do not match")
        if result["identity"] != reference["identity"]:
            raise ValueError("mode comparison requires one exact image identity")

    loaded = controls + candidates
    counts = {
        result["icache_prefix_status"]["before"]["configured_entries"]
        for result, _rows in loaded
    }
    if counts != {16}:
        raise ValueError("mode comparison requires one shared 16-entry table")

    rng = random.Random(0x7A66ED05)
    output = {
        "purpose": (
            "Compare full-table replay on both directions with direction-selected "
            "eight-entry replay while holding route, image, and workload fixed."
        ),
        "workload_config": workload,
        "identity": reference["identity"],
        "configured_entries": 16,
        "control": {
            "mode": CONTROL_MODE,
            "transcripts": [str(path) for path in control_paths],
        },
        "candidate": {
            "mode": CANDIDATE_MODE,
            "transcripts": [str(path) for path in candidate_paths],
        },
        "bootstrap_samples": bootstrap_samples,
        "metrics": {},
        "interpretation_limits": [
            "Each transcript contains its own matched enabled/disabled A/B arms.",
            "Boot strata are resampled independently within each runtime mode.",
        ],
    }
    for metric in METRICS:
        control_strata = [
            block_differences(rows, metric) for _result, rows in controls
        ]
        candidate_strata = [
            block_differences(rows, metric) for _result, rows in candidates
        ]
        control_blocks = [
            value for stratum in control_strata for value in stratum
        ]
        candidate_blocks = [
            value for stratum in candidate_strata for value in stratum
        ]
        control_point = statistics.median(control_blocks)
        candidate_point = statistics.median(candidate_blocks)
        draws = []
        for _ in range(bootstrap_samples):
            control_sample = [
                value for stratum in control_strata
                for value in rng.choices(stratum, k=len(stratum))
            ]
            candidate_sample = [
                value for stratum in candidate_strata
                for value in rng.choices(stratum, k=len(stratum))
            ]
            draws.append(
                statistics.median(candidate_sample)
                - statistics.median(control_sample)
            )
        output["metrics"][metric] = {
            "full_table_saved_cycles": control_point,
            "direction_selected_saved_cycles": candidate_point,
            "direction_selected_incremental_saved_cycles": (
                candidate_point - control_point
            ),
            "direction_selected_incremental_95pct_ci_saved_cycles": [
                percentile(draws, 0.025), percentile(draws, 0.975)
            ],
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--control-replicate", action="append", default=[],
                        type=Path)
    parser.add_argument("--candidate-replicate", action="append", default=[],
                        type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    args = parser.parse_args()
    try:
        result = compare(
            [args.control, *args.control_replicate],
            [args.candidate, *args.candidate_replicate],
            args.bootstrap_samples,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
