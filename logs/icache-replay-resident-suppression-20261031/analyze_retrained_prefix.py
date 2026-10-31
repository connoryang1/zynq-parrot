#!/usr/bin/env python3
"""Compare the rejected persistent-trained 16-line table with accepted controls."""

import hashlib
import json
import random
import re
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ELF_SHA = "9ba97d82db9cbd07b03e04577ca36c298c38c11dced597bc37a28aa24c3375e9"
RUNNER_SHA = "2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30"
NBF_SHA = {
    "retrained16": "b5b8fc92146a5ff30dfa5163913c4daacaa57193c5d117e178e8e7195c156518",
    "old16": "d7a2964c018f260cba7695607e0f7d86eced474e65dd57bb4ec967af16fae235",
    "disabled": "eee6fa9ff26307f7b8f0edf3cf3e2718f2a6ad2a073a11fa87aa6c27235fe716",
}
SAMPLE = re.compile(
    r"^SAMPLE=(\d+)\s+TRACE_HEADER .*?elapsed=(\d+) i_count=(\d+)"
    r" d_count=(\d+) i_overflow=(\d+) d_overflow=(\d+)",
    re.MULTILINE,
)


def load(name, arm):
    path = ROOT / "fpga" / name
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    rows = [tuple(map(int, match)) for match in SAMPLE.findall(text)]
    if [row[0] for row in rows] != list(range(1, 202)):
        raise SystemExit(f"{name}: invalid sample sequence")
    for marker in (
        f"CONTROL_PROGRAM_SHA256={RUNNER_SHA}",
        f"NBF_SHA256={NBF_SHA[arm]}",
        ELF_SHA,
        "PERSISTENT_END",
        "INFO:    CORE PASS",
        "Returning from ps_main with RC: 0",
        "INFO:    BSG PASS",
    ):
        if marker not in text:
            raise SystemExit(f"{name}: missing marker {marker!r}")
    if "TRACE_FAIL" in text:
        raise SystemExit(f"{name}: contains TRACE_FAIL")
    rows = rows[1:]
    elapsed = [row[1] for row in rows]
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "samples": len(rows),
        "discarded_warmups": 1,
        "elapsed": elapsed,
        "median": statistics.median(elapsed),
        "mean": statistics.mean(elapsed),
        "i_count_median": statistics.median(row[2] for row in rows),
        "d_count_median": statistics.median(row[3] for row in rows),
        "i_overflow_samples": sum(row[4] for row in rows),
        "quarter_medians": [
            statistics.median(elapsed[start:start + 50])
            for start in range(0, 200, 50)
        ],
    }


def bootstrap(candidate, control, seed, resamples=100_000):
    rng = random.Random(seed)
    differences = []
    for _ in range(resamples):
        replicate_differences = []
        for index in range(2):
            candidate_sample = rng.choices(candidate[index]["elapsed"], k=200)
            control_sample = rng.choices(control[index]["elapsed"], k=200)
            replicate_differences.append(
                statistics.median(candidate_sample)
                - statistics.median(control_sample)
            )
        differences.append(statistics.mean(replicate_differences))
    differences.sort()
    return {
        "resamples": resamples,
        "difference_ci95": [differences[2_500], differences[97_499]],
        "fraction_candidate_faster": (
            sum(value < 0 for value in differences) / resamples
        ),
    }


retrained = [
    load("retrained16-persistent201.log", "retrained16"),
    load("retrained16-persistent201-r2.log", "retrained16"),
]
old = [
    load("prefix16-persistent201.log", "old16"),
    load("prefix16-persistent201-r2.log", "old16"),
]
disabled = [
    load("disabled-persistent201.log", "disabled"),
    load("disabled-persistent201-r2.log", "disabled"),
]


def comparison(control, seed):
    point = statistics.mean(
        retrained[index]["median"] - control[index]["median"]
        for index in range(2)
    )
    return {
        "estimand": "mean of two fresh-boot candidate-minus-control median differences",
        "point_estimate": point,
        "bootstrap": bootstrap(retrained, control, seed),
    }


def pooled(arms):
    return statistics.median([
        value for arm in arms for value in arm["elapsed"]
    ])


result = {
    "purpose": (
        "Test whether replacing the old table's five unused complete-fast-path "
        "slots with the next persistent-trace lines improves the accepted old table."
    ),
    "identity": {
        "benchmark_elf_sha256": ELF_SHA,
        "retrained_shell_nbf_sha256": NBF_SHA["retrained16"],
        "opensbi_elf_sha256": "d54e6210960a424ec1389e83ce22531e7ccbae175641e52379e65b88373d3186",
        "kernel_payload_sha256": "98a0edc35455d5d2446a3e3e7efbe8d7fa8fb4499e16c22700169a126390acb8",
        "dtb_sha256": "bfa8247ae703bc96d4c8f6f14b4ca13b6553de05388dba26ba5881fb5593606f",
    },
    "retrained16": retrained,
    "old16": old,
    "disabled": disabled,
    "pooled_medians": {
        "retrained16": pooled(retrained),
        "old16": pooled(old),
        "disabled": pooled(disabled),
    },
    "retrained_minus_old16": comparison(old, 0x1601),
    "retrained_minus_disabled": comparison(disabled, 0x1602),
    "interpretation": (
        "The candidate lowers I-request count in its first boot but does not "
        "improve timing reproducibly. Keep old16; extra covered lines are not "
        "necessarily latency-critical, and fixed-table membership tuning is exhausted."
    ),
}

print(json.dumps(result, indent=2))
