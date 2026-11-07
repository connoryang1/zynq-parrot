#!/usr/bin/env python3
"""Compare post-first-use tail effects across two instruction-prefix images."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import percentile
from analyze_scheduler_tagged_replay_tail import (
    TAIL_METRICS, block_effects, load,
)


def compare(control_paths, candidate_paths, bootstrap_samples=20000):
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
        if result["config"] != reference["config"]:
            raise ValueError("tail prefix configurations do not match")
    if reference["config"]["mode"] != "instruction-explicit-roundtrip":
        raise ValueError("tail prefix comparison requires explicit roundtrip mode")

    same_keys = (
        "transfer_sha256", "elf_sha256", "control_program_sha256",
        "bitstream_sha256",
    )
    for result, _rows in controls[1:] + candidates:
        for key in same_keys:
            if reference["identity"][key] != result["identity"][key]:
                raise ValueError(f"tail prefix identity mismatch: {key}")

    def one_value(loaded, identity_key=None, count=False):
        if count:
            values = {
                result["icache_prefix_status"]["before"]["configured_entries"]
                for result, _rows in loaded
            }
        else:
            values = {result["identity"][identity_key]
                      for result, _rows in loaded}
        if len(values) != 1:
            raise ValueError("replicates within a tail prefix image mismatch")
        return next(iter(values))

    control_nbf = one_value(controls, "nbf_sha256")
    candidate_nbf = one_value(candidates, "nbf_sha256")
    control_count = one_value(controls, count=True)
    candidate_count = one_value(candidates, count=True)
    if control_nbf == candidate_nbf or control_count == candidate_count:
        raise ValueError("tail prefix comparison requires distinct images and counts")

    output = {
        "purpose": (
            "Compare post-first-use tail A/B effects across prefix images "
            "while preserving independent boot strata."
        ),
        "config": reference["config"],
        "common_identity": {
            key: reference["identity"][key] for key in same_keys
        },
        "control": {
            "transcripts": [str(path) for path in control_paths],
            "nbf_sha256": control_nbf,
            "configured_entries": control_count,
        },
        "candidate": {
            "transcripts": [str(path) for path in candidate_paths],
            "nbf_sha256": candidate_nbf,
            "configured_entries": candidate_count,
        },
        "bootstrap_samples": bootstrap_samples,
        "metrics": {},
        "interpretation_limits": [
            "Boot strata are resampled independently within each prefix image.",
            "The instrumented ELF is identical across images but differs from "
            "the uninstrumented accepted first-use benchmark.",
        ],
    }
    rng = random.Random(0x7A66ED06)
    for metric in TAIL_METRICS:
        control_strata = [
            [effect[0] for effect in block_effects(rows, metric)]
            for _result, rows in controls
        ]
        candidate_strata = [
            [effect[0] for effect in block_effects(rows, metric)]
            for _result, rows in candidates
        ]
        control_point = statistics.median(
            value for stratum in control_strata for value in stratum
        )
        candidate_point = statistics.median(
            value for stratum in candidate_strata for value in stratum
        )
        samples = []
        for _ in range(bootstrap_samples):
            control_sample = [
                value for stratum in control_strata
                for value in rng.choices(stratum, k=len(stratum))
            ]
            candidate_sample = [
                value for stratum in candidate_strata
                for value in rng.choices(stratum, k=len(stratum))
            ]
            samples.append(
                statistics.median(candidate_sample)
                - statistics.median(control_sample)
            )
        output["metrics"][metric] = {
            "control_saved_cycles": control_point,
            "candidate_saved_cycles": candidate_point,
            "candidate_incremental_saved_cycles": (
                candidate_point - control_point
            ),
            "candidate_incremental_95pct_ci_saved_cycles": [
                percentile(samples, 0.025), percentile(samples, 0.975)
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
