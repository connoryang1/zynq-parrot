#!/usr/bin/env python3
"""Pool validated tagged-replay replications while preserving boot strata."""

import argparse
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import (
    METRICS,
    PREWAKE_ROW,
    ROW,
    analyze,
    percentile,
)


def block_effects(rows, metric):
    """Return absolute and disabled-normalized effects for each balanced block."""
    effects = []
    for start in range(0, len(rows), 4):
        block = rows[start:start + 4]
        disabled = statistics.mean(
            row[metric] for row in block if not row["enabled"]
        )
        enabled = statistics.mean(
            row[metric] for row in block if row["enabled"]
        )
        saved = disabled - enabled
        effects.append((saved, 100.0 * saved / disabled))
    return effects


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
    if result["config"]["mode"] in (
            "data-prewake-equalized", "data-prewake-equalized-quiescent",
            "joint-prewake-quiescent", "joint-preseed-quiescent"):
        prewake = [int(cycles) for _trial, cycles in PREWAKE_ROW.findall(text)]
        if len(prewake) != len(rows):
            raise ValueError("prewake row count changed after strict validation")
        for row, cycles in zip(rows, prewake):
            row["prewake_cycles"] = cycles
        if result["config"]["mode"] in (
                "data-prewake-equalized-quiescent",
                "joint-prewake-quiescent", "joint-preseed-quiescent"):
            maximum = result["config"]["prewake_max_cycles"]
            rows = [
                row
                for start in range(0, len(rows), 4)
                if all(candidate["prewake_cycles"] <= maximum
                       for candidate in rows[start:start + 4])
                for row in rows[start:start + 4]
            ]
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
    metrics = METRICS + (("prewake_cycles",)
                         if reference_config["mode"] in (
                             "data-prewake-equalized",
                             "data-prewake-equalized-quiescent",
                             "joint-prewake-quiescent",
                             "joint-preseed-quiescent",
                         )
                         else ())
    for metric in metrics:
        effects = [block_effects(rows, metric) for _result, rows in loaded]
        cycle_strata = [[effect[0] for effect in boot] for boot in effects]
        percent_strata = [[effect[1] for effect in boot] for boot in effects]
        point = statistics.median(
            value for blocks in cycle_strata for value in blocks
        )
        percent_point = statistics.median(
            value for blocks in percent_strata for value in blocks
        )
        cycle_boots = []
        percent_boots = []
        for _ in range(bootstrap_samples):
            cycle_sample = []
            percent_sample = []
            for cycle_blocks, percent_blocks in zip(
                    cycle_strata, percent_strata):
                indices = rng.choices(range(len(cycle_blocks)),
                                      k=len(cycle_blocks))
                cycle_sample.extend(cycle_blocks[index] for index in indices)
                percent_sample.extend(percent_blocks[index] for index in indices)
            cycle_boots.append(statistics.median(cycle_sample))
            percent_boots.append(statistics.median(percent_sample))
        output["metrics"][metric] = {
            "replicate_saved_cycles": [statistics.median(blocks)
                                        for blocks in cycle_strata],
            "pooled_saved_cycles": point,
            "pooled_95pct_ci_saved_cycles": [
                percentile(cycle_boots, 0.025),
                percentile(cycle_boots, 0.975),
            ],
            "replicate_saved_percent": [statistics.median(blocks)
                                         for blocks in percent_strata],
            "pooled_saved_percent": percent_point,
            "pooled_95pct_ci_saved_percent": [
                percentile(percent_boots, 0.025),
                percentile(percent_boots, 0.975),
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
