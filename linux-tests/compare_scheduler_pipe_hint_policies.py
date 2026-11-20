#!/usr/bin/env python3
"""Compare retained-prefix and refresh policies across independent boots."""

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


def compare(seed_paths, continuous_paths, bootstrap_samples=20000,
            baseline_policy="seed", comparison_policy="continuous"):
    """Return comparison-minus-baseline effects with strict identity.

    The original positional path arguments and continuous output aliases remain
    supported; new callers can select deployment-shaped futex policies.
    """
    if baseline_policy not in ("seed", "preseed", "continuous-unmatched", "futex-early"):
        raise ValueError(
            "baseline policy must be seed, preseed, continuous-unmatched, or futex-early")
    if comparison_policy not in ("continuous", "futex-early", "futex-early-both"):
        raise ValueError("comparison policy must be continuous, futex-early, or futex-early-both")
    if comparison_policy == baseline_policy:
        raise ValueError("comparison and baseline policies must differ")
    if len(seed_paths) < 2 or len(continuous_paths) < 2:
        raise ValueError("each policy requires at least two independent boots")
    all_paths = [path.resolve() for path in (*seed_paths, *continuous_paths)]
    if len(set(all_paths)) != len(all_paths):
        raise ValueError("independent boots require distinct transcript paths")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    seed = _load(seed_paths, baseline_policy)
    continuous = _load(continuous_paths, comparison_policy)
    reference_identity = seed[0]["identity"]
    reference_config = {key: value for key, value in seed[0]["config"].items()
                        if key != "policy"}
    for label, results in ((baseline_policy, seed), (comparison_policy, continuous)):
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
    effect = {
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
    }
    output = {
        "purpose": (
            f"Measure the incremental sustained benefit of {comparison_policy} "
            f"over {baseline_policy} using one exact ELF."
        ),
        "baseline_policy": baseline_policy,
        "comparison_policy": comparison_policy,
        "identity": reference_identity,
        "config": reference_config,
        "baseline_replicates": [str(path) for path in seed_paths],
        "comparison_replicates": [str(path) for path in continuous_paths],
        "bootstrap_samples": bootstrap_samples,
        "baseline_saved_cycles_per_boot": [statistics.median(boot) for boot in seed_cycles],
        "comparison_saved_cycles_per_boot": [statistics.median(boot) for boot in continuous_cycles],
        "comparison_minus_baseline": effect,
    }
    if comparison_policy == "continuous":
        output["seed_replicates"] = output["baseline_replicates"]
        output["continuous_replicates"] = output["comparison_replicates"]
        output["seed_saved_cycles_per_boot"] = output["baseline_saved_cycles_per_boot"]
        output["continuous_saved_cycles_per_boot"] = output["comparison_saved_cycles_per_boot"]
        output["continuous_minus_baseline"] = effect
        if baseline_policy == "seed":
            output["continuous_minus_seed"] = effect
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", "--baseline", nargs="+", required=True, type=Path)
    parser.add_argument("--continuous", "--comparison", nargs="+", required=True, type=Path)
    parser.add_argument("--baseline-policy",
                        choices=("seed", "preseed", "continuous-unmatched", "futex-early"),
                        default="seed")
    parser.add_argument("--comparison-policy", choices=("continuous", "futex-early", "futex-early-both"),
                        default="continuous")
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.seed, args.continuous, args.bootstrap_samples,
                         args.baseline_policy, args.comparison_policy)
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
