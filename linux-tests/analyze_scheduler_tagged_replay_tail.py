#!/usr/bin/env python3
"""Validate and pool post-first-use partitions from tagged-replay runs."""

import argparse
import json
import random
import re
import statistics
from pathlib import Path

from analyze_scheduler_tagged_replay import ROW, analyze, percentile


TAIL_ROW = re.compile(
    r"^TAGGED_REPLAY_TAIL trial=(\d+) enabled=(\d+) "
    r"child_post_load=(\d+) return_handoff=(\d+) post_load_total=(\d+)$",
    re.MULTILINE,
)
TAIL_METRICS = ("child_post_load", "return_handoff", "post_load_total")


def load(path):
    """Apply the primary validator, then require exact tail identities."""
    result = analyze(path, bootstrap_samples=1)
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    base_fields = (
        "trial", "enabled", "hooks", "woken", "hook_cycles", "admitted",
        "filtered", "triggers", "dropped", "wake_to_entry", "load_cycles",
        "wake_to_load", "roundtrip",
    )
    base_rows = [dict(zip(base_fields, map(int, match.groups())))
                 for match in ROW.finditer(text)]
    tail_fields = (
        "trial", "enabled", "child_post_load", "return_handoff",
        "post_load_total",
    )
    tails = [dict(zip(tail_fields, map(int, match.groups())))
             for match in TAIL_ROW.finditer(text)]
    if len(tails) != 512 or [row["trial"] for row in tails] != list(range(512)):
        raise ValueError("expected exactly 512 ordered tagged-replay tail rows")
    for base, tail in zip(base_rows, tails):
        if (tail["trial"], tail["enabled"]) != (base["trial"], base["enabled"]):
            raise ValueError(f"tail arm mismatch at trial {base['trial']}")
        if tail["child_post_load"] + tail["return_handoff"] != tail["post_load_total"]:
            raise ValueError(f"tail partition mismatch at trial {base['trial']}")
        if base["wake_to_load"] + tail["post_load_total"] != base["roundtrip"]:
            raise ValueError(f"tail endpoint mismatch at trial {base['trial']}")
    return result, tails


def block_effects(rows, metric):
    """Return disabled-minus-enabled effects for balanced four-trial blocks."""
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


def pool(paths, bootstrap_samples=20000):
    """Pool tail effects while preserving independent-boot strata."""
    if not paths:
        raise ValueError("at least one transcript is required")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    loaded = [load(path) for path in paths]
    reference_config = loaded[0][0]["config"]
    reference_identity = loaded[0][0]["identity"]
    for index, (result, _rows) in enumerate(loaded[1:], start=1):
        if result["config"] != reference_config:
            raise ValueError(f"replicate {index} configuration mismatch")
        if result["identity"] != reference_identity:
            raise ValueError(f"replicate {index} identity mismatch")
    rng = random.Random(0x7A66ED05)
    output = {
        "purpose": (
            "Partition the post-first-use tail into accepted child bookkeeping "
            "and the child-to-parent return handoff without changing timed code."
        ),
        "config": reference_config,
        "identity": reference_identity,
        "replicates": [str(path) for path in paths],
        "replicate_count": len(paths),
        "bootstrap_samples": bootstrap_samples,
        "metrics": {},
    }
    for metric in TAIL_METRICS:
        effects = [block_effects(rows, metric) for _result, rows in loaded]
        cycle_strata = [[effect[0] for effect in boot] for boot in effects]
        percent_strata = [[effect[1] for effect in boot] for boot in effects]
        cycle_samples = []
        percent_samples = []
        for _ in range(bootstrap_samples):
            sampled_cycles = []
            sampled_percent = []
            for cycles, percents in zip(cycle_strata, percent_strata):
                indices = rng.choices(range(len(cycles)), k=len(cycles))
                sampled_cycles.extend(cycles[index] for index in indices)
                sampled_percent.extend(percents[index] for index in indices)
            cycle_samples.append(statistics.median(sampled_cycles))
            percent_samples.append(statistics.median(sampled_percent))
        output["metrics"][metric] = {
            "replicate_saved_cycles": [statistics.median(values)
                                        for values in cycle_strata],
            "pooled_saved_cycles": statistics.median(
                value for values in cycle_strata for value in values
            ),
            "pooled_95pct_ci_saved_cycles": [
                percentile(cycle_samples, 0.025), percentile(cycle_samples, 0.975)
            ],
            "replicate_saved_percent": [statistics.median(values)
                                         for values in percent_strata],
            "pooled_saved_percent": statistics.median(
                value for values in percent_strata for value in values
            ),
            "pooled_95pct_ci_saved_percent": [
                percentile(percent_samples, 0.025),
                percentile(percent_samples, 0.975),
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
