#!/usr/bin/env python3
"""Compare joint wake/data and instruction-only fixed-arm FPGA effects."""

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

from analyze_scheduler_physical_preview_fixed_ab import circular_blocks


COMPARABLE_METRICS = ("wake_to_entry", "load_cycles", "wake_to_load")


def load_analysis(path):
    """Load one strict fixed-arm analysis and retain its file identity."""
    raw = path.read_bytes()
    result = json.loads(raw)
    result["_analysis_path"] = str(path)
    result["_analysis_sha256"] = hashlib.sha256(raw).hexdigest()
    return result


def validate_analysis(result, label, timing):
    """Require the fixed-arm shape needed for an effect comparison."""
    if result.get("timing") != timing:
        raise ValueError(
            f"{label}: timing={result.get('timing')!r}, expected {timing!r}"
        )
    if result.get("mode") != 6 or result.get("footprint") != "target":
        raise ValueError(f"{label}: expected mode-six target-footprint analysis")
    replicates = result.get("replicates", [])
    if len(replicates) != 2:
        raise ValueError(f"{label}: expected exactly two replicates")
    if sorted(run.get("order") for run in replicates) != [
            "disabled-enabled", "enabled-disabled"]:
        raise ValueError(f"{label}: missing opposite boot orders")
    for run in replicates:
        for arm in ("enabled", "disabled"):
            sample = run.get(arm, {})
            if sample.get("trials") != 512:
                raise ValueError(f"{label}: {arm} arm does not have 512 trials")
            values = sample.get("values", {})
            for metric in COMPARABLE_METRICS:
                if len(values.get(metric, [])) != 512:
                    raise ValueError(
                        f"{label}: {arm} arm lacks 512 {metric} values"
                    )


def resampled_effect(replicates, metric, rng, block_length):
    """Resample arms within each boot and return mean enabled-minus-disabled."""
    differences = []
    for run in replicates:
        enabled = run["enabled"]["values"][metric]
        disabled = run["disabled"]["values"][metric]
        if block_length == 1:
            enabled = rng.choices(enabled, k=len(enabled))
            disabled = rng.choices(disabled, k=len(disabled))
        else:
            enabled = circular_blocks(enabled, block_length, rng)
            disabled = circular_blocks(disabled, block_length, rng)
        differences.append(
            statistics.median(enabled) - statistics.median(disabled)
        )
    return statistics.mean(differences)


def bootstrap_difference(control, candidate, metric, seed, resamples,
                         block_length):
    """Bootstrap candidate-minus-control enabled effects independently."""
    rng = random.Random(seed)
    differences = []
    for _ in range(resamples):
        control_effect = resampled_effect(
            control["replicates"], metric, rng, block_length
        )
        candidate_effect = resampled_effect(
            candidate["replicates"], metric, rng, block_length
        )
        differences.append(candidate_effect - control_effect)
    differences.sort()
    return {
        "resamples": resamples,
        "block_length": block_length,
        "difference_ci95": [
            differences[int(resamples * 0.025)],
            differences[int(resamples * 0.975) - 1],
        ],
        "fraction_candidate_effect_faster": (
            sum(value < 0 for value in differences) / resamples
        ),
    }


def point_effect(result, metric):
    """Return the mean per-boot enabled-minus-disabled median."""
    return statistics.mean(
        run["median_difference_enabled_minus_disabled"][metric]
        for run in result["replicates"]
    )


def compare(control, candidate, iid_resamples=20000, block_resamples=20000):
    """Compare joint wake/data against instruction-only before the tail."""
    validate_analysis(control, "control", "wake-trigger")
    validate_analysis(candidate, "candidate", "wake-data")
    if control.get("group") != candidate.get("group"):
        raise ValueError("control and candidate use different cache-set groups")
    for key in ("bitstream_sha256", "control_program_sha256"):
        control_value = control.get("identity", {}).get(key)
        candidate_value = candidate.get("identity", {}).get(key)
        if not control_value or control_value != candidate_value:
            raise ValueError(f"control and candidate identity {key} differs")
    if iid_resamples <= 0 or block_resamples <= 0:
        raise ValueError("bootstrap resample counts must be positive")

    output = {
        "purpose": (
            "Measure the incremental effect of adding four late data hints to "
            "mode-six wakeup instruction replay on the same routed FPGA."
        ),
        "sign_convention": (
            "candidate-minus-control enabled effect; negative means late data "
            "improves the endpoint beyond instruction replay alone"
        ),
        "control": {
            "timing": control["timing"],
            "identity": control["identity"],
            "analysis_path": control.get("_analysis_path"),
            "analysis_sha256": control.get("_analysis_sha256"),
        },
        "candidate": {
            "timing": candidate["timing"],
            "identity": candidate["identity"],
            "analysis_path": candidate.get("_analysis_path"),
            "analysis_sha256": candidate.get("_analysis_sha256"),
        },
        "group": control["group"],
        "metrics": {},
        "interpretation_limit": (
            "Only endpoints ending at first use are compared. The ordinary "
            "wake-trigger benchmark calls getrusage after first use, while "
            "wake-data uses a counted hook, so post-load and roundtrip effects "
            "are intentionally excluded."
        ),
    }
    for index, metric in enumerate(COMPARABLE_METRICS):
        control_effect = point_effect(control, metric)
        candidate_effect = point_effect(candidate, metric)
        output["metrics"][metric] = {
            "instruction_only_enabled_minus_disabled": control_effect,
            "joint_enabled_minus_disabled": candidate_effect,
            "joint_minus_instruction_only": (
                candidate_effect - control_effect
            ),
            "iid_bootstrap": bootstrap_difference(
                control, candidate, metric, 0xDA7A + index,
                iid_resamples, 1
            ),
            "circular_block_bootstrap": bootstrap_difference(
                control, candidate, metric, 0xDA8A + index,
                block_resamples, 16
            ),
        }
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--iid-resamples", type=int, default=20000)
    parser.add_argument("--block-resamples", type=int, default=20000)
    args = parser.parse_args(argv)
    try:
        result = compare(
            load_analysis(args.control), load_analysis(args.candidate),
            args.iid_resamples, args.block_resamples
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
