#!/usr/bin/env python3
"""Derive target-prediction break-even from accepted physical hint outcomes."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "logs/linux-prefetch-precision-sweep-rotate-20261003/results.json"


def main():
    source = json.loads(SOURCE.read_text())
    rows = {}
    for direction in ("to_main", "to_worker"):
        derived = source["derived"][direction]
        correct_saving = derived["comparisons"]["correct8"]["total_cycles_saved_vs_cold"]
        stale_saved = derived["comparisons"]["correct0"]["total_cycles_saved_vs_cold"]
        stale_penalty = -stale_saved
        threshold = stale_penalty / (correct_saving + stale_penalty)
        rows[direction] = {
            "correct8_total_saving_cycles": correct_saving,
            "stale8_total_penalty_cycles": stale_penalty,
            "median_break_even_target_accuracy": threshold,
            "expected_saving_at_accuracy": {
                str(p): p * correct_saving - (1.0 - p) * stale_penalty
                for p in (0.5, 0.75, 0.8, 0.9, 0.95, 0.99)
            },
        }

    result = {
        "method": (
            "For an early target prediction, a correct prediction receives the observed correct8 "
            "median total saving and a wrong prediction receives the observed correct0 median total "
            "penalty. Solve p*save-(1-p)*penalty > 0."
        ),
        "source": str(SOURCE.relative_to(ROOT)),
        "rows": rows,
        "conservative_planning_threshold": max(r["median_break_even_target_accuracy"] for r in rows.values()),
        "limits": [
            "The correct8 scheduler-inclusive saving has a bootstrap interval crossing zero, so the median threshold is a planning bound rather than repeatable end-to-end proof.",
            "This is an eight-hint same-mm experiment; hundreds of wrong full-line replays can have nonlinear cache-pollution and bandwidth cost.",
            "Line accuracy within the predicted context is separate from target-context prediction accuracy.",
        ],
    }
    out = Path(__file__).with_name("results.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
