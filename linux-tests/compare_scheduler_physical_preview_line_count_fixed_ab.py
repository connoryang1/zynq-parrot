#!/usr/bin/env python3
"""Compare one- and four-line fixed-arm effects on one exact FPGA image."""

import argparse
import json
from pathlib import Path

from analyze_scheduler_physical_preview_fixed_ab import ALL_METRICS
from compare_scheduler_physical_preview_fixed_ab import (
    bootstrap_difference,
    load_analysis,
    point_effect,
)


def validate_analysis(result, label, lines):
    """Require the counted early-data shape used by the line-count test."""
    if result.get("timing") != "wake-early-data" or result.get("mode") != 1:
        raise ValueError(f"{label}: expected wake-early-data mode one")
    if result.get("footprint") != "target" or result.get("lines") != lines:
        raise ValueError(f"{label}: expected target footprint with lines={lines}")
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


def compare(one_line, four_line, iid_resamples=20000,
            block_resamples=20000):
    """Return four-minus-one differences in enabled-arm timing effects."""
    validate_analysis(one_line, "one-line", 1)
    validate_analysis(four_line, "four-line", 4)
    if one_line.get("group") != four_line.get("group"):
        raise ValueError("analyses use different cache-set groups")
    for key in (
            "nbf_sha256", "transfer_sha256", "elf_sha256",
            "control_program_sha256", "bitstream_sha256"):
        one_value = one_line.get("identity", {}).get(key)
        four_value = four_line.get("identity", {}).get(key)
        if not one_value or one_value != four_value:
            raise ValueError(f"line-count identity {key} differs")
    if iid_resamples <= 0 or block_resamples <= 0:
        raise ValueError("bootstrap resample counts must be positive")

    output = {
        "purpose": (
            "Measure whether using all four physical data-hint slots improves "
            "the enabled-minus-disabled effect beyond one slot on the same "
            "routed FPGA and Linux image."
        ),
        "sign_convention": (
            "four-minus-one enabled effect; negative means four lines improve "
            "the endpoint more than one line"
        ),
        "identity": one_line["identity"],
        "group": one_line["group"],
        "metrics": {},
        "interpretation_limit": (
            "The line counts use independent fresh boots. This comparison "
            "does not remove the bimodal scheduler-phase mixture seen in "
            "wake-to-entry timing."
        ),
    }
    for index, metric in enumerate(ALL_METRICS):
        one_effect = point_effect(one_line, metric)
        four_effect = point_effect(four_line, metric)
        output["metrics"][metric] = {
            "one_line_enabled_minus_disabled": one_effect,
            "four_line_enabled_minus_disabled": four_effect,
            "four_minus_one": four_effect - one_effect,
            "iid_bootstrap": bootstrap_difference(
                one_line, four_line, metric, 0x1A10 + index,
                iid_resamples, 1,
            ),
            "circular_block_bootstrap": bootstrap_difference(
                one_line, four_line, metric, 0x1A20 + index,
                block_resamples, 16,
            ),
        }
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--one-line", required=True, type=Path)
    parser.add_argument("--four-line", required=True, type=Path)
    parser.add_argument("--iid-resamples", type=int, default=20000)
    parser.add_argument("--block-resamples", type=int, default=20000)
    args = parser.parse_args(argv)
    try:
        result = compare(
            load_analysis(args.one_line), load_analysis(args.four_line),
            args.iid_resamples, args.block_resamples,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
