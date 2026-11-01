#!/usr/bin/env python3
"""Validate opposite-order fresh-boot comparisons of two mode-6 replay tables."""

import argparse
import hashlib
import json
import random
import re
import statistics
from pathlib import Path

from analyze_persistent_preview_ab import read_text, status_path, SAMPLE


def prefix_identity(path):
    """Load one fixed prefix policy and retain its exact content identity."""
    data = json.loads(path.read_text())
    try:
        lines = [entry["paddr"] for entry in data["fixed_shared_prefix"]["lines"]]
    except (KeyError, TypeError) as error:
        raise ValueError(f"{path}: prefix JSON lacks fixed_shared_prefix lines") from error
    if not lines or len(lines) != len(set(lines)):
        raise ValueError(f"{path}: prefix lines must be nonempty and unique")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "lines": lines,
    }


def load_run(path, arm, identity, prefix_lines):
    """Validate one mode-6 run and return its 200 post-warmup samples."""
    text = read_text(path).replace("\x00", "").replace("\r", "")
    status_file = status_path(path)
    if not status_file.is_file():
        raise ValueError(f"{path}: missing runner status {status_file}")
    status = json.loads(status_file.read_text())
    expected = {
        "status": "PASS",
        "nbf_sha256": identity[f"{arm}_nbf_sha256"],
        "transfer_sha256": identity["transfer_sha256"],
        "elf_sha256": identity["elf_sha256"],
        "control_program_sha256": identity["control_program_sha256"],
        "window": "to-peer",
        "samples": 201,
        "program": "cache-miss",
        "cache_preview_mode": "wake-trigger",
        "cache_summary_only": True,
        "cache_allow_overflow": True,
        "cache_final_addresses": True,
    }
    for key, value in expected.items():
        if status.get(key) != value:
            raise ValueError(
                f"{path}: status {key}={status.get(key)!r}, expected {value!r}"
            )
    for marker in (
        "TRACE_PREVIEW mode=wake-trigger value=6",
        "TRACE_CAPTURE_PASS samples=201 allow_overflow=1",
        "TRACE_FINAL_ADDRESSES ",
        "TRACE_CAPTURE_EXIT rc=0",
        "BSG PASS",
    ):
        if marker not in text:
            raise ValueError(f"{path}: missing marker {marker!r}")
    if not re.search(r"CORE(?:\[0\])? PASS", text):
        raise ValueError(f"{path}: missing CORE PASS marker")
    if "TRACE_FAIL" in text:
        raise ValueError(f"{path}: contains TRACE_FAIL")
    rows = [tuple(map(int, match)) for match in SAMPLE.findall(text)]
    if [row[0] for row in rows] != list(range(1, 202)):
        raise ValueError(f"{path}: expected numbered samples 1--201")
    rows = rows[1:]
    elapsed = [row[1] for row in rows]
    icount = [row[2] for row in rows]
    dcount = [row[3] for row in rows]
    instruction_addresses = {
        int(address, 16)
        for address in re.findall(
            r"^TRACE_RECORD .*?side=I .*?paddr=0x([0-9a-fA-F]+)",
            text,
            re.MULTILINE,
        )
    }
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status_path": str(status_file),
        "status_sha256": hashlib.sha256(status_file.read_bytes()).hexdigest(),
        "analyzed_samples": len(rows),
        "discarded_warmups": 1,
        "elapsed": elapsed,
        "i_count": icount,
        "d_count": dcount,
        "median": statistics.median(elapsed),
        "mean": statistics.mean(elapsed),
        "q1": statistics.quantiles(elapsed, n=4, method="inclusive")[0],
        "q3": statistics.quantiles(elapsed, n=4, method="inclusive")[2],
        "i_count_median": statistics.median(icount),
        "d_count_median": statistics.median(dcount),
        "i_overflow_samples": sum(row[4] for row in rows),
        "d_overflow_samples": sum(row[5] for row in rows),
        "quarter_medians": [
            statistics.median(elapsed[start:start + 50])
            for start in range(0, 200, 50)
        ],
        "final_recorded_instruction_lines": len(instruction_addresses),
        "configured_prefix_lines_seen_as_demand": [
            f"0x{address:09x}" for address in prefix_lines
            if address in instruction_addresses
        ],
    }


def circular_blocks(values, block_length, rng):
    """Resample one ordered sequence using circular blocks."""
    sampled = []
    while len(sampled) < len(values):
        start = rng.randrange(len(values))
        sampled.extend(
            values[(start + offset) % len(values)]
            for offset in range(block_length)
        )
    return sampled[:len(values)]


