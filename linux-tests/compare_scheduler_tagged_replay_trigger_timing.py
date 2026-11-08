#!/usr/bin/env python3
"""Compare successful-wakeup and pre-wake instruction replay timing."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import METRICS, percentile
from pool_scheduler_tagged_replay_replicates import block_effects, load_rows


CONTROL_MODE = "instruction-wake"
CANDIDATE_MODE = "instruction-explicit"


def _workload_config(config):
    """Remove only fields that encode the two trigger locations."""
    return {
        key: value for key, value in config.items()
        if key not in ("mode", "kernel_mode", "expected_hooks")
    }


def _draw(rng, strata, value_index):
    """Resample balanced blocks independently within each boot."""
    values = [
        effect[value_index]
        for stratum in strata
        for effect in rng.choices(stratum, k=len(stratum))
    ]
    return statistics.median(values)


def compare(wake_paths, explicit_paths, bootstrap_samples=20000):
    """Measure the direct value of moving replay before the wake operation."""
    if len(wake_paths) < 2 or len(explicit_paths) < 2:
        raise ValueError("each trigger location requires at least two boots")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    wake_paths = [Path(path) for path in wake_paths]
    explicit_paths = [Path(path) for path in explicit_paths]
    wake_runs = [load_rows(path) for path in wake_paths]
    explicit_runs = [load_rows(path) for path in explicit_paths]
    if any(result["config"]["mode"] != CONTROL_MODE
           for result, _rows in wake_runs):
        raise ValueError(f"control transcripts must use {CONTROL_MODE}")
    if any(result["config"]["mode"] != CANDIDATE_MODE
           for result, _rows in explicit_runs):
        raise ValueError(f"candidate transcripts must use {CANDIDATE_MODE}")

    reference = wake_runs[0][0]
    workload = _workload_config(reference["config"])
    identity = reference["identity"]
    for label, runs in (("control", wake_runs), ("candidate", explicit_runs)):
        for index, (result, _rows) in enumerate(runs):
            if _workload_config(result["config"]) != workload:
                raise ValueError(
                    f"{label} replicate {index} workload configuration mismatch"
                )
            if result["identity"] != identity:
                raise ValueError(
                    f"{label} replicate {index} exact image identity mismatch"
                )
            if (result["icache_prefix_status"]["before"]["configured_entries"]
                    != 32):
                raise ValueError("trigger comparison requires a 32-entry table")

    rng = random.Random(0x54524947)
    output = {
        "purpose": (
            "Measure the direct effect of moving the same shared instruction "
            "replay from successful wakeup to immediately before wake."
        ),
        "workload_config": workload,
        "identity": identity,
        "control": {
            "mode": CONTROL_MODE,
            "transcripts": [str(path) for path in wake_paths],
        },
        "candidate": {
            "mode": CANDIDATE_MODE,
            "transcripts": [str(path) for path in explicit_paths],
        },
        "bootstrap_samples": bootstrap_samples,
        "metrics": {},
        "interpretation_limits": [
            "Each transcript contains its own balanced enabled/disabled arms.",
            "Boot strata are independent rather than simultaneous paired runs.",
            "The pre-wake arm includes its matched prctl/no-op syscall cost.",
        ],
    }
    for metric in METRICS:
        wake_strata = [block_effects(rows, metric)
                       for _result, rows in wake_runs]
        explicit_strata = [block_effects(rows, metric)
                           for _result, rows in explicit_runs]
        wake_points = [effect for stratum in wake_strata for effect in stratum]
        explicit_points = [effect for stratum in explicit_strata
                           for effect in stratum]
        wake_cycles = statistics.median(effect[0] for effect in wake_points)
        explicit_cycles = statistics.median(
            effect[0] for effect in explicit_points
        )
        wake_percent = statistics.median(effect[1] for effect in wake_points)
        explicit_percent = statistics.median(
            effect[1] for effect in explicit_points
        )
        cycle_draws = []
        percent_draws = []
        for _ in range(bootstrap_samples):
            cycle_draws.append(
                _draw(rng, explicit_strata, 0) - _draw(rng, wake_strata, 0)
            )
            percent_draws.append(
                _draw(rng, explicit_strata, 1) - _draw(rng, wake_strata, 1)
            )
        output["metrics"][metric] = {
            "successful_wakeup_saved_cycles": wake_cycles,
            "prewake_saved_cycles": explicit_cycles,
            "prewake_increment_saved_cycles": explicit_cycles - wake_cycles,
            "prewake_increment_95pct_ci_saved_cycles": [
                percentile(cycle_draws, 0.025), percentile(cycle_draws, 0.975)
            ],
            "successful_wakeup_saved_percent": wake_percent,
            "prewake_saved_percent": explicit_percent,
            "prewake_increment_saved_percentage_points": (
                explicit_percent - wake_percent
            ),
            "prewake_increment_95pct_ci_saved_percentage_points": [
                percentile(percent_draws, 0.025),
                percentile(percent_draws, 0.975),
            ],
        }
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wake", nargs="+", required=True, type=Path)
    parser.add_argument("--prewake", nargs="+", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    args = parser.parse_args(argv)
    try:
        result = compare(args.wake, args.prewake, args.bootstrap_samples)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
