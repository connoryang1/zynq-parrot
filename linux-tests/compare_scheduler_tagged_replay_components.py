#!/usr/bin/env python3
"""Attribute data, instruction, and joint tagged-replay effects across boots."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import METRICS, percentile
from compare_scheduler_tagged_replay_routes import block_differences, load


MODES = {
    "data": "data",
    "instruction": "instruction-explicit",
    "joint": "joint-explicit",
}
MODE_FIELDS = ("mode", "kernel_mode", "expected_hooks")


def _workload_config(config):
    """Remove only fields that define which replay components are active."""
    return {key: value for key, value in config.items()
            if key not in MODE_FIELDS}


def _load_arm(paths, label):
    if len(paths) < 2:
        raise ValueError(f"{label} requires at least two independent boots")
    loaded = [load(path) for path in paths]
    expected_mode = MODES[label]
    if any(result["config"]["mode"] != expected_mode
           for result, _rows in loaded):
        raise ValueError(f"{label} transcripts must use {expected_mode}")
    return loaded


def _draw(rng, strata):
    """Resample balanced blocks within every independent boot stratum."""
    sample = [
        value
        for stratum in strata
        for value in rng.choices(stratum, k=len(stratum))
    ]
    return statistics.median(sample)


def compare(data_paths, instruction_paths, joint_paths,
            bootstrap_samples=20000):
    """Return component increments and their non-additive interaction."""
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    paths = {
        "data": [Path(path) for path in data_paths],
        "instruction": [Path(path) for path in instruction_paths],
        "joint": [Path(path) for path in joint_paths],
    }
    arms = {label: _load_arm(arm_paths, label)
            for label, arm_paths in paths.items()}

    reference = arms["data"][0][0]
    workload = _workload_config(reference["config"])
    identity = reference["identity"]
    for label, loaded in arms.items():
        for index, (result, _rows) in enumerate(loaded):
            if _workload_config(result["config"]) != workload:
                raise ValueError(
                    f"{label} replicate {index} workload configuration mismatch"
                )
            if result["identity"] != identity:
                raise ValueError(
                    f"{label} replicate {index} exact image identity mismatch"
                )

    output = {
        "purpose": (
            "Attribute exact-image data-only, instruction-only, and joint "
            "tagged-replay effects while preserving independent-boot strata."
        ),
        "workload_config": workload,
        "identity": identity,
        "arms": {
            label: {
                "mode": MODES[label],
                "transcripts": [str(path) for path in paths[label]],
            }
            for label in ("data", "instruction", "joint")
        },
        "bootstrap_samples": bootstrap_samples,
        "metrics": {},
        "interpretation_limits": [
            "Each transcript contains its own matched enabled/disabled arms.",
            "Component arms are independent boots, not paired simultaneous runs.",
            "Interaction is joint minus instruction-only minus data-only effect.",
        ],
    }
    rng = random.Random(0x434F4D50)
    for metric in METRICS:
        strata = {
            label: [block_differences(rows, metric)
                    for _result, rows in loaded]
            for label, loaded in arms.items()
        }
        points = {
            label: statistics.median(
                value for stratum in arm_strata for value in stratum
            )
            for label, arm_strata in strata.items()
        }
        instruction_increment_draws = []
        data_increment_draws = []
        interaction_draws = []
        for _ in range(bootstrap_samples):
            draws = {label: _draw(rng, arm_strata)
                     for label, arm_strata in strata.items()}
            instruction_increment_draws.append(draws["joint"] - draws["data"])
            data_increment_draws.append(draws["joint"] - draws["instruction"])
            interaction_draws.append(
                draws["joint"] - draws["instruction"] - draws["data"]
            )
        output["metrics"][metric] = {
            "data_only_saved_cycles": points["data"],
            "instruction_only_saved_cycles": points["instruction"],
            "joint_saved_cycles": points["joint"],
            "instruction_increment_with_data_saved_cycles": (
                points["joint"] - points["data"]
            ),
            "instruction_increment_with_data_95pct_ci_saved_cycles": [
                percentile(instruction_increment_draws, 0.025),
                percentile(instruction_increment_draws, 0.975),
            ],
            "data_increment_with_instruction_saved_cycles": (
                points["joint"] - points["instruction"]
            ),
            "data_increment_with_instruction_95pct_ci_saved_cycles": [
                percentile(data_increment_draws, 0.025),
                percentile(data_increment_draws, 0.975),
            ],
            "nonadditive_interaction_cycles": (
                points["joint"] - points["instruction"] - points["data"]
            ),
            "nonadditive_interaction_95pct_ci_cycles": [
                percentile(interaction_draws, 0.025),
                percentile(interaction_draws, 0.975),
            ],
        }
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", nargs="+", required=True, type=Path)
    parser.add_argument("--instruction", nargs="+", required=True, type=Path)
    parser.add_argument("--joint", nargs="+", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(
            args.data, args.instruction, args.joint, args.bootstrap_samples
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite output: {args.output}")
        args.output.write_text(rendered)
        print(f"wrote {args.output}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
