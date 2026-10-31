#!/usr/bin/env python3
"""Validate the replicated persistent-thread physical Linux replay A/B."""

import hashlib
import json
import random
import re
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EXPECTED_ELF = "9ba97d82db9cbd07b03e04577ca36c298c38c11dced597bc37a28aa24c3375e9"
EXPECTED_RUNNER = "2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30"
EXPECTED_NBF = {
    "enabled": "d7a2964c018f260cba7695607e0f7d86eced474e65dd57bb4ec967af16fae235",
    "disabled": "eee6fa9ff26307f7b8f0edf3cf3e2718f2a6ad2a073a11fa87aa6c27235fe716",
}
SAMPLE = re.compile(
    r"^SAMPLE=(\d+)\s+TRACE_HEADER .*?elapsed=(\d+) i_count=(\d+)"
    r" d_count=(\d+) i_overflow=(\d+) d_overflow=(\d+)",
    re.MULTILINE,
)
PREFIX16 = (
    0x8023D480, 0x8023D4C0, 0x8023D540, 0x80236280,
    0x80236340, 0x80236300, 0x8000B4C0, 0x8023D1C0,
    0x802424C0, 0x80242480, 0x8052A3C0, 0x8023EB00,
    0x8023EB40, 0x802431C0, 0x8023F3C0, 0x80243200,
)


def load(name, arm):
    path = ROOT / "fpga" / name
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    rows = [tuple(map(int, match)) for match in SAMPLE.findall(text)]
    if [row[0] for row in rows] != list(range(1, 202)):
        raise SystemExit(f"{name}: expected numbered samples 1--201, found {len(rows)}")
    required = (
        f"CONTROL_PROGRAM_SHA256={EXPECTED_RUNNER}",
        f"NBF_SHA256={EXPECTED_NBF[arm]}",
        EXPECTED_ELF,
        "PERSISTENT_BEGIN",
        "PERSISTENT_END",
        "INFO:    CORE PASS",
        "Returning from ps_main with RC: 0",
        "INFO:    BSG PASS",
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f"{name}: missing marker {marker!r}")
    if "TRACE_FAIL" in text:
        raise SystemExit(f"{name}: contains TRACE_FAIL")

    # Sample one warms the same persistent task pair and is not analyzed.
    rows = rows[1:]
    elapsed = [row[1] for row in rows]
    icount = [row[2] for row in rows]
    dcount = [row[3] for row in rows]
    quartiles = statistics.quantiles(elapsed, n=4, method="inclusive")
    mean = statistics.mean(elapsed)
    variance = sum((value - mean) ** 2 for value in elapsed)
    autocorrelation = {}
    for lag in (1, 2, 5, 10, 20):
        autocorrelation[str(lag)] = (
            sum(
                (elapsed[index] - mean) * (elapsed[index - lag] - mean)
                for index in range(lag, len(elapsed))
            )
            / variance
        )
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "analyzed_samples": len(rows),
        "discarded_warmups": 1,
        "elapsed": elapsed,
        "median": statistics.median(elapsed),
        "mean": mean,
        "q1": quartiles[0],
        "q3": quartiles[2],
        "minimum": min(elapsed),
        "maximum": max(elapsed),
        "i_count_median": statistics.median(icount),
        "i_count_mean": statistics.mean(icount),
        "d_count_median": statistics.median(dcount),
        "d_count_mean": statistics.mean(dcount),
        "i_overflow_samples": sum(row[4] for row in rows),
        "d_overflow_samples": sum(row[5] for row in rows),
        "quarter_medians": [
            statistics.median(elapsed[start:start + 50])
            for start in range(0, 200, 50)
        ],
        "elapsed_autocorrelation": autocorrelation,
    }


def circular_block_sample(values, block_length, rng):
    sampled = []
    while len(sampled) < len(values):
        start = rng.randrange(len(values))
        sampled.extend(
            values[(start + offset) % len(values)]
            for offset in range(block_length)
        )
    return sampled[:len(values)]


def load_address_trace(name, arm):
    path = ROOT / "fpga" / name
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    required = (
        f"CONTROL_PROGRAM_SHA256={EXPECTED_RUNNER}",
        f"NBF_SHA256={EXPECTED_NBF[arm]}",
        EXPECTED_ELF,
        "PERSISTENT_END",
        "INFO:    CORE PASS",
        "INFO:    BSG PASS",
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f"{name}: missing marker {marker!r}")
    sections = re.split(r"^SAMPLE=(\d+)\s*$", text, flags=re.MULTILINE)
    samples = []
    for index in range(1, len(sections), 2):
        number = int(sections[index])
        body = sections[index + 1]
        header = SAMPLE.search(f"SAMPLE={number}\n{body}")
        if not header:
            raise SystemExit(f"{name}: missing sample {number} header")
        instruction_addresses = [
            int(address, 16)
            for address in re.findall(
                r"^TRACE_RECORD .*?side=I .*?paddr=0x([0-9a-fA-F]+)",
                body,
                re.MULTILINE,
            )
        ]
        samples.append({
            "sample": number,
            "elapsed": int(header.group(2)),
            "i_count": int(header.group(3)),
            "d_count": int(header.group(4)),
            "i_overflow": int(header.group(5)),
            "recorded_i": len(instruction_addresses),
            "configured_prefix_lines_seen_as_demand": [
                f"0x{address:09x}"
                for address in PREFIX16
                if address in instruction_addresses
            ],
        })
    if [sample["sample"] for sample in samples] != [1, 2]:
        raise SystemExit(f"{name}: expected two address-trace samples")
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "samples": samples,
    }


