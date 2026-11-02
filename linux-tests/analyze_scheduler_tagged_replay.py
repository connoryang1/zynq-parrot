#!/usr/bin/env python3
"""Validate and summarize one interleaved tagged-replay Linux board run."""

import argparse
import hashlib
import json
import random
import re
import statistics
from pathlib import Path


CONFIG = re.compile(
    r"TAGGED_REPLAY_CONFIG mode=(data|joint) lines=(\d+) slot=(\d+) "
    r"delay=(\d+) gap=(\d+) policy=(normal|fifo) lead_cycles=(\d+)"
)
ROW = re.compile(
    r"TAGGED_REPLAY trial=(\d+) enabled=(\d+) hooks=(\d+) "
    r"hook_cycles=(\d+) admitted=(\d+) filtered=(\d+) triggers=(\d+) "
    r"dropped=(\d+) wake_to_entry=(\d+) load_cycles=(\d+) "
    r"wake_to_load=(\d+) roundtrip=(\d+)"
)
METRICS = (
    "hook_cycles", "wake_to_entry", "load_cycles", "wake_to_load", "roundtrip"
)


def percentile(values, fraction):
    """Return a nearest-rank value from an already finite sample."""
    ordered = sorted(values)
    return ordered[round(fraction * (len(ordered) - 1))]


def summarize_metric(rows, metric, rng, bootstrap_samples):
    """Use balanced 0,1,1,0 blocks to suppress monotonic timing drift."""
    disabled = [row[metric] for row in rows if not row["enabled"]]
    enabled = [row[metric] for row in rows if row["enabled"]]
    blocks = []
    for start in range(0, len(rows), 4):
        block = rows[start:start + 4]
        disabled_mean = (block[0][metric] + block[3][metric]) / 2
        enabled_mean = (block[1][metric] + block[2][metric]) / 2
        blocks.append(disabled_mean - enabled_mean)
    estimate = statistics.median(blocks)
    boots = [statistics.median(rng.choices(blocks, k=len(blocks)))
             for _ in range(bootstrap_samples)]
    return {
        "disabled_median_cycles": statistics.median(disabled),
        "enabled_median_cycles": statistics.median(enabled),
        "paired_median_saved_cycles": estimate,
        "paired_95pct_ci_saved_cycles": [
            percentile(boots, 0.025), percentile(boots, 0.975)
        ],
        "disabled_range_cycles": [min(disabled), max(disabled)],
        "enabled_range_cycles": [min(enabled), max(enabled)],
    }


