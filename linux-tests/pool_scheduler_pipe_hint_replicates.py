#!/usr/bin/env python3
"""Pool sustained pipe-hint replications with a hierarchical bootstrap."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_pipe_hint import analyze
from analyze_scheduler_tagged_replay import percentile


def _boot_effects(result, key):
    return [pair[key] for pair in result["pairs"]]


def pool(paths, bootstrap_samples=20000):
    """Validate and pool matched pairs while resampling boots and pairs."""
    if len(paths) < 2:
        raise ValueError("at least two independent boot replications are required")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")

    # analyze() remains the fail-closed authority for transcript identity,
    # balanced arm order, terminal markers, and controller drain. Its local
    # interval is not used here, so one draw avoids redundant work.
    results = [analyze(path, bootstrap_samples=1) for path in paths]
    config = results[0]["config"]
    identity = results[0]["identity"]
    for index, result in enumerate(results[1:], start=1):
        if result["config"] != config:
            raise ValueError(f"replicate {index} configuration mismatch")
        if result["identity"] != identity:
            raise ValueError(f"replicate {index} identity mismatch")

    cycle_strata = [_boot_effects(result, "saved_cycles_per_roundtrip")
                    for result in results]
    percent_strata = [_boot_effects(result, "saved_percent")
                      for result in results]
    flat_cycles = [value for boot in cycle_strata for value in boot]
    flat_percent = [value for boot in percent_strata for value in boot]

    # The first resampling level represents independent Linux boots. The
    # second represents the matched repeat blocks inside each selected boot.
    # This is deliberately more conservative than treating all blocks as one
    # exchangeable sample.
    rng = random.Random(0x50495046)
    cycle_draws = []
    percent_draws = []
    boot_indices = range(len(results))
    for _ in range(bootstrap_samples):
        sampled_boots = rng.choices(boot_indices, k=len(results))
        sampled_cycles = []
        sampled_percent = []
        for boot_index in sampled_boots:
            cycles = cycle_strata[boot_index]
            percents = percent_strata[boot_index]
            indices = rng.choices(range(len(cycles)), k=len(cycles))
            sampled_cycles.extend(cycles[index] for index in indices)
            sampled_percent.extend(percents[index] for index in indices)
        cycle_draws.append(statistics.median(sampled_cycles))
        percent_draws.append(statistics.median(sampled_percent))

    return {
        "purpose": (
            "Pool sustained hot pipe-hint comparisons while preserving "
            "matched pairs and independent Linux-boot variation."
        ),
        "config": config,
        "identity": identity,
        "replicates": [str(path) for path in paths],
        "replicate_count": len(paths),
        "bootstrap_samples": bootstrap_samples,
        "replicate_saved_cycles_per_roundtrip": [
            statistics.median(values) for values in cycle_strata
        ],
        "replicate_saved_percent": [
            statistics.median(values) for values in percent_strata
        ],
        "pooled": {
            "paired_median_saved_cycles_per_roundtrip": statistics.median(
                flat_cycles),
            "hierarchical_95pct_ci_saved_cycles_per_roundtrip": [
                percentile(cycle_draws, 0.025),
                percentile(cycle_draws, 0.975),
            ],
            "paired_median_saved_percent": statistics.median(flat_percent),
            "hierarchical_95pct_ci_saved_percent": [
                percentile(percent_draws, 0.025),
                percentile(percent_draws, 0.975),
            ],
        },
        "interpretation_limits": [
            "The three boots support a sustained hot ping-pong workload, not a cold first-resume claim.",
            "The interval is a hierarchical bootstrap over a small number of independent boots.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", nargs="+", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = pool(args.transcript, args.bootstrap_samples)
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
