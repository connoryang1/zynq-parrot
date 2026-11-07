#!/usr/bin/env python3
"""Validate and summarize one sustained pipe-hint FPGA comparison."""

import argparse
import hashlib
import json
import random
import re
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import percentile


CONFIG = re.compile(
    r"^PIPE_HINT_CONFIG loops=(\d+) repeats=(\d+) warmup=(\d+) "
    r"configured_entries=(\d+)(?: policy=(continuous|seed|preseed))?"
    r"(?: sync=(pipe|futex))?$", re.MULTILINE
)
ROW = re.compile(
    r"^PIPE_HINT_RESULT repeat=(\d+) order=(\d+) enabled=([01]) "
    r"cycles=(\d+) loops=(\d+)$", re.MULTILINE
)
STATUS = re.compile(
    r"^PIPE_HINT_STATUS before=0x([0-9a-fA-F]{16}) "
    r"after=0x([0-9a-fA-F]{16}) configured_entries=(\d+) dropped=(\d+)$",
    re.MULTILINE,
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode_status(value):
    return {
        "ready": value & 1,
        "busy": (value >> 1) & 1,
        "entry_held": (value >> 2) & 1,
        "read_pending": (value >> 3) & 1,
        "configured_entries": (value >> 4) & 0x1ff,
        "next_index": (value >> 13) & 0x1ff,
        "accepted_entries": (value >> 22) & 0xffff,
        "accepted_triggers": (value >> 38) & 0xff,
        "dropped_triggers": (value >> 46) & 0xff,
        "resident_query_pending": (value >> 54) & 1,
        "resident_drops": (value >> 55) & 0x1ff,
    }


def analyze(path, bootstrap_samples=20000):
    """Fail closed on identities, order balance, controller drain, and markers."""
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    status_path = path.with_suffix(path.suffix + ".status.json")
    if not status_path.is_file():
        raise ValueError("missing runner status")
    runner = json.loads(status_path.read_text())
    if runner.get("status") != "PASS":
        raise ValueError("runner status is not PASS")
    for key in ("nbf_sha256", "transfer_sha256", "elf_sha256",
                "control_program_sha256", "bitstream_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(runner.get(key, ""))):
            raise ValueError(f"status lacks valid {key}")
    for marker in ("PIPE_HINT_PASS", "CORE PASS", "BSG PASS"):
        if marker not in text:
            raise ValueError(f"missing terminal marker {marker}")

    configs = CONFIG.findall(text)
    statuses = STATUS.findall(text)
    if len(configs) != 1 or len(statuses) != 1:
        raise ValueError("expected exactly one config and status marker")
    loops, repeats, warmup, configured = map(int, configs[0][:4])
    policy = configs[0][4] or "continuous"
    sync = configs[0][5] or "pipe"
    if loops != runner.get("loops") or repeats != runner.get("repeats"):
        raise ValueError("transcript and runner configuration differ")
    if warmup != runner.get("warmup", 32):
        raise ValueError("transcript and runner warmup differ")
    if policy != runner.get("policy", "continuous"):
        raise ValueError("transcript and runner policy differ")
    if sync != runner.get("sync", "pipe"):
        raise ValueError("transcript and runner sync differ")
    parsed = [dict(repeat=int(a), order=int(b), enabled=int(c),
                   cycles=int(d), loops=int(e)) for a, b, c, d, e in ROW.findall(text)]
    if len(parsed) != repeats * 2:
        raise ValueError("result row count does not match repeats")
    pairs = []
    for repeat in range(repeats):
        rows = [row for row in parsed if row["repeat"] == repeat]
        if len(rows) != 2 or sorted(row["order"] for row in rows) != [0, 1]:
            raise ValueError("each repeat must contain orders zero and one")
        rows.sort(key=lambda row: row["order"])
        expected_first = repeat & 1
        if [row["enabled"] for row in rows] != [expected_first, expected_first ^ 1]:
            raise ValueError("arm order does not alternate by repeat")
        if any(row["loops"] != loops or row["cycles"] <= 0 for row in rows):
            raise ValueError("invalid loop count or cycle result")
        disabled = next(row for row in rows if not row["enabled"])
        enabled = next(row for row in rows if row["enabled"])
        saved = (disabled["cycles"] - enabled["cycles"]) / loops
        pairs.append({
            "repeat": repeat,
            "enabled_order": next(row["order"] for row in rows if row["enabled"]),
            "disabled_cycles_per_roundtrip": disabled["cycles"] / loops,
            "enabled_cycles_per_roundtrip": enabled["cycles"] / loops,
            "saved_cycles_per_roundtrip": saved,
            "saved_percent": 100.0 * (disabled["cycles"] - enabled["cycles"])
                             / disabled["cycles"],
        })

    before_hex, after_hex, printed_configured, printed_dropped = statuses[0]
    before = decode_status(int(before_hex, 16))
    after = decode_status(int(after_hex, 16))
    if (configured != int(printed_configured)
            or configured != before["configured_entries"]
            or configured != after["configured_entries"]):
        raise ValueError("configured entry counts disagree")
    if any(before[key] for key in (
            "busy", "entry_held", "read_pending", "next_index",
            "accepted_entries", "accepted_triggers", "dropped_triggers",
            "resident_query_pending", "resident_drops")):
        raise ValueError("instruction-prefix baseline is not clean")
    expected_entries = min(0xffff, repeats * configured)
    if policy == "preseed":
        expected_triggers = min(0xff, repeats)
        expected_resident_drops = 0
    elif policy == "seed":
        expected_triggers = min(0xff, repeats * 2)
        expected_resident_drops = min(0x1ff, repeats * configured)
    else:
        total_triggers = repeats * 2 * (warmup + loops)
        expected_triggers = min(0xff, total_triggers)
        expected_resident_drops = min(
            0x1ff, (total_triggers - repeats) * configured)
    if (after["next_index"] != configured
            or after["accepted_entries"] != expected_entries
            or after["accepted_triggers"] != expected_triggers
            or after["resident_drops"] != expected_resident_drops
            or after["dropped_triggers"] or int(printed_dropped)
            or any(after[key] for key in (
                "busy", "entry_held", "read_pending", "resident_query_pending"))
            or not after["accepted_entries"]):
        raise ValueError("instruction-prefix replay did not drain cleanly")

    saved = [pair["saved_cycles_per_roundtrip"] for pair in pairs]
    saved_percent = [pair["saved_percent"] for pair in pairs]
    rng = random.Random(0x50495045)
    boot_saved = [statistics.median(rng.choices(saved, k=len(saved)))
                  for _ in range(bootstrap_samples)]
    boot_percent = [statistics.median(rng.choices(saved_percent, k=len(saved_percent)))
                    for _ in range(bootstrap_samples)]
    by_order = {}
    for order in (0, 1):
        values = [pair["saved_cycles_per_roundtrip"] for pair in pairs
                  if pair["enabled_order"] == order]
        by_order[str(order)] = statistics.median(values)
    return {
        "purpose": f"Measure sustained hot {sync} roundtrip throughput with matched explicit instruction hints.",
        "transcript": str(path),
        "transcript_sha256": sha256(path),
        "status": str(status_path),
        "status_sha256": sha256(status_path),
        "identity": {key: runner[key] for key in (
            "nbf_sha256", "transfer_sha256", "elf_sha256",
            "control_program_sha256", "bitstream_sha256")},
        "config": {"loops": loops, "repeats": repeats, "warmup": warmup,
                   "configured_entries": configured, "policy": policy,
                   "sync": sync},
        "pairs": pairs,
        "metrics": {
            "disabled_median_cycles_per_roundtrip": statistics.median(
                pair["disabled_cycles_per_roundtrip"] for pair in pairs),
            "enabled_median_cycles_per_roundtrip": statistics.median(
                pair["enabled_cycles_per_roundtrip"] for pair in pairs),
            "paired_median_saved_cycles_per_roundtrip": statistics.median(saved),
            "paired_95pct_ci_saved_cycles_per_roundtrip": [
                percentile(boot_saved, 0.025), percentile(boot_saved, 0.975)],
            "paired_median_saved_percent": statistics.median(saved_percent),
            "paired_95pct_ci_saved_percent": [
                percentile(boot_percent, 0.025), percentile(boot_percent, 0.975)],
            "saved_cycles_by_enabled_order": by_order,
        },
        "icache_prefix_status": {"before": before, "after": after},
        "interpretation_limits": [
            "One Linux boot supplies paired repeat blocks but not independent boot strata.",
            f"The {warmup} warmup {sync} roundtrips intentionally measure hot sustained throughput, not cold first resume.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = analyze(args.transcript, args.bootstrap_samples)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite output: {args.output}")
        args.output.write_text(rendered)
        print(f"wrote {args.output}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
