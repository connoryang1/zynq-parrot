#!/usr/bin/env python3
"""Compare replay benefit across two instruction-prefix images."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import METRICS, percentile
from compare_scheduler_tagged_replay_routes import block_differences, load


def compare(control_paths, candidate_paths, bootstrap_samples=20000):
    """Measure candidate-minus-control A/B effect with independent blocks."""
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    if isinstance(control_paths, (str, Path)):
        control_paths = [Path(control_paths)]
    if isinstance(candidate_paths, (str, Path)):
        candidate_paths = [Path(candidate_paths)]
    if not control_paths or not candidate_paths:
        raise ValueError("each prefix image requires at least one transcript")
    controls = [load(path) for path in control_paths]
    candidates = [load(path) for path in candidate_paths]
    reference = controls[0][0]
    for result, _rows in controls[1:] + candidates:
        if reference["config"] != result["config"]:
            raise ValueError("prefix-image configurations do not match")
    if reference["config"]["mode"] != "instruction-wake":
        raise ValueError("prefix-image comparison requires instruction-wake mode")

    same_keys = (
        "transfer_sha256", "elf_sha256", "control_program_sha256",
        "bitstream_sha256",
    )
    for result, _rows in controls[1:] + candidates:
        for key in same_keys:
            if reference["identity"][key] != result["identity"][key]:
                raise ValueError(f"prefix-image identity mismatch: {key}")

    control_nbfs = {
        result["identity"]["nbf_sha256"] for result, _rows in controls
    }
    candidate_nbfs = {
        result["identity"]["nbf_sha256"] for result, _rows in candidates
    }
    if len(control_nbfs) != 1 or len(candidate_nbfs) != 1:
        raise ValueError("replicates within a prefix image must use one NBF")
    control_nbf = next(iter(control_nbfs))
    candidate_nbf = next(iter(candidate_nbfs))
    if control_nbf == candidate_nbf:
        raise ValueError("prefix-image comparison requires distinct NBFs")

    control_counts = {
        result["icache_prefix_status"]["before"]["configured_entries"]
        for result, _rows in controls
    }
    candidate_counts = {
        result["icache_prefix_status"]["before"]["configured_entries"]
        for result, _rows in candidates
    }
    if len(control_counts) != 1 or len(candidate_counts) != 1:
        raise ValueError("replicates within a prefix image must use one count")
    control_count = next(iter(control_counts))
    candidate_count = next(iter(candidate_counts))
    if control_count == candidate_count:
        raise ValueError("prefix-image comparison requires distinct prefix counts")

    rng = random.Random(0x7A66ED04)
    output = {
        "purpose": (
            "Compare the within-boot instruction-replay A/B effect across two "
            "NBFs while holding bitstream, benchmark, transfer, and workload fixed."
        ),
        "config": reference["config"],
        "common_identity": {
            key: reference["identity"][key] for key in same_keys
        },
        "control": {
            "transcripts": [str(path) for path in control_paths],
            "nbf_sha256": control_nbf,
            "configured_entries": control_count,
            "filtered_attempts": [result["filtered_attempts"]
                                  for result, _rows in controls],
        },
        "candidate": {
            "transcripts": [str(path) for path in candidate_paths],
            "nbf_sha256": candidate_nbf,
            "configured_entries": candidate_count,
            "filtered_attempts": [result["filtered_attempts"]
                                  for result, _rows in candidates],
        },
        "bootstrap_samples": bootstrap_samples,
        "metrics": {},
        "interpretation_limits": [
            "Boot strata are resampled independently within each prefix image.",
            "Large filtered-wake counts limit this to mechanism-quality evidence.",
        ],
    }
    for metric in METRICS:
        control_strata = [
            block_differences(rows, metric) for _result, rows in controls
        ]
        candidate_strata = [
            block_differences(rows, metric) for _result, rows in candidates
        ]
        control_blocks = [value for stratum in control_strata for value in stratum]
        candidate_blocks = [value for stratum in candidate_strata for value in stratum]
        control_point = statistics.median(control_blocks)
        candidate_point = statistics.median(candidate_blocks)
        boots = []
        for _ in range(bootstrap_samples):
            control_sample = [
                value for stratum in control_strata
                for value in rng.choices(stratum, k=len(stratum))
            ]
            candidate_sample = [
                value for stratum in candidate_strata
                for value in rng.choices(stratum, k=len(stratum))
            ]
            boots.append(
                statistics.median(candidate_sample)
                - statistics.median(control_sample)
            )
        output["metrics"][metric] = {
            "control_saved_cycles": control_point,
            "candidate_saved_cycles": candidate_point,
            "candidate_incremental_saved_cycles": candidate_point - control_point,
            "candidate_incremental_95pct_ci_saved_cycles": [
                percentile(boots, 0.025), percentile(boots, 0.975)
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