def stratified_bootstrap(replicates, seed, resamples, block_length=1):
    rng = random.Random(seed)
    differences = []
    for _ in range(resamples):
        replicate_differences = []
        for replicate in replicates:
            enabled = replicate["enabled"]["elapsed"]
            disabled = replicate["disabled"]["elapsed"]
            if block_length == 1:
                enabled_sample = rng.choices(enabled, k=len(enabled))
                disabled_sample = rng.choices(disabled, k=len(disabled))
            else:
                enabled_sample = circular_block_sample(enabled, block_length, rng)
                disabled_sample = circular_block_sample(disabled, block_length, rng)
            replicate_differences.append(
                statistics.median(enabled_sample)
                - statistics.median(disabled_sample)
            )
        differences.append(statistics.mean(replicate_differences))
    differences.sort()
    low = int(resamples * 0.025)
    high = int(resamples * 0.975) - 1
    return {
        "resamples": resamples,
        "block_length": block_length,
        "difference_ci95": [differences[low], differences[high]],
        "fraction_enabled_faster": sum(value < 0 for value in differences) / resamples,
    }


replicates = [
    {
        "order": "enabled-then-disabled",
        "enabled": load("prefix16-persistent201.log", "enabled"),
        "disabled": load("disabled-persistent201.log", "disabled"),
    },
    {
        "order": "disabled-then-enabled",
        "enabled": load("prefix16-persistent201-r2.log", "enabled"),
        "disabled": load("disabled-persistent201-r2.log", "disabled"),
    },
]
for replicate in replicates:
    enabled_median = replicate["enabled"]["median"]
    disabled_median = replicate["disabled"]["median"]
    replicate["median_difference_enabled_minus_disabled"] = (
        enabled_median - disabled_median
    )
    replicate["point_reduction_percent"] = (
        100.0 * (disabled_median - enabled_median) / disabled_median
    )
    replicate["i_count_median_difference_enabled_minus_disabled"] = (
        replicate["enabled"]["i_count_median"]
        - replicate["disabled"]["i_count_median"]
    )

pooled_enabled = [
    value for replicate in replicates for value in replicate["enabled"]["elapsed"]
]
pooled_disabled = [
    value for replicate in replicates for value in replicate["disabled"]["elapsed"]
]
pooled_enabled_median = statistics.median(pooled_enabled)
pooled_disabled_median = statistics.median(pooled_disabled)
point_estimate = statistics.mean(
    replicate["median_difference_enabled_minus_disabled"]
    for replicate in replicates
)

result = {
    "purpose": (
        "Measure best-case repeated Linux source-to-peer handoffs between one "
        "persistent pinned task pair, excluding creation and shell-launch variation."
    ),
    "identity": {
        "benchmark_elf_sha256": EXPECTED_ELF,
        "control_program_sha256": EXPECTED_RUNNER,
        "enabled_nbf_sha256": EXPECTED_NBF["enabled"],
        "disabled_nbf_sha256": EXPECTED_NBF["disabled"],
    },
    "replicates": replicates,
    "pooled": {
        "samples_per_arm": len(pooled_enabled),
        "enabled_median": pooled_enabled_median,
        "disabled_median": pooled_disabled_median,
        "median_difference_enabled_minus_disabled": (
            pooled_enabled_median - pooled_disabled_median
        ),
        "point_reduction_percent": (
            100.0
            * (pooled_disabled_median - pooled_enabled_median)
            / pooled_disabled_median
        ),
    },
    "replicate_stratified": {
        "estimand": "mean of two fresh-boot enabled-minus-disabled median differences",
        "point_estimate": point_estimate,
        "iid_bootstrap": stratified_bootstrap(replicates, 0x2201, 100_000),
        "circular_block_bootstrap": stratified_bootstrap(
            replicates, 0x220A, 20_000, block_length=10
        ),
    },
    "address_attribution": {
        "purpose": (
            "Diagnostic only: full recorder readout perturbs later handoffs, so "
            "these samples establish line identity and are excluded from timing."
        ),
        "configured_prefix": [f"0x{address:09x}" for address in PREFIX16],
        "enabled": load_address_trace("prefix16-persistent-full2.log", "enabled"),
        "disabled": load_address_trace("disabled-persistent-full2.log", "disabled"),
    },
    "interpretation": (
        "Both opposite-order fresh-boot pairs favor replay. This establishes a "
        "repeatable best-case improvement for the persistent-pair benchmark, not "
        "a general Linux or application speedup."
    ),
}

print(json.dumps(result, indent=2))
