#!/usr/bin/env python3
"""Pool validated tagged-replay replications while preserving boot strata."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import METRICS, ROW, analyze, percentile


def block_differences(rows, metric):
    """Return disabled-minus-enabled means for each balanced four-row block."""
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


def load_rows(path):
    """Run the strict single-run validator, then recover its measured rows."""
    # Pooling computes its own stratified interval below. One bootstrap draw is
    # sufficient here because analyze() is used for strict structural,
    # identity, marker, and counter validation rather than its per-run CI.
    result = analyze(path, bootstrap_samples=1)
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    fields = (
        "trial", "enabled", "hooks", "woken", "hook_cycles", "admitted", "filtered",
        "triggers", "dropped", "wake_to_entry", "load_cycles",
        "wake_to_load", "roundtrip",
    )
    rows = [dict(zip(fields, map(int, match.groups())))
            for match in ROW.finditer(text)]
    return result, rows


def pool(paths, bootstrap_samples=20000):
    """Pool paired effects by resampling blocks independently within each boot."""
    if len(paths) < 2:
        raise ValueError("at least two replications are required")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    loaded = [load_rows(path) for path in paths]
    reference_config = loaded[0][0]["config"]
    if reference_config["mode"] == "off":
        raise ValueError("replay-off stability runs have no A/B effect to pool")
    reference_identity = loaded[0][0]["identity"]
    for index, (result, _rows) in enumerate(loaded[1:], start=1):
        if result["config"] != reference_config:
            raise ValueError(f"replicate {index} configuration mismatch")
        if result["identity"] != reference_identity:
            raise ValueError(f"replicate {index} identity mismatch")

    rng = random.Random(0x7A66ED02)
    output = {
        "purpose": (
            "Pool matched tagged-replay A/B replications while preserving "
            "independent-boot strata."
        ),
        "config": reference_config,
        "identity": reference_identity,
        "replicates": [str(path) for path in paths],
        "replicate_count": len(paths),
        "bootstrap_samples": bootstrap_samples,
        "metrics": {},
    }
    for metric in METRICS:
        strata = [block_differences(rows, metric) for _result, rows in loaded]
        point = statistics.median(
            value for blocks in strata for value in blocks
        )
        boots = []
        for _ in range(bootstrap_samples):
            sample = []
            for blocks in strata:
                sample.extend(rng.choices(blocks, k=len(blocks)))
            boots.append(statistics.median(sample))
        output["metrics"][metric] = {
            "replicate_saved_cycles": [statistics.median(blocks)
                                        for blocks in strata],
            "pooled_saved_cycles": point,
            "pooled_95pct_ci_saved_cycles": [
                percentile(boots, 0.025), percentile(boots, 0.975)
            ],
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", nargs="+", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    args = parser.parse_args()
    try:
        result = pool(args.transcript, args.bootstrap_samples)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
