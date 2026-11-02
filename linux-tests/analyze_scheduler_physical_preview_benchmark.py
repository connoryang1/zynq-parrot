#!/usr/bin/env python3
"""Summarize interleaved Linux physical-preview timing with paired block CIs."""

import argparse
import json
import random
import re
import statistics
from pathlib import Path


ROW = re.compile(r"PHYSICAL_BENCH trial=(\d+) mode=(\d+) hooks=(\d+) "
                 r"wake_to_entry=(\d+) load_cycles=(\d+) "
                 r"wake_to_load=(\d+) roundtrip=(\d+)")
HOOK = re.compile(r"PHYSICAL_BENCH_HOOK trial=(\d+) cycles=(\d+)")
CONFIG = re.compile(r"PHYSICAL_BENCH_CONFIG group=(\d+) first_offset=(\d+) "
                    r"lines=(\d+) "
                    r"timing=(early|late|instruction|counter|trigger|wake-trigger|wake-data|wake-early-data|wake-early-drop|wake-early-data-only) "
                    r"mode=(\d+)")
METRICS = ("wake_to_entry", "load_cycles", "wake_to_load", "roundtrip")
TIMING_MODES = {
    "early": 1,
    "late": 2,
    "instruction": 3,
    "counter": 4,
    "trigger": 5,
    "wake-trigger": 6,
    "wake-data": 6,
    "wake-early-data": 1,
    "wake-early-drop": 7,
    "wake-early-data-only": 8,
}
LEAD_CYCLES = re.compile(r"PHYSICAL_BENCH_CONFIG[^\n]* lead_cycles=(\d+)")
ARM = re.compile(
    r"PHYSICAL_BENCH_CONFIG[^\n]* arm=(alternating|disabled|enabled|accepted-drop|joint-data-only)"
)
HOOK_TIMING = re.compile(r"PHYSICAL_BENCH_CONFIG[^\n]* hook_timing=([01])")


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[round(fraction * (len(ordered) - 1))]


def summarize_metric(rows, metric, rng, bootstrap_samples):
    off = [row[metric] for row in rows if row["mode"] == 0]
    on = [row[metric] for row in rows if row["mode"] == 1]
    blocks = []
    for start in range(0, len(rows), 4):
        block = rows[start:start + 4]
        off_mean = (block[0][metric] + block[3][metric]) / 2
        on_mean = (block[1][metric] + block[2][metric]) / 2
        blocks.append(off_mean - on_mean)
    estimate = statistics.median(blocks)
    boots = [statistics.median(rng.choices(blocks, k=len(blocks)))
             for _ in range(bootstrap_samples)]
    return {
        "off_median_cycles": statistics.median(off),
        "on_median_cycles": statistics.median(on),
        "paired_median_saved_cycles": estimate,
        "paired_95pct_ci_saved_cycles": [percentile(boots, 0.025),
                                          percentile(boots, 0.975)],
        "off_range_cycles": [min(off), max(off)],
        "on_range_cycles": [min(on), max(on)],
    }


