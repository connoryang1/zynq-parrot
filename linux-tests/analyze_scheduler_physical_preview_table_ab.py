#!/usr/bin/env python3
"""Validate opposite-order fixed-arm pipe replay table comparisons."""

import argparse
import json
import re
import statistics
from pathlib import Path

from analyze_scheduler_physical_preview_fixed_ab import (
    ALL_METRICS,
    bootstrap,
    load_run,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-nbf-sha256", required=True)
    parser.add_argument("--candidate-nbf-sha256", required=True)
    parser.add_argument("--transfer-sha256", required=True)
    parser.add_argument("--elf-sha256", required=True)
    parser.add_argument("--control-program-sha256", required=True)
    parser.add_argument("--group", type=int, choices=range(8), default=7)
    parser.add_argument("--replicate", action="append", nargs=3, required=True,
                        metavar=("ORDER", "CURRENT_LOG", "CANDIDATE_LOG"))
    parser.add_argument("--iid-resamples", type=int, default=100_000)
    parser.add_argument("--block-resamples", type=int, default=20_000)
    return parser.parse_args(argv)


def analyze(args):
    """Validate table identities and calculate candidate-minus-current effects."""
    if len(args.replicate) != 2:
        raise ValueError("exactly two opposite-order fresh-boot replicates are required")
    orders = [replicate[0] for replicate in args.replicate]
    if sorted(orders) != ["candidate-current", "current-candidate"]:
        raise ValueError("replicates must contain both opposite boot orders")
    common = {
        "transfer_sha256": args.transfer_sha256,
        "elf_sha256": args.elf_sha256,
        "control_program_sha256": args.control_program_sha256,
    }
    current_identity = {"nbf_sha256": args.current_nbf_sha256, **common}
    candidate_identity = {"nbf_sha256": args.candidate_nbf_sha256, **common}
    for digest in (*current_identity.values(), args.candidate_nbf_sha256):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("identities must be 64 lowercase hex SHA-256 values")
    if args.current_nbf_sha256 == args.candidate_nbf_sha256:
        raise ValueError("current and candidate NBF identities must differ")
    if args.iid_resamples <= 0 or args.block_resamples <= 0:
        raise ValueError("bootstrap resample counts must be positive")

    replicates = []
    bootstrap_replicates = []
    for order, current_path, candidate_path in args.replicate:
        replicate = {
            "order": order,
            "current": load_run(
                Path(current_path), "enabled", current_identity, args.group
            ),
            "candidate": load_run(
                Path(candidate_path), "enabled", candidate_identity, args.group
            ),
        }
        replicate["median_difference_candidate_minus_current"] = {
            metric: replicate["candidate"]["medians"][metric]
            - replicate["current"]["medians"][metric]
            for metric in ALL_METRICS
        }
        replicates.append(replicate)
        bootstrap_replicates.append({
            "enabled": replicate["candidate"],
            "disabled": replicate["current"],
        })

    output = {
        "purpose": (
            "Measure whether the accepted futex-specific v1 table transfers "
            "to the persistent Linux FIFO pipe handoff."
        ),
        "identity": {
            "current_nbf_sha256": args.current_nbf_sha256,
            "candidate_nbf_sha256": args.candidate_nbf_sha256,
            **common,
        },
        "group": args.group,
        "replicates": replicates,
        "metrics": {},
        "interpretation_limit": (
            "This compares fixed table contents on one synthetic persistent "
            "pipe pair; it is not a general training-policy evaluation."
        ),
    }
    for index, metric in enumerate(ALL_METRICS):
        candidate = [value for replicate in replicates
                     for value in replicate["candidate"]["values"][metric]]
        current = [value for replicate in replicates
                   for value in replicate["current"]["values"][metric]]
        point = statistics.mean(
            replicate["median_difference_candidate_minus_current"][metric]
            for replicate in replicates
        )
        output["metrics"][metric] = {
            "pooled_candidate_median": statistics.median(candidate),
            "pooled_current_median": statistics.median(current),
            "pooled_median_difference_candidate_minus_current": (
                statistics.median(candidate) - statistics.median(current)
            ),
            "replicate_stratified_point_estimate": point,
            "iid_bootstrap": bootstrap(
                bootstrap_replicates, metric, 0x7AB1 + index,
                args.iid_resamples
            ),
            "circular_block_bootstrap": bootstrap(
                bootstrap_replicates, metric, 0x7AB2 + index,
                args.block_resamples, block_length=16
            ),
        }
    return output


def main(argv=None):
    args = parse_args(argv)
    try:
        result = analyze(args)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
