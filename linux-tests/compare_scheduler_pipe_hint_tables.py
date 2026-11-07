#!/usr/bin/env python3
"""Compare equal-capacity preseed pipe-prefix tables across boots."""

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


def compare(baseline_paths, candidate_paths, bootstrap_samples=20000):
    """Return candidate-minus-baseline effect with NBF as the only change."""
    if len(baseline_paths) < 2 or len(candidate_paths) < 2:
        raise ValueError("each table requires at least two independent boots")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    baseline = _load(baseline_paths)
    candidate = _load(candidate_paths)
    config = baseline[0]["config"]
    common_identity = {key: value for key, value in baseline[0]["identity"].items()
                       if key != "nbf_sha256"}
    nbfs = {}
    for label, results in (("baseline", baseline), ("candidate", candidate)):
        for index, result in enumerate(results):
            if result["config"] != config:
                raise ValueError(f"{label} replicate {index} configuration mismatch")
            identity = {key: value for key, value in result["identity"].items()
                        if key != "nbf_sha256"}
            if identity != common_identity:
                raise ValueError(f"{label} replicate {index} identity mismatch")
            prior = nbfs.setdefault(label, result["identity"]["nbf_sha256"])
            if result["identity"]["nbf_sha256"] != prior:
                raise ValueError(f"{label} replicate {index} NBF mismatch")
    if nbfs["baseline"] == nbfs["candidate"]:
        raise ValueError("table arms unexpectedly use the same NBF")

    baseline_cycles = _strata(baseline, "saved_cycles_per_roundtrip")
    candidate_cycles = _strata(candidate, "saved_cycles_per_roundtrip")
    baseline_percent = _strata(baseline, "saved_percent")
    candidate_percent = _strata(candidate, "saved_percent")
    flatten = lambda values: [item for boot in values for item in boot]
    point_cycles = (statistics.median(flatten(candidate_cycles))
                    - statistics.median(flatten(baseline_cycles)))
    point_percent = (statistics.median(flatten(candidate_percent))
                     - statistics.median(flatten(baseline_percent)))
    rng = random.Random(0x5441424C)
    cycle_draws = []
    percent_draws = []
    for _ in range(bootstrap_samples):
        cycle_draws.append(_draw(rng, candidate_cycles)
                           - _draw(rng, baseline_cycles))
        percent_draws.append(_draw(rng, candidate_percent)
                             - _draw(rng, baseline_percent))
    return {
        "purpose": (
            "Measure the incremental sustained effect of an equal-capacity "
            "retained instruction table while allowing only NBF to differ."
        ),
        "config": config,
        "common_identity": common_identity,
        "baseline": {"nbf_sha256": nbfs["baseline"],
                     "replicates": [str(path) for path in baseline_paths],
                     "saved_cycles_per_boot": [statistics.median(boot)
                                               for boot in baseline_cycles]},
        "candidate": {"nbf_sha256": nbfs["candidate"],
                      "replicates": [str(path) for path in candidate_paths],
                      "saved_cycles_per_boot": [statistics.median(boot)
                                                for boot in candidate_cycles]},
        "bootstrap_samples": bootstrap_samples,
        "candidate_minus_baseline": {
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
    parser.add_argument("--baseline", nargs="+", required=True, type=Path)
    parser.add_argument("--candidate", nargs="+", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.baseline, args.candidate, args.bootstrap_samples)
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
