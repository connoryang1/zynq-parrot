#!/usr/bin/env python3
"""Compare late and earlier one-line joint-preview fixed-arm FPGA effects."""

import argparse
import json
from pathlib import Path

from analyze_scheduler_physical_preview_fixed_ab import ALL_METRICS
from compare_scheduler_physical_preview_fixed_ab import (
    bootstrap_difference,
    load_analysis,
    point_effect,
)


def validate_analysis(result, label, timing, mode):
    """Require the counted one-line fixed-arm shape used by this comparison."""
    if result.get("timing") != timing or result.get("mode") != mode:
        raise ValueError(
            f"{label}: expected timing={timing!r} mode={mode}"
        )
    if result.get("footprint") != "target" or result.get("lines") != 1:
        raise ValueError(f"{label}: expected one-line target-footprint analysis")
    replicates = result.get("replicates", [])
    if len(replicates) != 2 or sorted(
            run.get("order") for run in replicates) != [
                "disabled-enabled", "enabled-disabled"]:
        raise ValueError(f"{label}: expected two opposite-order replicates")
    for run in replicates:
        for arm in ("enabled", "disabled"):
            sample = run.get(arm, {})
            if sample.get("trials") != 512:
                raise ValueError(f"{label}: {arm} arm does not have 512 trials")
            for metric in ALL_METRICS:
                if len(sample.get("values", {}).get(metric, [])) != 512:
                    raise ValueError(
                        f"{label}: {arm} arm lacks 512 {metric} values"
                    )


def compare(late, early, iid_resamples=20000, block_resamples=20000):
    """Return earlier-minus-late differences in enabled-arm timing effects."""
    validate_analysis(late, "late", "wake-data", 6)
    validate_analysis(early, "early", "wake-early-data", 1)
    if late.get("group") != early.get("group"):
        raise ValueError("late and early analyses use different cache-set groups")
    for key in ("bitstream_sha256", "control_program_sha256"):
        late_value = late.get("identity", {}).get(key)
        early_value = early.get("identity", {}).get(key)
        if not late_value or late_value != early_value:
            raise ValueError(f"late and early identity {key} differs")
    if iid_resamples <= 0 or block_resamples <= 0:
        raise ValueError("bootstrap resample counts must be positive")

    output = {
        "purpose": (
            "Measure whether issuing one physical hint at scheduler selection "
            "changes the enabled-minus-disabled effect relative to the same "
            "one-line hint at the late pre-register-switch hook."
        ),
        "sign_convention": (
            "early-minus-late enabled effect; negative means earlier issue "
            "improves the endpoint relative to late issue"
        ),
        "late": {
            "timing": late["timing"],
            "identity": late["identity"],
            "analysis_path": late.get("_analysis_path"),
            "analysis_sha256": late.get("_analysis_sha256"),
        },
        "early": {
            "timing": early["timing"],
            "identity": early["identity"],
            "analysis_path": early.get("_analysis_path"),
            "analysis_sha256": early.get("_analysis_sha256"),
        },
        "group": late["group"],
        "lines": 1,
        "metrics": {},
        "interpretation_limit": (
            "The images use the same route and counted fixed-arm measurement "
            "shape, but independent fresh boots and different kernel mode "
            "immediates. This compares total runtime effects, not a paired "
            "within-boot timing intervention."
        ),
    }
    for index, metric in enumerate(ALL_METRICS):
        late_effect = point_effect(late, metric)
        early_effect = point_effect(early, metric)
        output["metrics"][metric] = {
            "late_enabled_minus_disabled": late_effect,
            "early_enabled_minus_disabled": early_effect,
            "early_minus_late": early_effect - late_effect,
            "iid_bootstrap": bootstrap_difference(
                late, early, metric, 0xEA71 + index,
                iid_resamples, 1,
            ),
            "circular_block_bootstrap": bootstrap_difference(
                late, early, metric, 0xEA81 + index,
                block_resamples, 16,
            ),
        }
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--late", required=True, type=Path)
    parser.add_argument("--early", required=True, type=Path)
    parser.add_argument("--iid-resamples", type=int, default=20000)
    parser.add_argument("--block-resamples", type=int, default=20000)
    args = parser.parse_args(argv)
    try:
        result = compare(
            load_analysis(args.late), load_analysis(args.early),
            args.iid_resamples, args.block_resamples,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
