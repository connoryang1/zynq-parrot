#!/usr/bin/env python3
"""Compare seed-only and continuous pipe hints across independent boots."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_pipe_hint import analyze
from analyze_scheduler_tagged_replay import percentile


def _load(paths, policy):
    results = [analyze(path, bootstrap_samples=1) for path in paths]
    for index, result in enumerate(results):
        if result["config"]["policy"] != policy:
            raise ValueError(f"{policy} replicate {index} has wrong policy")
    return results


def _strata(results, key):
    return [[pair[key] for pair in result["pairs"]] for result in results]


def _draw_hierarchical(rng, strata):
    sample = []
    for boot_index in rng.choices(range(len(strata)), k=len(strata)):
        boot = strata[boot_index]
        sample.extend(rng.choices(boot, k=len(boot)))
    return statistics.median(sample)


def compare(seed_paths, continuous_paths, bootstrap_samples=20000):
    """Return continuous-minus-seed incremental effects with strict identity."""
    if len(seed_paths) < 2 or len(continuous_paths) < 2:
        raise ValueError("each policy requires at least two independent boots")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    seed = _load(seed_paths, "seed")
    continuous = _load(continuous_paths, "continuous")
    reference_identity = seed[0]["identity"]
    reference_config = {key: value for key, value in seed[0]["config"].items()
                        if key != "policy"}
    for label, results in (("seed", seed), ("continuous", continuous)):
        for index, result in enumerate(results):
            config = {key: value for key, value in result["config"].items()
                      if key != "policy"}
            if result["identity"] != reference_identity:
                raise ValueError(f"{label} replicate {index} identity mismatch")
            if config != reference_config:
                raise ValueError(f"{label} replicate {index} configuration mismatch")

    seed_cycles = _strata(seed, "saved_cycles_per_roundtrip")
    continuous_cycles = _strata(continuous, "saved_cycles_per_roundtrip")
    seed_percent = _strata(seed, "saved_percent")
    continuous_percent = _strata(continuous, "saved_percent")
    flat = lambda values: [item for boot in values for item in boot]
    point_cycles = (statistics.median(flat(continuous_cycles))
                    - statistics.median(flat(seed_cycles)))
    point_percent = (statistics.median(flat(continuous_percent))
                     - statistics.median(flat(seed_percent)))
    rng = random.Random(0x504F4C49)
    cycle_draws = []
    percent_draws = []
    for _ in range(bootstrap_samples):
        cycle_draws.append(
            _draw_hierarchical(rng, continuous_cycles)
            - _draw_hierarchical(rng, seed_cycles))
        percent_draws.append(
            _draw_hierarchical(rng, continuous_percent)
            - _draw_hierarchical(rng, seed_percent))
    return {
        "purpose": (
            "Measure the incremental sustained benefit of continuous hints "
            "over a one-time cache-state seed using one exact ELF."
        ),
        "identity": reference_identity,
        "config": reference_config,
        "seed_replicates": [str(path) for path in seed_paths],
        "continuous_replicates": [str(path) for path in continuous_paths],
        "bootstrap_samples": bootstrap_samples,
        "seed_saved_cycles_per_boot": [statistics.median(boot)
                                       for boot in seed_cycles],
        "continuous_saved_cycles_per_boot": [statistics.median(boot)
                                             for boot in continuous_cycles],
        "continuous_minus_seed": {
            "saved_cycles_per_roundtrip": point_cycles,
            "hierarchical_95pct_ci_saved_cycles_per_roundtrip": [
                percentile(cycle_draws, 0.025),
                percentile(cycle_draws, 0.975),
            ],
            "saved_percentage_points": point_percent,
            "hierarchical_95pct_ci_saved_percentage_points": [
                percentile(percent_draws, 0.025),
                percentile(percent_draws, 0.975),
            ],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", nargs="+", required=True, type=Path)
    parser.add_argument("--continuous", nargs="+", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.seed, args.continuous, args.bootstrap_samples)
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
