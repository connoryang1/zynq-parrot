#!/usr/bin/env python3
"""Validate fresh-boot fixed-arm pipe replay A/B replicates."""

import argparse
import gzip
import hashlib
import json
import random
import re
import statistics
from pathlib import Path

from analyze_scheduler_physical_preview_benchmark import METRICS, ROW, percentile


CONFIG = re.compile(
    r"PHYSICAL_BENCH_CONFIG group=(\d+) first_offset=(\d+) lines=(\d+) "
    r"timing=wake-trigger mode=6 footprint=hot-proxy policy=fifo "
    r"replay_state=persistent arm=(enabled|disabled)"
)
TAIL = re.compile(
    r"PHYSICAL_BENCH_TAIL trial=(\d+) child_post_load=(\d+) "
    r"return_handoff=(\d+)"
)
ALL_METRICS = METRICS + ("child_post_load", "return_handoff")


def read_text(path):
    """Read a retained plain or deterministic-gzip transcript."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", errors="replace") as stream:
            return stream.read()
    return path.read_text(errors="replace")


def status_path(path):
    """Return the runner status beside a plain or compressed transcript."""
    if path.suffix == ".gz":
        path = path.with_suffix("")
    return path.with_suffix(path.suffix + ".status.json")


def load_run(path, arm, identity, group):
    """Validate one fixed-arm run and return its 512 timing rows."""
    text = read_text(path).replace("\x00", "").replace("\r", "")
    status_file = status_path(path)
    if not status_file.is_file():
        raise ValueError(f"{path}: missing runner status {status_file}")
    status = json.loads(status_file.read_text())
    expected_status = {
        "status": "PASS",
        "nbf_sha256": identity["nbf_sha256"],
        "transfer_sha256": identity["transfer_sha256"],
        "elf_sha256": identity["elf_sha256"],
        "control_program_sha256": identity["control_program_sha256"],
        "footprint": "hot-proxy",
        "policy": "fifo",
        "replay_state": "persistent",
        "arm": arm,
        "cells": [f"{group}:wake-trigger"],
    }
    for key, expected in expected_status.items():
        if status.get(key) != expected:
            raise ValueError(
                f"{path}: status {key}={status.get(key)!r}, expected {expected!r}"
            )
    configs = CONFIG.findall(text)
    if configs != [(str(group), str(group * 256), "4", arm)]:
        raise ValueError(f"{path}: missing or invalid fixed-arm configuration")
    required = (
        "PHYSICAL_BENCH_CHILD PASS",
        "PHYSICAL_BENCH_PARENT PASS",
        f"PHYSICAL_CELL_EXIT group={group} timing=wake-trigger rc=0",
        "BSG PASS",
    )
    for marker in required:
        if marker not in text:
            raise ValueError(f"{path}: missing marker {marker!r}")
    if not re.search(r"\bCORE(?:\[0\])? PASS\b", text):
        raise ValueError(f"{path}: missing CORE PASS")
    for marker in ("BUG:", "Kernel panic", "Oops:",
                   "scheduling while atomic", "Segmentation fault"):
        if marker in text:
            raise ValueError(f"{path}: contains kernel failure marker {marker!r}")
    retry_markers = len(re.findall(r"^PHYSICAL_BENCH_RETRY ", text, re.MULTILINE))
    retry_pass = re.findall(r"PHYSICAL_BENCH_CHILD PASS retries=(\d+)", text)
    if retry_pass != [str(retry_markers)]:
        raise ValueError(f"{path}: retry count does not match filtered attempts")

    base_rows = []
    for match in ROW.finditer(text):
        values = [int(value) for value in match.groups()]
        base_rows.append(dict(zip(("trial", "mode", "hooks") + METRICS, values)))
    tail_matches = TAIL.findall(text)
    if len(tail_matches) != 512:
        raise ValueError(f"{path}: expected exactly 512 tail timing rows")
    tails = {
        int(trial): (int(child), int(returned))
        for trial, child, returned in tail_matches
    }
    if [row["trial"] for row in base_rows] != list(range(512)):
        raise ValueError(f"{path}: expected exactly 512 ordered trials")
    expected_mode = 1 if arm == "enabled" else 0
    for row in base_rows:
        trial = row["trial"]
        if row["mode"] != expected_mode or row["hooks"] != 0:
            raise ValueError(f"{path}: trial {trial} has invalid mode/hooks")
        if trial not in tails:
            raise ValueError(f"{path}: trial {trial} lacks tail timing")
        row["child_post_load"], row["return_handoff"] = tails[trial]
        if row["wake_to_entry"] + row["load_cycles"] != row["wake_to_load"]:
            raise ValueError(f"{path}: trial {trial} has inconsistent first-use timing")
        if (row["wake_to_load"] + row["child_post_load"]
                + row["return_handoff"] != row["roundtrip"]):
            raise ValueError(f"{path}: trial {trial} has inconsistent tail timing")
    if set(tails) != set(range(512)):
        raise ValueError(f"{path}: duplicate or extra tail timing rows")
    values = {metric: [row[metric] for row in base_rows]
              for metric in ALL_METRICS}
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status_path": str(status_file),
        "status_sha256": hashlib.sha256(status_file.read_bytes()).hexdigest(),
        "trials": len(base_rows),
        "filtered_attempts": retry_markers,
        "values": values,
        "medians": {metric: statistics.median(metric_values)
                    for metric, metric_values in values.items()},
    }


def circular_blocks(values, block_length, rng):
    """Resample a time series using fixed-length circular blocks."""
    sampled = []
    while len(sampled) < len(values):
        start = rng.randrange(len(values))
        sampled.extend(values[(start + offset) % len(values)]
                       for offset in range(block_length))
    return sampled[:len(values)]


def bootstrap(replicates, metric, seed, resamples, block_length=1):
    """Bootstrap the mean fresh-boot enabled-minus-disabled median."""
    rng = random.Random(seed)
    differences = []
    for _ in range(resamples):
        replicate_differences = []
        for replicate in replicates:
            enabled = replicate["enabled"]["values"][metric]
            disabled = replicate["disabled"]["values"][metric]
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
    parser.add_argument("--group", type=int, choices=range(8), default=7)
    parser.add_argument("--replicate", action="append", nargs=3, required=True,
                        metavar=("ORDER", "ENABLED_LOG", "DISABLED_LOG"))
    parser.add_argument("--iid-resamples", type=int, default=100_000)
    parser.add_argument("--block-resamples", type=int, default=20_000)
    return parser.parse_args(argv)


def analyze(args):
    """Validate identities and calculate all fixed-arm timing effects."""
    if len(args.replicate) != 2:
        raise ValueError("exactly two opposite-order fresh-boot replicates are required")
    orders = [replicate[0] for replicate in args.replicate]
    if sorted(orders) != ["disabled-enabled", "enabled-disabled"]:
        raise ValueError("replicates must contain both opposite boot orders")
    identity = {
        "nbf_sha256": args.nbf_sha256,
        "transfer_sha256": args.transfer_sha256,
        "elf_sha256": args.elf_sha256,
        "control_program_sha256": args.control_program_sha256,
    }
    for digest in identity.values():
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("identities must be 64 lowercase hex SHA-256 values")
    if args.iid_resamples <= 0 or args.block_resamples <= 0:
        raise ValueError("bootstrap resample counts must be positive")
    replicates = []
    for order, enabled_path, disabled_path in args.replicate:
        replicate = {
            "order": order,
            "enabled": load_run(Path(enabled_path), "enabled", identity, args.group),
            "disabled": load_run(Path(disabled_path), "disabled", identity, args.group),
        }
        replicate["median_difference_enabled_minus_disabled"] = {
            metric: replicate["enabled"]["medians"][metric]
            - replicate["disabled"]["medians"][metric]
            for metric in ALL_METRICS
        }
        replicates.append(replicate)

    output = {
        "purpose": (
            "Measure persistent instruction replay on a fixed-arm Linux FIFO "
            "pipe handoff without retained-state leakage between A/B arms."
        ),
        "identity": identity,
        "group": args.group,
        "replicates": replicates,
        "metrics": {},
        "interpretation_limit": (
            "This is one synthetic persistent pipe pair with hot proxy data "
            "hints, not general application throughput."
        ),
    }
    for index, metric in enumerate(ALL_METRICS):
        enabled = [value for replicate in replicates
                   for value in replicate["enabled"]["values"][metric]]
        disabled = [value for replicate in replicates
                    for value in replicate["disabled"]["values"][metric]]
        point = statistics.mean(
            replicate["median_difference_enabled_minus_disabled"][metric]
            for replicate in replicates
        )
        output["metrics"][metric] = {
            "pooled_enabled_median": statistics.median(enabled),
            "pooled_disabled_median": statistics.median(disabled),
            "pooled_median_difference_enabled_minus_disabled": (
                statistics.median(enabled) - statistics.median(disabled)
            ),
            "replicate_stratified_point_estimate": point,
            "iid_bootstrap": bootstrap(
                replicates, metric, 0xB50A + index, args.iid_resamples
            ),
            "circular_block_bootstrap": bootstrap(
                replicates, metric, 0xB50B + index,
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