def bootstrap(replicates, seed, resamples, block_length=1):
    """Bootstrap the mean candidate-minus-current replicate median effect."""
    rng = random.Random(seed)
    differences = []
    for _ in range(resamples):
        replicate_differences = []
        for replicate in replicates:
            candidate = replicate["candidate"]["elapsed"]
            current = replicate["current"]["elapsed"]
            if block_length == 1:
                candidate = rng.choices(candidate, k=len(candidate))
                current = rng.choices(current, k=len(current))
            else:
                candidate = circular_blocks(candidate, block_length, rng)
                current = circular_blocks(current, block_length, rng)
            replicate_differences.append(
                statistics.median(candidate) - statistics.median(current)
            )
        differences.append(statistics.mean(replicate_differences))
    differences.sort()
    return {
        "resamples": resamples,
        "block_length": block_length,
        "difference_ci95": [
            differences[int(resamples * 0.025)],
            differences[int(resamples * 0.975) - 1],
        ],
        "fraction_candidate_faster": (
            sum(value < 0 for value in differences) / resamples
        ),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-nbf-sha256", required=True)
    parser.add_argument("--candidate-nbf-sha256", required=True)
    parser.add_argument("--transfer-sha256", required=True)
    parser.add_argument("--elf-sha256", required=True)
    parser.add_argument("--control-program-sha256", required=True)
    parser.add_argument("--current-prefix-json", type=Path, required=True)
    parser.add_argument("--candidate-prefix-json", type=Path, required=True)
    parser.add_argument(
        "--replicate", action="append", nargs=3, required=True,
        metavar=("ORDER", "CANDIDATE_LOG", "CURRENT_LOG"),
        help="ORDER is candidate-current or current-candidate",
    )
    parser.add_argument("--iid-resamples", type=int, default=100_000)
    parser.add_argument("--block-resamples", type=int, default=20_000)
    return parser.parse_args(argv)


def analyze(args):
    """Validate identities and calculate the table replacement effect."""
    if len(args.replicate) != 2:
        raise ValueError("exactly two opposite-order fresh-boot replicates are required")
    orders = [replicate[0] for replicate in args.replicate]
    if sorted(orders) != ["candidate-current", "current-candidate"]:
        raise ValueError("replicates must contain both opposite boot orders")
    identity = {
        "current_nbf_sha256": args.current_nbf_sha256,
        "candidate_nbf_sha256": args.candidate_nbf_sha256,
        "transfer_sha256": args.transfer_sha256,
        "elf_sha256": args.elf_sha256,
        "control_program_sha256": args.control_program_sha256,
    }
    for digest in identity.values():
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("identities must be 64 lowercase hex SHA-256 values")
    if args.iid_resamples <= 0 or args.block_resamples <= 0:
        raise ValueError("bootstrap resample counts must be positive")
    prefixes = {
        "current": prefix_identity(args.current_prefix_json),
        "candidate": prefix_identity(args.candidate_prefix_json),
    }
    replicates = []
    for order, candidate_path, current_path in args.replicate:
        replicate = {
            "order": order,
            "candidate": load_run(
                Path(candidate_path), "candidate", identity,
                prefixes["candidate"]["lines"],
            ),
            "current": load_run(
                Path(current_path), "current", identity,
                prefixes["current"]["lines"],
            ),
        }
        difference = replicate["candidate"]["median"] - replicate["current"]["median"]
        replicate["median_difference_candidate_minus_current"] = difference
        replicate["candidate_reduction_percent"] = (
            -100.0 * difference / replicate["current"]["median"]
        )
        replicates.append(replicate)
    pooled_candidate = [
        value for replicate in replicates for value in replicate["candidate"]["elapsed"]
    ]
    pooled_current = [
        value for replicate in replicates for value in replicate["current"]["elapsed"]
    ]
    candidate_median = statistics.median(pooled_candidate)
    current_median = statistics.median(pooled_current)
    point_estimate = statistics.mean(
        replicate["median_difference_candidate_minus_current"]
        for replicate in replicates
    )
    return {
        "purpose": (
            "Compare a futex-specific 16-line mode-6 replay table with the "
            "accepted current 16-line table in persistent Linux handoffs."
        ),
        "identity": identity,
        "prefixes": prefixes,
        "replicates": replicates,
        "pooled": {
            "samples_per_arm": len(pooled_candidate),
            "candidate_median": candidate_median,
            "current_median": current_median,
            "median_difference_candidate_minus_current": (
                candidate_median - current_median
            ),
            "candidate_reduction_percent": (
                100.0 * (current_median - candidate_median) / current_median
            ),
            "candidate_i_count_median": statistics.median(
                value for replicate in replicates
                for value in replicate["candidate"]["i_count"]
            ),
            "current_i_count_median": statistics.median(
                value for replicate in replicates
                for value in replicate["current"]["i_count"]
            ),
        },
        "replicate_stratified": {
            "estimand": "mean fresh-boot candidate-minus-current median difference",
            "point_estimate": point_estimate,
            "iid_bootstrap": bootstrap(replicates, 0x2611, args.iid_resamples),
            "circular_block_bootstrap": bootstrap(
                replicates, 0x2612, args.block_resamples, block_length=10
            ),
        },
        "acceptance_rule": (
            "Retain the candidate only if its replicate-level improvement over "
            "the accepted current table resolves below zero."
        ),
        "interpretation_limit": (
            "This is a persistent-pair best case, not general Linux or "
            "application throughput."
        ),
    }


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
