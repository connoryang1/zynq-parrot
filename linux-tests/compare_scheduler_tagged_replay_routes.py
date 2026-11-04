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


def compare(control_path, candidate_path, bootstrap_samples=20000):
    """Measure candidate-minus-control change in paired replay benefit."""
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    control, control_rows = load(control_path)
    candidate, candidate_rows = load(candidate_path)
    if control["config"] != candidate["config"]:
        raise ValueError("route configurations do not match")
    common_keys = (
        "nbf_sha256", "transfer_sha256", "elf_sha256",
        "control_program_sha256",
    )
    for key in common_keys:
        if control["identity"][key] != candidate["identity"][key]:
            raise ValueError(f"route identity mismatch: {key}")
    control_bit = control["identity"]["bitstream_sha256"]
    candidate_bit = candidate["identity"]["bitstream_sha256"]
    if control_bit == candidate_bit:
        raise ValueError("route comparison requires distinct bitstreams")

    rng = random.Random(0x7A66ED03)
    output = {
        "purpose": (
            "Compare replay benefit across two physical routes while "
            "resampling balanced trial blocks independently."
        ),
        "config": control["config"],
        "common_identity": {
            key: control["identity"][key] for key in common_keys
        },
        "control": {
            "transcript": str(control_path),
            "bitstream_sha256": control_bit,
        },
        "candidate": {
            "transcript": str(candidate_path),
            "bitstream_sha256": candidate_bit,
        },
        "bootstrap_samples": bootstrap_samples,
        "metrics": {},
    }
    for metric in METRICS:
        control_blocks = block_differences(control_rows, metric)
        candidate_blocks = block_differences(candidate_rows, metric)
        control_point = statistics.median(control_blocks)
        candidate_point = statistics.median(candidate_blocks)
        boots = []
        for _ in range(bootstrap_samples):
            control_sample = rng.choices(control_blocks, k=len(control_blocks))
            candidate_sample = rng.choices(candidate_blocks, k=len(candidate_blocks))
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
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    args = parser.parse_args()
    try:
        result = compare(args.control, args.candidate, args.bootstrap_samples)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