def summarize(rows, group, timing, bootstrap_samples=20000, lines=4):
    trials = len(rows)
    if trials != 512 or [row["trial"] for row in rows] != list(range(trials)):
        raise ValueError("expected exactly 512 ordered trials")
    for start in range(0, trials, 4):
        modes = [row["mode"] for row in rows[start:start + 4]]
        if modes != [0, 1, 1, 0]:
            raise ValueError(f"unbalanced trial block at {start}: {modes}")
    for row in rows:
        expected_hooks = 0 if timing in ("trigger", "wake-trigger") else row["mode"]
        if row["hooks"] != expected_hooks:
            raise ValueError(
                f"trial {row['trial']} had mode={row['mode']} hooks={row['hooks']}; "
                f"expected hook count {expected_hooks} for {timing} timing"
            )
        if row["wake_to_entry"] + row["load_cycles"] != row["wake_to_load"]:
            raise ValueError(f"inconsistent timing at trial {row['trial']}")
        if row["wake_to_load"] > row["roundtrip"]:
            raise ValueError(f"roundtrip ended before child load at trial {row['trial']}")

    rng = random.Random(0xB50)
    paired_blocks = trials // 4
    result = {"l2_set_group": group, "preview_timing": timing,
              "active_lines": lines,
              "trials": trials,
              "trials_per_mode": trials // 2,
              "paired_blocks": paired_blocks, "metrics": {}}
    for metric in METRICS:
        result["metrics"][metric] = summarize_metric(
            rows, metric, rng, bootstrap_samples
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    text = args.transcript.read_text(errors="replace")
    if "PHYSICAL_BENCH_CHILD PASS" not in text or "PHYSICAL_BENCH_PARENT PASS" not in text:
        raise SystemExit("missing guest PASS markers")
    configs = CONFIG.findall(text)
    if len(configs) != 1:
        raise SystemExit("expected exactly one benchmark configuration marker")
    group = int(configs[0][0])
    first_offset = int(configs[0][1])
    lines = int(configs[0][2])
    timing = configs[0][3]
    mode = int(configs[0][4])
    lead_matches = LEAD_CYCLES.findall(text)
    lead_cycles = int(lead_matches[0]) if lead_matches else 0
    if len(lead_matches) > 1:
        raise SystemExit("expected at most one preview lead-cycle marker")
    if (group > 7 or first_offset != group * 256 or lines not in range(1, 5)
            or mode != TIMING_MODES[timing]):
        raise SystemExit("invalid benchmark configuration marker")
    arms = ARM.findall(text)
    if len(arms) != 1:
        raise SystemExit("expected exactly one benchmark arm marker")
    arm = arms[0]
    if arm in ("accepted-drop", "joint-data-only") \
            and timing != "wake-early-data":
        raise SystemExit("comparison arm requires wake-early-data timing")
    rows = []
    for match in ROW.finditer(text):
        values = [int(value) for value in match.groups()]
        rows.append(dict(zip(("trial", "mode", "hooks") + METRICS, values)))
    hook_timing_matches = HOOK_TIMING.findall(text)
    hook_timing = bool(hook_timing_matches
                       and int(hook_timing_matches[0]))
    if len(hook_timing_matches) > 1:
        raise SystemExit("expected at most one hook-timing marker")
    hook_rows = HOOK.findall(text)
    if hook_timing:
        if len(hook_rows) != len(rows):
            raise SystemExit("expected one hook timing for every trial")
        for expected, (trial, cycles) in enumerate(hook_rows):
            if int(trial) != expected:
                raise SystemExit("hook timings are not ordered by trial")
            rows[expected]["hook_cycles"] = int(cycles)
            if rows[expected]["hook_cycles"] > rows[expected]["wake_to_entry"]:
                raise SystemExit("hook timing exceeds wake-to-entry interval")
            rows[expected]["wake_to_entry_minus_hook"] = (
                rows[expected]["wake_to_entry"]
                - rows[expected]["hook_cycles"]
            )
    elif hook_rows:
        raise SystemExit("hook timings present while disabled")
    if arm in ("accepted-drop", "joint-data-only"):
        for row in rows:
            if row["hooks"] != 1:
                raise SystemExit(
                    f"comparison trial {row['trial']} had "
                    f"{row['hooks']} hooks; expected one"
                )
        # summarize() normally validates disabled-versus-enabled hook counts.
        # Preserve its paired-block calculation while presenting dropped
        # addresses as the control arm and accepted addresses as the target.
        normalized = [dict(row, hooks=row["mode"]) for row in rows]
        result = summarize(normalized, group, timing, lines=lines)
        result["comparison"] = (
            "pma-dropped-vs-accepted" if arm == "accepted-drop"
            else "data-only-vs-joint"
        )
    else:
        result = summarize(rows, group, timing, lines=lines)
        result["comparison"] = "disabled-vs-enabled"
    if hook_timing:
        result["metrics"]["hook_cycles"] = summarize_metric(
            normalized if arm in ("accepted-drop", "joint-data-only") else rows,
            "hook_cycles", random.Random(0xB51), 20000
        )
        result["metrics"]["wake_to_entry_minus_hook"] = summarize_metric(
            normalized if arm in ("accepted-drop", "joint-data-only") else rows,
            "wake_to_entry_minus_hook", random.Random(0xB52), 20000
        )
    result["hook_timing"] = hook_timing
    result["lead_cycles"] = lead_cycles
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
