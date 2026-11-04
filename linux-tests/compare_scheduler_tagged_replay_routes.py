#!/usr/bin/env python3
"""Compare two validated tagged-replay routes with independent block resampling."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import METRICS, ROW, analyze, percentile


FIELDS = (
    "trial", "enabled", "hooks", "woken", "hook_cycles", "admitted",
    "filtered", "triggers", "dropped", "wake_to_entry", "load_cycles",
    "wake_to_load", "roundtrip",
)


def load(path):
    """Strictly validate one run and recover its balanced timing rows."""
    result = analyze(path, bootstrap_samples=1)
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    rows = [dict(zip(FIELDS, map(int, match.groups())))
            for match in ROW.finditer(text)]
    return result, rows


def block_differences(rows, metric):
    """Return disabled-minus-enabled means for each four-trial block."""
    differences = []
    for start in range(0, len(rows), 4):
        block = rows[start:start + 4]
        disabled = statistics.mean(
            row[metric] for row in block if not row["enabled"]
        )
        enabled = statistics.mean(
            row[metric] for row in block if row["enabled"]
        )
        differences.append(disabled - enabled)
    return differences


def compare(control_paths, candidate_paths, bootstrap_samples=20000):
    """Measure candidate-minus-control change across independent boot strata."""
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    if isinstance(control_paths, (str, Path)):
        control_paths = [Path(control_paths)]
    if isinstance(candidate_paths, (str, Path)):
        candidate_paths = [Path(candidate_paths)]
    if not control_paths or not candidate_paths:
        raise ValueError("each route requires at least one transcript")
    controls = [load(path) for path in control_paths]
    candidates = [load(path) for path in candidate_paths]
    reference = controls[0][0]
    for result, _rows in controls[1:] + candidates:
        if reference["config"] != result["config"]:
            raise ValueError("route configurations do not match")
    common_keys = (
        "nbf_sha256", "transfer_sha256", "elf_sha256",
        "control_program_sha256",
    )
    for result, _rows in controls[1:] + candidates:
        for key in common_keys:
            if reference["identity"][key] != result["identity"][key]:
                raise ValueError(f"route identity mismatch: {key}")
    control_bits = {
        result["identity"]["bitstream_sha256"] for result, _rows in controls
    }
    candidate_bits = {
        result["identity"]["bitstream_sha256"] for result, _rows in candidates
    }
    if len(control_bits) != 1 or len(candidate_bits) != 1:
        raise ValueError("replicates within a route must use one bitstream")
    control_bit = next(iter(control_bits))
    candidate_bit = next(iter(candidate_bits))
    if control_bit == candidate_bit:
        raise ValueError("route comparison requires distinct bitstreams")

    rng = random.Random(0x7A66ED03)
    output = {
        "purpose": (
            "Compare replay benefit across two physical routes while "
            "resampling balanced trial blocks independently."
        ),
        "config": reference["config"],
        "common_identity": {
            key: reference["identity"][key] for key in common_keys
        },
        "control": {
            "transcripts": [str(path) for path in control_paths],
            "bitstream_sha256": control_bit,
        },
        "candidate": {
            "transcripts": [str(path) for path in candidate_paths],
            "bitstream_sha256": candidate_bit,
        },
        "bootstrap_samples": bootstrap_samples,
        "metrics": {},
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
                value
                for stratum in control_strata
                for value in rng.choices(stratum, k=len(stratum))
            ]
            candidate_sample = [
                value
                for stratum in candidate_strata
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
