#!/usr/bin/env python3
"""Compare data-only prewake with joint instruction/data preseed across boots."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import METRICS, percentile
from analyze_scheduler_tagged_replay_tail import (
    TAIL_METRICS,
    block_effects as tail_block_effects,
    load as load_tail,
)
from pool_scheduler_tagged_replay_replicates import block_effects, load_rows


CONTROL_MODE = "data-prewake-equalized-quiescent"
CANDIDATE_MODE = "joint-preseed-quiescent"


def _workload_config(config):
    """Remove only the replay-component selector from a validated config."""
    return {key: value for key, value in config.items() if key != "mode"}


def _draw(rng, strata, value_index):
    """Resample balanced blocks within each independent boot stratum."""
    sample = [
        effect[value_index]
        for stratum in strata
        for effect in rng.choices(stratum, k=len(stratum))
    ]
    return statistics.median(sample)


def compare(control_paths, candidate_paths, bootstrap_samples=20000):
    """Measure the incremental value of early instruction preseed."""
    if len(control_paths) < 2 or len(candidate_paths) < 2:
        raise ValueError("each prewake mode requires at least two independent boots")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    control_paths = [Path(path) for path in control_paths]
    candidate_paths = [Path(path) for path in candidate_paths]
    controls = [load_rows(path) for path in control_paths]
    candidates = [load_rows(path) for path in candidate_paths]
    if any(result["config"]["mode"] != CONTROL_MODE
           for result, _rows in controls):
        raise ValueError(f"control transcripts must use {CONTROL_MODE}")
    if any(result["config"]["mode"] != CANDIDATE_MODE
           for result, _rows in candidates):
        raise ValueError(f"candidate transcripts must use {CANDIDATE_MODE}")

    reference = controls[0][0]
    workload = _workload_config(reference["config"])
    identity = reference["identity"]
    for label, loaded in (("control", controls), ("candidate", candidates)):
        for index, (result, _rows) in enumerate(loaded):
            if _workload_config(result["config"]) != workload:
                raise ValueError(
                    f"{label} replicate {index} workload configuration mismatch"
                )
            if result["identity"] != identity:
                raise ValueError(
                    f"{label} replicate {index} exact image identity mismatch"
                )
    if any(result["icache_prefix_status"]["before"]["configured_entries"] != 32
           for result, _rows in candidates):
        raise ValueError("joint preseed requires one exact 32-entry prefix table")

    rng = random.Random(0x50524557)
    output = {
        "purpose": (
            "Measure the incremental effect of a drained 32-line instruction "
            "preseed over the same drained 32-line data prewake."
        ),
        "workload_config": workload,
        "identity": identity,
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
        "tail_metrics": {},
        "interpretation_limits": [
            "Both arms execute one replay attempt per trial and use the same frozen whole-block duration filter.",
            "Control and candidate boots are independent strata rather than simultaneous paired runs.",
            "Replay issue cost occurs before readiness and is excluded from the measured wake interval.",
        ],
    }
    for metric in (*METRICS, "prewake_cycles"):
        control_strata = [block_effects(rows, metric)
                           for _result, rows in controls]
        candidate_strata = [block_effects(rows, metric)
                             for _result, rows in candidates]
        control_points = [effect for stratum in control_strata for effect in stratum]
        candidate_points = [effect for stratum in candidate_strata for effect in stratum]
        control_cycles = statistics.median(effect[0] for effect in control_points)
        candidate_cycles = statistics.median(effect[0] for effect in candidate_points)
        control_percent = statistics.median(effect[1] for effect in control_points)
        candidate_percent = statistics.median(effect[1] for effect in candidate_points)
        cycle_draws = []
        percent_draws = []
        for _ in range(bootstrap_samples):
            cycle_draws.append(
                _draw(rng, candidate_strata, 0) - _draw(rng, control_strata, 0)
            )
            percent_draws.append(
                _draw(rng, candidate_strata, 1) - _draw(rng, control_strata, 1)
            )
        output["metrics"][metric] = {
            "data_only_saved_cycles": control_cycles,
            "joint_preseed_saved_cycles": candidate_cycles,
            "instruction_increment_saved_cycles": candidate_cycles - control_cycles,
            "instruction_increment_95pct_ci_saved_cycles": [
                percentile(cycle_draws, 0.025), percentile(cycle_draws, 0.975)
            ],
            "data_only_saved_percent": control_percent,
            "joint_preseed_saved_percent": candidate_percent,
            "instruction_increment_saved_percentage_points": (
                candidate_percent - control_percent
            ),
            "instruction_increment_95pct_ci_saved_percentage_points": [
                percentile(percent_draws, 0.025),
                percentile(percent_draws, 0.975),
            ],
        }
    tail_controls = [load_tail(path) for path in control_paths]
    tail_candidates = [load_tail(path) for path in candidate_paths]
    for metric in TAIL_METRICS:
        control_strata = [tail_block_effects(rows, metric)
                           for _result, rows in tail_controls]
        candidate_strata = [tail_block_effects(rows, metric)
                             for _result, rows in tail_candidates]
        control_points = [effect for stratum in control_strata for effect in stratum]
        candidate_points = [effect for stratum in candidate_strata for effect in stratum]
        control_cycles = statistics.median(effect[0] for effect in control_points)
        candidate_cycles = statistics.median(effect[0] for effect in candidate_points)
        control_percent = statistics.median(effect[1] for effect in control_points)
        candidate_percent = statistics.median(effect[1] for effect in candidate_points)
        cycle_draws = []
        percent_draws = []
        for _ in range(bootstrap_samples):
            cycle_draws.append(
                _draw(rng, candidate_strata, 0) - _draw(rng, control_strata, 0)
            )
            percent_draws.append(
                _draw(rng, candidate_strata, 1) - _draw(rng, control_strata, 1)
            )
        output["tail_metrics"][metric] = {
            "data_only_saved_cycles": control_cycles,
            "joint_preseed_saved_cycles": candidate_cycles,
            "instruction_increment_saved_cycles": candidate_cycles - control_cycles,
            "instruction_increment_95pct_ci_saved_cycles": [
                percentile(cycle_draws, 0.025), percentile(cycle_draws, 0.975)
            ],
            "data_only_saved_percent": control_percent,
            "joint_preseed_saved_percent": candidate_percent,
            "instruction_increment_saved_percentage_points": (
                candidate_percent - control_percent
            ),
            "instruction_increment_95pct_ci_saved_percentage_points": [
                percentile(percent_draws, 0.025),
                percentile(percent_draws, 0.975),
            ],
        }
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", nargs="+", required=True, type=Path)
    parser.add_argument("--joint", nargs="+", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    args = parser.parse_args(argv)
    try:
        result = compare(args.data, args.joint, args.bootstrap_samples)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
