#!/usr/bin/env python3
"""Compare two preseed pipe-prefix capacities across independent boots."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_pipe_hint import analyze
from analyze_scheduler_tagged_replay import percentile


def _load(paths):
    return [analyze(path, bootstrap_samples=1) for path in paths]


def _strata(results, key):
    return [[pair[key] for pair in result["pairs"]] for result in results]


def _draw(rng, strata):
    sample = []
    for boot_index in rng.choices(range(len(strata)), k=len(strata)):
        sample.extend(rng.choices(strata[boot_index], k=len(strata[boot_index])))
    return statistics.median(sample)


def compare(small_paths, large_paths, bootstrap_samples=20000):
    """Return large-minus-small effects while allowing only NBF/count changes."""
    if len(small_paths) < 2 or len(large_paths) < 2:
        raise ValueError("each capacity requires at least two independent boots")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    small = _load(small_paths)
    large = _load(large_paths)
    small_count = small[0]["config"]["configured_entries"]
    large_count = large[0]["config"]["configured_entries"]
    if small_count >= large_count:
        raise ValueError("small capacity must be less than large capacity")
    reference_identity = {key: value for key, value in small[0]["identity"].items()
                          if key != "nbf_sha256"}
    reference_config = {key: value for key, value in small[0]["config"].items()
                        if key != "configured_entries"}
    nbf_by_capacity = {}
    for label, count, results in (("small", small_count, small),
                                  ("large", large_count, large)):
        for index, result in enumerate(results):
            if result["config"]["configured_entries"] != count:
                raise ValueError(f"{label} replicate {index} count mismatch")
            config = {key: value for key, value in result["config"].items()
                      if key != "configured_entries"}
            identity = {key: value for key, value in result["identity"].items()
                        if key != "nbf_sha256"}
            if config != reference_config:
                raise ValueError(f"{label} replicate {index} configuration mismatch")
            if identity != reference_identity:
                raise ValueError(f"{label} replicate {index} identity mismatch")
            prior = nbf_by_capacity.setdefault(count,
                                                result["identity"]["nbf_sha256"])
            if result["identity"]["nbf_sha256"] != prior:
                raise ValueError(f"{label} replicate {index} NBF mismatch")
    if nbf_by_capacity[small_count] == nbf_by_capacity[large_count]:
        raise ValueError("capacity arms unexpectedly use the same NBF")

    small_cycles = _strata(small, "saved_cycles_per_roundtrip")
    large_cycles = _strata(large, "saved_cycles_per_roundtrip")
    small_percent = _strata(small, "saved_percent")
    large_percent = _strata(large, "saved_percent")
    flatten = lambda values: [item for boot in values for item in boot]
    point_cycles = (statistics.median(flatten(large_cycles))
                    - statistics.median(flatten(small_cycles)))
    point_percent = (statistics.median(flatten(large_percent))
                     - statistics.median(flatten(small_percent)))
    rng = random.Random(0x43415041)
    cycle_draws = []
    percent_draws = []
    for _ in range(bootstrap_samples):
        cycle_draws.append(_draw(rng, large_cycles) - _draw(rng, small_cycles))
        percent_draws.append(_draw(rng, large_percent) - _draw(rng, small_percent))
    return {
        "purpose": (
            "Measure the incremental sustained benefit of a larger retained "
            "instruction prefix while allowing only NBF/count to differ."
        ),
        "common_identity": reference_identity,
        "config": reference_config,
        "small": {"configured_entries": small_count,
                  "nbf_sha256": nbf_by_capacity[small_count],
                  "replicates": [str(path) for path in small_paths],
                  "saved_cycles_per_boot": [statistics.median(boot)
                                            for boot in small_cycles]},
        "large": {"configured_entries": large_count,
                  "nbf_sha256": nbf_by_capacity[large_count],
                  "replicates": [str(path) for path in large_paths],
                  "saved_cycles_per_boot": [statistics.median(boot)
                                            for boot in large_cycles]},
        "bootstrap_samples": bootstrap_samples,
        "large_minus_small": {
            "saved_cycles_per_roundtrip": point_cycles,
            "hierarchical_95pct_ci_saved_cycles_per_roundtrip": [
                percentile(cycle_draws, 0.025), percentile(cycle_draws, 0.975)],
            "saved_percentage_points": point_percent,
            "hierarchical_95pct_ci_saved_percentage_points": [
                percentile(percent_draws, 0.025),
                percentile(percent_draws, 0.975)],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--small", nargs="+", required=True, type=Path)
    parser.add_argument("--large", nargs="+", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.small, args.large, args.bootstrap_samples)
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
