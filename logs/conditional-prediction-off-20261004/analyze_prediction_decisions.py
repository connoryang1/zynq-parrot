#!/usr/bin/env python3
"""Verify the conditional-prediction isolation in paired waveform extracts."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from cache_overlap_vcd import EvidenceError, rising_edges  # noqa: E402
from prefetch_overlap_vcd import bit, read_header  # noqa: E402

HERE = Path(__file__).resolve().parent
SIGNALS = {
    # Verilator aliases the core clock to a constant in this trace but retains
    # the generated inverse. Sample its rising edge (the core falling edge),
    # where the combinational predictor decision is stable.
    "clock": "blackparrot.negedge_clk",
    "bht_pred": "bht_pred_lo",
    "btb_valid": "btb_br_tgt_v_lo",
    "btb_jump": "btb_br_tgt_jmp_lo",
    "btb_taken": "btb_taken",
}


def analyze(path, conditional_enabled):
    counts = {
        "sampled_cycles": 0,
        "valid_conditional_taken_candidates": 0,
        "unconditional_jump_hits": 0,
        "observed_btb_taken": 0,
    }
    failures = []
    with path.open() as stream:
        selected, timescale = read_header(stream, SIGNALS)
        for cycle, timestamp, values in rising_edges(stream, selected):
            try:
                valid = bit(values, "btb_valid")
                jump = bit(values, "btb_jump")
                prediction = bit(values, "bht_pred")
                taken = bit(values, "btb_taken")
            except EvidenceError:
                # Predictor SRAMs are unknown during reset initialization.
                continue
            counts["sampled_cycles"] += 1
            conditional_candidate = valid and prediction and not jump
            unconditional_hit = valid and jump
            counts["valid_conditional_taken_candidates"] += int(conditional_candidate)
            counts["unconditional_jump_hits"] += int(unconditional_hit)
            counts["observed_btb_taken"] += taken
            expected = int(valid and (jump or (conditional_enabled and prediction)))
            if taken != expected:
                failures.append({
                    "cycle": cycle,
                    "timestamp": timestamp,
                    "valid": valid,
                    "jump": jump,
                    "prediction": prediction,
                    "taken": taken,
                    "expected": expected,
                })
    if not counts["sampled_cycles"]:
        failures.append({"kind": "coverage", "reason": "no sampled cycles"})
    if not counts["valid_conditional_taken_candidates"]:
        failures.append({"kind": "coverage", "reason": "no conditional candidates"})
    if not counts["unconditional_jump_hits"]:
        failures.append({"kind": "coverage", "reason": "no unconditional jump hits"})
    return {
        "trace": path.name,
        "timescale": timescale,
        "conditional_prediction_enabled": conditional_enabled,
        **counts,
        "failures": failures,
    }


def main():
    runs = [
        analyze(HERE / "predictor-enabled-selected.vcd", True),
        analyze(HERE / "prediction-off-selected.vcd", False),
    ]
    summary = {
        "status": "PASS" if all(not run["failures"] for run in runs) else "FAIL",
        "runs": runs,
    }
    (HERE / "prediction-decision-analysis.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return int(summary["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
