#!/usr/bin/env python3
"""Validate opposite-order fresh-boot persistent preview A/B replicates."""

import argparse
import gzip
import hashlib
import json
import random
import re
import statistics
from pathlib import Path


SAMPLE = re.compile(
    r"^SAMPLE=(\d+)\s+TRACE_HEADER .*?elapsed=(\d+) i_count=(\d+)"
    r" d_count=(\d+) i_overflow=(\d+) d_overflow=(\d+)",
    re.MULTILINE,
)


def read_text(path):
    """Read a retained plain or gzip transcript without changing its bytes."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", errors="replace") as stream:
            return stream.read()
    return path.read_text(errors="replace")


def status_path(path):
    """Return the serialized runner status adjacent to a plain or gzip log."""
    if path.suffix == ".gz":
        path = path.with_suffix("")
    return path.with_suffix(path.suffix + ".status.json")


def load_run(path, arm, identity):
    """Validate one 201-sample run and return its 200 post-warmup rows."""
    text = read_text(path).replace("\x00", "").replace("\r", "")
    status_file = status_path(path)
    if not status_file.is_file():
        raise ValueError(f"{path}: missing runner status {status_file}")
    status = json.loads(status_file.read_text())
    expected_mode = "wake-trigger" if arm == "enabled" else "disabled"
    expected_status = {
        "status": "PASS",
        "nbf_sha256": identity["nbf_sha256"],
        "transfer_sha256": identity["transfer_sha256"],
        "elf_sha256": identity["elf_sha256"],
        "control_program_sha256": identity["control_program_sha256"],
        "window": "to-peer",
        "samples": 201,
        "program": "cache-miss",
        "cache_preview_mode": expected_mode,
        "cache_summary_only": True,
        "cache_allow_overflow": True,
        "cache_final_addresses": True,
    }
    if identity.get("bitstream_sha256") is not None:
        expected_status["bitstream_sha256"] = identity["bitstream_sha256"]
    for key, expected in expected_status.items():
        if status.get(key) != expected:
            raise ValueError(
                f"{path}: status {key}={status.get(key)!r}, expected {expected!r}"
            )
    required = (
        f"TRACE_PREVIEW mode={expected_mode} value={6 if arm == 'enabled' else 0}",
        "TRACE_CAPTURE_PASS samples=201 allow_overflow=1",
        "TRACE_FINAL_ADDRESSES ",
        "TRACE_CAPTURE_EXIT rc=0",
        "CORE PASS",
        "BSG PASS",
    )
    if identity.get("bitstream_sha256") is not None:
        required += (f"BITSTREAM_SHA256={identity['bitstream_sha256']}",)
    for marker in required:
        if marker not in text:
            raise ValueError(f"{path}: missing marker {marker!r}")
    if "TRACE_FAIL" in text:
        raise ValueError(f"{path}: contains TRACE_FAIL")
    rows = [tuple(map(int, match)) for match in SAMPLE.findall(text)]
    if [row[0] for row in rows] != list(range(1, 202)):
        raise ValueError(f"{path}: expected numbered samples 1--201")
    rows = rows[1:]
    elapsed = [row[1] for row in rows]
    icount = [row[2] for row in rows]
    dcount = [row[3] for row in rows]
    instruction_addresses = [
        int(address, 16)
        for address in re.findall(
            r"^TRACE_RECORD .*?side=I .*?paddr=0x([0-9a-fA-F]+)",
            text,
            re.MULTILINE,
        )
    ]
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
            f"0x{address:09x}"
            for address in identity["prefix_lines"]
            if address in instruction_addresses
        ],
    }


def circular_blocks(values, block_length, rng):
    """Resample one sequence using circular blocks of a fixed length."""
    sampled = []
    while len(sampled) < len(values):
        start = rng.randrange(len(values))
        sampled.extend(
            values[(start + offset) % len(values)]
            for offset in range(block_length)
        )
    return sampled[:len(values)]


def bootstrap(replicates, seed, resamples, block_length=1):
    """Bootstrap the mean of replicate-level median differences."""
    rng = random.Random(seed)
    differences = []
    for _ in range(resamples):
        replicate_differences = []
        for replicate in replicates:
            enabled = replicate["enabled"]["elapsed"]
            disabled = replicate["disabled"]["elapsed"]
            if block_length == 1:
                enabled = rng.choices(enabled, k=len(enabled))
                disabled = rng.choices(disabled, k=len(disabled))
            else:
                enabled = circular_blocks(enabled, block_length, rng)
                disabled = circular_blocks(disabled, block_length, rng)
            replicate_differences.append(
                statistics.median(enabled) - statistics.median(disabled)
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
        "fraction_enabled_faster": (
            sum(value < 0 for value in differences) / resamples
        ),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nbf-sha256", required=True)
    parser.add_argument("--transfer-sha256", required=True)
    parser.add_argument("--elf-sha256", required=True)
    parser.add_argument("--control-program-sha256", required=True)
    parser.add_argument("--bitstream-sha256")
    parser.add_argument("--prefix-json", type=Path, required=True)
    parser.add_argument(
        "--replicate", action="append", nargs=3, required=True,
        metavar=("ORDER", "ENABLED_LOG", "DISABLED_LOG"),
        help="ORDER is enabled-disabled or disabled-enabled",
    )
    parser.add_argument("--iid-resamples", type=int, default=100_000)
    parser.add_argument("--block-resamples", type=int, default=20_000)
    return parser.parse_args(argv)


def analyze(args):
    """Validate identities and calculate the persistent-pair A/B result."""
    if len(args.replicate) != 2:
        raise ValueError("exactly two opposite-order fresh-boot replicates are required")
    orders = [replicate[0] for replicate in args.replicate]
    if sorted(orders) != ["disabled-enabled", "enabled-disabled"]:
        raise ValueError("replicates must contain both opposite boot orders")
    digests = (args.nbf_sha256, args.transfer_sha256, args.elf_sha256,
               args.control_program_sha256)
    if args.bitstream_sha256 is not None:
        digests += (args.bitstream_sha256,)
    for digest in digests:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("identities must be 64 lowercase hex SHA-256 values")
    if args.iid_resamples <= 0 or args.block_resamples <= 0:
        raise ValueError("bootstrap resample counts must be positive")
    identity = {
        "nbf_sha256": args.nbf_sha256,
        "transfer_sha256": args.transfer_sha256,
        "elf_sha256": args.elf_sha256,
        "control_program_sha256": args.control_program_sha256,
        "bitstream_sha256": args.bitstream_sha256,
    }
    prefix = json.loads(args.prefix_json.read_text())
    try:
        identity["prefix_lines"] = [
            entry["paddr"] for entry in prefix["fixed_shared_prefix"]["lines"]
        ]
    except (KeyError, TypeError) as error:
        raise ValueError("prefix JSON lacks fixed_shared_prefix lines") from error
    if not identity["prefix_lines"]:
        raise ValueError("prefix JSON contains no lines")
    identity["prefix_json"] = str(args.prefix_json)
    identity["prefix_json_sha256"] = hashlib.sha256(
        args.prefix_json.read_bytes()
    ).hexdigest()
    replicates = []
    for order, enabled_path, disabled_path in args.replicate:
        replicate = {
            "order": order,
            "enabled": load_run(Path(enabled_path), "enabled", identity),
            "disabled": load_run(Path(disabled_path), "disabled", identity),
        }
        difference = replicate["enabled"]["median"] - replicate["disabled"]["median"]
        replicate["median_difference_enabled_minus_disabled"] = difference
        replicate["point_reduction_percent"] = (
            -100.0 * difference / replicate["disabled"]["median"]
        )
        replicates.append(replicate)
    pooled_enabled = [
        value for replicate in replicates for value in replicate["enabled"]["elapsed"]
    ]
    pooled_disabled = [
        value for replicate in replicates for value in replicate["disabled"]["elapsed"]
    ]
    enabled_median = statistics.median(pooled_enabled)
    disabled_median = statistics.median(pooled_disabled)
    point_estimate = statistics.mean(
        replicate["median_difference_enabled_minus_disabled"]
        for replicate in replicates
    )
    return {
        "purpose": (
            "Measure current mode-6 instruction replay in repeated Linux futex "
            "handoffs between one persistent pinned task pair."
        ),
        "identity": identity,
        "replicates": replicates,
        "pooled": {
            "samples_per_arm": len(pooled_enabled),
            "enabled_median": enabled_median,
            "disabled_median": disabled_median,
            "median_difference_enabled_minus_disabled": (
                enabled_median - disabled_median
            ),
            "point_reduction_percent": (
                100.0 * (disabled_median - enabled_median) / disabled_median
            ),
            "enabled_i_count_median": statistics.median(
                value for replicate in replicates
                for value in replicate["enabled"]["i_count"]
            ),
            "disabled_i_count_median": statistics.median(
                value for replicate in replicates
                for value in replicate["disabled"]["i_count"]
            ),
        },
        "replicate_stratified": {
            "estimand": "mean fresh-boot enabled-minus-disabled median difference",
            "point_estimate": point_estimate,
            "iid_bootstrap": bootstrap(
                replicates, 0x260B, args.iid_resamples
            ),
            "circular_block_bootstrap": bootstrap(
                replicates, 0x2610, args.block_resamples, block_length=10
            ),
        },
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