def analyze(path, bootstrap_samples=20000):
    """Fail closed on identities, counters, markers, and A/B trial shape."""
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    status_path = path.with_suffix(path.suffix + ".status.json")
    if not status_path.is_file():
        raise ValueError(f"missing runner status {status_path}")
    status = json.loads(status_path.read_text())
    if status.get("status") != "PASS":
        raise ValueError("runner status is not PASS")
    for key in ("nbf_sha256", "transfer_sha256", "elf_sha256",
                "control_program_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(status.get(key, ""))):
            raise ValueError(f"status lacks valid {key}")
    bitstream = status.get("bitstream_sha256")
    if bitstream is not None and not re.fullmatch(r"[0-9a-f]{64}", bitstream):
        raise ValueError("status has invalid bitstream_sha256")

    configs = CONFIG.findall(text)
    if len(configs) != 1:
        raise ValueError("expected exactly one tagged-replay configuration")
    mode, lines, slot, delay, gap, policy, lead = configs[0]
    config = {
        "mode": mode,
        "lines": int(lines),
        "slot": int(slot),
        "delay": int(delay),
        "gap": int(gap),
        "policy": policy,
        "lead_cycles": int(lead),
    }
    if config["lines"] != 32 or config["slot"] != 2:
        raise ValueError("unexpected replay footprint shape")
    for key in ("mode", "delay", "gap", "policy", "lead_cycles"):
        if status.get(key) != config[key]:
            raise ValueError(
                f"status {key}={status.get(key)!r}, expected {config[key]!r}"
            )

    required = ("TAGGED_REPLAY_CHILD PASS", "TAGGED_REPLAY_PARENT PASS", "BSG PASS")
    for marker in required:
        if marker not in text:
            raise ValueError(f"missing marker {marker!r}")
    if not re.search(r"\bCORE(?:\[0\])? PASS\b", text):
        raise ValueError("missing CORE PASS")
    for marker in ("BUG:", "Kernel panic", "Oops:", "scheduling while atomic",
                   "Segmentation fault"):
        if marker in text:
            raise ValueError(f"contains kernel failure marker {marker!r}")
    retry_markers = len(re.findall(r"^TAGGED_REPLAY_RETRY ", text, re.MULTILINE))
    retry_pass = re.findall(r"TAGGED_REPLAY_CHILD PASS retries=(\d+)", text)
    if retry_pass != [str(retry_markers)]:
        raise ValueError("retry count does not match filtered attempts")

    fields = (
        "trial", "enabled", "hooks", "hook_cycles", "admitted", "filtered",
        "triggers", "dropped", "wake_to_entry", "load_cycles", "wake_to_load",
        "roundtrip",
    )
    rows = [dict(zip(fields, map(int, match.groups()))) for match in ROW.finditer(text)]
    if len(rows) != 512 or [row["trial"] for row in rows] != list(range(512)):
        raise ValueError("expected exactly 512 ordered trials")
    for start in range(0, len(rows), 4):
        pattern = [row["enabled"] for row in rows[start:start + 4]]
        if pattern != [0, 1, 1, 0]:
            raise ValueError(f"unbalanced trial block at {start}: {pattern}")

    admitted = filtered = accepted_triggers = 0
    for index, row in enumerate(rows):
        if row["hooks"] != row["enabled"]:
            raise ValueError(f"trial {index} has invalid hook count")
        if row["wake_to_entry"] + row["load_cycles"] != row["wake_to_load"]:
            raise ValueError(f"trial {index} has inconsistent first-use timing")
        if row["wake_to_load"] > row["roundtrip"]:
            raise ValueError(f"trial {index} ends before first use")
        # PR_BP_PREVIEW_REPLAY_CONFIG sets the hardware clear bit before every
        # trial, so these are independent snapshots rather than deltas.
        if row["triggers"] != row["enabled"] or row["dropped"] != 0:
            raise ValueError(f"trial {index} has invalid trigger/drop counters")
        if row["enabled"]:
            if row["admitted"] + row["filtered"] != config["lines"]:
                raise ValueError(f"trial {index} did not complete all replay entries")
            admitted += row["admitted"]
            filtered += row["filtered"]
            accepted_triggers += row["triggers"]
        elif row["admitted"] or row["filtered"]:
            raise ValueError(f"disabled trial {index} changed replay counters")

    rng = random.Random(0x7A66ED)
    return {
        "purpose": (
            "Measure a matched Linux wakeup with one tagged 32-line data replay "
            "while validating that every enabled tag completed."
        ),
        "transcript": str(path),
        "transcript_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": str(status_path),
        "status_sha256": hashlib.sha256(status_path.read_bytes()).hexdigest(),
        "identity": {key: status.get(key) for key in (
            "nbf_sha256", "transfer_sha256", "elf_sha256",
            "control_program_sha256", "bitstream_sha256"
        )},
        "config": config,
        "trials": len(rows),
        "trials_per_arm": len(rows) // 2,
        "filtered_attempts": retry_markers,
        "counter_deltas": {
            "admitted_entries": admitted,
            "filtered_entries": filtered,
            "accepted_triggers": accepted_triggers,
            "dropped_triggers": 0,
        },
        "metrics": {
            metric: summarize_metric(rows, metric, rng, bootstrap_samples)
            for metric in METRICS
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    args = parser.parse_args()
    try:
        result = analyze(args.transcript, args.bootstrap_samples)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
