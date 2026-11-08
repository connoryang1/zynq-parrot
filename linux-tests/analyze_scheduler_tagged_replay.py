#!/usr/bin/env python3
"""Validate and summarize one interleaved tagged-replay Linux board run."""

import argparse
import hashlib
import json
import random
import re
import statistics
from pathlib import Path


CONFIG = re.compile(
    r"TAGGED_REPLAY_CONFIG mode=(off|data|data-prewake|data-prewake-equalized|data-prewake-equalized-quiescent|data-late|instruction-select|"
    r"instruction-wake|instruction-explicit|instruction-explicit-roundtrip|"
    r"instruction-explicit-directed|"
    r"joint|joint-explicit|joint-prewake-quiescent|joint-preseed-quiescent|joint-split|joint-split-one-hook|"
    r"joint-follow-only) "
    r"lines=(\d+) slot=(\d+) "
    r"delay=(\d+) gap=(\d+) policy=(normal|fifo) lead_cycles=(\d+)"
)
ROW = re.compile(
    r"TAGGED_REPLAY trial=(\d+) enabled=(\d+) hooks=(\d+) woken=(\d+) "
    r"hook_cycles=(\d+) admitted=(\d+) filtered=(\d+) triggers=(\d+) "
    r"dropped=(\d+) wake_to_entry=(\d+) load_cycles=(\d+) "
    r"wake_to_load=(\d+) roundtrip=(\d+)"
)
PROBE_CONFIG = re.compile(r"TAGGED_REPLAY_CONFIG .* probe_status=(0|1)")
PREWAKE_CONFIG = re.compile(
    r"TAGGED_REPLAY_CONFIG .* prewake_budget_cycles=(\d+)"
)
PREWAKE_MAX_CONFIG = re.compile(
    r"TAGGED_REPLAY_CONFIG .* prewake_max_cycles=(\d+)"
)
RT_CONFIG = re.compile(r"TAGGED_REPLAY_CONFIG .* rt_unlimited=(0|1)")
PREWAKE_ROW = re.compile(
    r"^TAGGED_REPLAY trial=(\d+).* prewake_cycles=(\d+) preblock_status=",
    re.MULTILINE,
)
LAYOUT_CONFIG = re.compile(r"TAGGED_REPLAY_CONFIG .* layout=(aligned|skew)")
SYNC_CONFIG = re.compile(r"TAGGED_REPLAY_CONFIG .* sync=(pipe|futex)")
ICACHE_RANGES_CONFIG = re.compile(
    r"TAGGED_REPLAY_CONFIG .* icache_ranges=(full|0:8,8:8)"
)
KERNEL_CONFIG = re.compile(
    r"TAGGED_REPLAY_CONFIG .* kernel_mode=(\d+) expected_hooks=(\d+)"
)
ICACHE_STATUS = re.compile(
    r"^TAGGED_REPLAY_ICACHE_STATUS before=0x([0-9a-fA-F]{16}) "
    r"after=0x([0-9a-fA-F]{16})$", re.MULTILINE
)
PROBE_ROW = re.compile(
    r"^TAGGED_REPLAY trial=(\d+).* preblock_status=0x([0-9a-fA-F]{16}) "
    r"preblock_probe_cycles=(\d+) entry_probe_status=0x([0-9a-fA-F]{16}) "
    r"entry_probe_cycles=(\d+)$", re.MULTILINE
)
METRICS = (
    "hook_cycles", "wake_to_entry", "load_cycles", "wake_to_load", "roundtrip"
)


def percentile(values, fraction):
    """Return a nearest-rank value from an already finite sample."""
    ordered = sorted(values)
    return ordered[round(fraction * (len(ordered) - 1))]


def summarize_metric(rows, metric, rng, bootstrap_samples):
    """Use polarity-alternating balanced blocks to suppress drift and phase."""
    disabled = [row[metric] for row in rows if not row["enabled"]]
    enabled = [row[metric] for row in rows if row["enabled"]]
    blocks = []
    for start in range(0, len(rows), 4):
        block = rows[start:start + 4]
        disabled_mean = statistics.mean(
            row[metric] for row in block if not row["enabled"]
        )
        enabled_mean = statistics.mean(
            row[metric] for row in block if row["enabled"]
        )
        blocks.append(disabled_mean - enabled_mean)
    estimate = statistics.median(blocks)
    boots = [statistics.median(rng.choices(blocks, k=len(blocks)))
             for _ in range(bootstrap_samples)]
    return {
        "disabled_median_cycles": statistics.median(disabled),
        "enabled_median_cycles": statistics.median(enabled),
        "paired_median_saved_cycles": estimate,
        "paired_95pct_ci_saved_cycles": [
            percentile(boots, 0.025), percentile(boots, 0.975)
        ],
        "disabled_range_cycles": [min(disabled), max(disabled)],
        "enabled_range_cycles": [min(enabled), max(enabled)],
    }


def summarize_disabled_metric(rows, metric):
    """Summarize a replay-off stability run without inventing an A/B effect."""
    values = [row[metric] for row in rows]
    return {
        "median_cycles": statistics.median(values),
        "range_cycles": [min(values), max(values)],
    }


def analyze(path, bootstrap_samples=20000):
    """Fail closed on identities, counters, markers, and A/B trial shape."""
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    text = path.read_text(errors="replace").replace("\x00", "").replace("\r", "")
    status_path = path.with_suffix(path.suffix + ".status.json")
    if not status_path.is_file():
        raise ValueError(f"missing runner status {status_path}")
    status = json.loads(status_path.read_text())
    if status.get("status") != "PASS":
        raise ValueError("runner status is not PASS")
    for key in ("nbf_sha256", "transfer_sha256", "elf_sha256",
                "control_program_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(status.get(key, ""))):
            raise ValueError(f"status lacks valid {key}")
    bitstream = status.get("bitstream_sha256")
    if bitstream is not None and not re.fullmatch(r"[0-9a-f]{64}", bitstream):
        raise ValueError("status has invalid bitstream_sha256")

    configs = CONFIG.findall(text)
    if len(configs) != 1:
        raise ValueError("expected exactly one tagged-replay configuration")
    mode, lines, slot, delay, gap, policy, lead = configs[0]
    config = {
        "mode": mode,
        "lines": int(lines),
        "slot": int(slot),
        "delay": int(delay),
        "gap": int(gap),
        "policy": policy,
        "lead_cycles": int(lead),
    }
    probe_configs = PROBE_CONFIG.findall(text)
    if len(probe_configs) > 1:
        raise ValueError("expected at most one probe-status configuration")
    config["probe_status"] = bool(int(probe_configs[0])) if probe_configs else False
    prewake_configs = PREWAKE_CONFIG.findall(text)
    if len(prewake_configs) > 1:
        raise ValueError("expected at most one prewake budget configuration")
    config["prewake_budget_cycles"] = (
        int(prewake_configs[0]) if prewake_configs else 0
    )
    expected_prewake_budget = (
        65536 if mode in ("data-prewake-equalized-quiescent",
                          "joint-prewake-quiescent",
                          "joint-preseed-quiescent") else
        262144 if mode == "data-prewake-equalized" else 0
    )
    if config["prewake_budget_cycles"] != expected_prewake_budget:
        raise ValueError("unexpected prewake equalization budget")
    prewake_max_configs = PREWAKE_MAX_CONFIG.findall(text)
    if len(prewake_max_configs) > 1:
        raise ValueError("expected at most one prewake maximum configuration")
    config["prewake_max_cycles"] = (
        int(prewake_max_configs[0]) if prewake_max_configs else 0
    )
    expected_prewake_max = (
        73728 if mode in ("data-prewake-equalized-quiescent",
                          "joint-prewake-quiescent",
                          "joint-preseed-quiescent") else 0
    )
    if config["prewake_max_cycles"] != expected_prewake_max:
        raise ValueError("unexpected prewake equalization maximum")
    rt_configs = RT_CONFIG.findall(text)
    if len(rt_configs) > 1:
        raise ValueError("expected at most one RT-runtime configuration")
    config["rt_unlimited"] = bool(int(rt_configs[0])) if rt_configs else False
    layout_configs = LAYOUT_CONFIG.findall(text)
    if len(layout_configs) > 1:
        raise ValueError("expected at most one footprint layout")
    config["layout"] = layout_configs[0] if layout_configs else "aligned"
    sync_configs = SYNC_CONFIG.findall(text)
    if len(sync_configs) > 1:
        raise ValueError("expected at most one synchronization style")
    config["sync"] = sync_configs[0] if sync_configs else "pipe"
    kernel_configs = KERNEL_CONFIG.findall(text)
    if len(kernel_configs) > 1:
        raise ValueError("expected at most one kernel-mode configuration")
    if kernel_configs:
        config["kernel_mode"] = int(kernel_configs[0][0])
        config["expected_hooks"] = int(kernel_configs[0][1])
        expected_kernel_modes = {
            "off": 0,
            "data": 9,
            "data-prewake": 0,
            "data-prewake-equalized": 0,
            "data-prewake-equalized-quiescent": 0,
            "data-late": 11,
            "instruction-select": 3,
            "instruction-wake": 13,
            "instruction-explicit": 0,
            "instruction-explicit-roundtrip": 0,
            "instruction-explicit-directed": 0,
            "joint": 10,
            "joint-explicit": 9,
            "joint-prewake-quiescent": 0,
            "joint-preseed-quiescent": 0,
            "joint-split": 12,
            "joint-split-one-hook": 12,
            "joint-follow-only": 12,
        }
        if config["kernel_mode"] != expected_kernel_modes[mode]:
            raise ValueError("mode name does not match configured kernel mode")
    elif mode in ("instruction-wake", "instruction-explicit",
                  "instruction-explicit-roundtrip",
                        "instruction-explicit-directed", "joint-explicit",
                        "joint-prewake-quiescent",
                        "joint-preseed-quiescent"):
        raise ValueError(
            f"{mode} transcript lacks dedicated kernel-mode binding"
        )
    if (config["lines"] not in range(4, 33, 4) or config["slot"] != 2):
        raise ValueError("unexpected replay footprint shape")
    for key in ("mode", "delay", "gap", "policy", "lead_cycles"):
        if status.get(key) != config[key]:
            raise ValueError(
                f"status {key}={status.get(key)!r}, expected {config[key]!r}"
            )
    if ("lines_per_base" in status
            and status["lines_per_base"] * 4 != config["lines"]):
        raise ValueError("status lines_per_base does not match replay footprint")
    if bool(status.get("probe_status", False)) != config["probe_status"]:
        raise ValueError("status probe_status does not match configuration")
    if bool(status.get("rt_unlimited", False)) != config["rt_unlimited"]:
        raise ValueError("status RT-runtime policy does not match configuration")
    if status.get("layout", "aligned") != config["layout"]:
        raise ValueError("status layout does not match configuration")
    if status.get("sync", "pipe") != config["sync"]:
        raise ValueError("status sync does not match configuration")
    ranges = ICACHE_RANGES_CONFIG.findall(text)
    if len(ranges) > 1:
        raise ValueError("expected at most one instruction range configuration")
    config["icache_ranges"] = ranges[0] if ranges else "full"
    expected_ranges = ("0:8,8:8"
                       if mode == "instruction-explicit-directed" else "full")
    if config["icache_ranges"] != expected_ranges:
        raise ValueError("mode does not match instruction range configuration")
    required = ("TAGGED_REPLAY_CHILD PASS", "TAGGED_REPLAY_PARENT PASS", "BSG PASS")
    for marker in required:
        if marker not in text:
            raise ValueError(f"missing marker {marker!r}")
    if not re.search(r"\bCORE(?:\[0\])? PASS\b", text):
        raise ValueError("missing CORE PASS")
    for marker in ("BUG:", "Kernel panic", "Oops:", "BP_REPLAY_TIMER_GUARD",
                   "scheduling while atomic",
                   "Segmentation fault", "unhandled signal ",
                   "RT throttling activated"):
        if marker in text:
            raise ValueError(f"contains kernel failure marker {marker!r}")
    retry_markers = len(re.findall(r"^TAGGED_REPLAY_RETRY ", text, re.MULTILINE))
    retry_pass = re.findall(r"TAGGED_REPLAY_CHILD PASS retries=(\d+)", text)
    if retry_pass != [str(retry_markers)]:
        raise ValueError("retry count does not match filtered attempts")
    if re.search(r"^TAGGED_REPLAY_PREWAKE_RETRY ", text, re.MULTILINE):
        raise ValueError("unexpected in-guest prewake retry")

    icache_statuses = ICACHE_STATUS.findall(text)
    if mode in ("instruction-wake", "instruction-explicit",
                "instruction-explicit-roundtrip",
                "instruction-explicit-directed", "joint-explicit",
                "joint-prewake-quiescent",
                "joint-preseed-quiescent"):
        if len(icache_statuses) != 1:
            raise ValueError(f"{mode} requires one I-cache status marker")
        before = int(icache_statuses[0][0], 16)
        after = int(icache_statuses[0][1], 16)
        before_decoded = {
            "ready": before & 1,
            "busy": (before >> 1) & 1,
            "entry_held": (before >> 2) & 1,
            "read_pending": (before >> 3) & 1,
            "configured_entries": (before >> 4) & 0x1ff,
            "next_index": (before >> 13) & 0x1ff,
            "accepted_entries": (before >> 22) & 0xffff,
            "accepted_triggers": (before >> 38) & 0xff,
            "dropped_triggers": (before >> 46) & 0xff,
            "resident_query_pending": (before >> 54) & 1,
            "resident_drops": (before >> 55) & 0x1ff,
        }
        after_decoded = {
            "ready": after & 1,
            "busy": (after >> 1) & 1,
            "entry_held": (after >> 2) & 1,
            "read_pending": (after >> 3) & 1,
            "configured_entries": (after >> 4) & 0x1ff,
            "next_index": (after >> 13) & 0x1ff,
            "accepted_entries": (after >> 22) & 0xffff,
            "accepted_triggers": (after >> 38) & 0xff,
            "dropped_triggers": (after >> 46) & 0xff,
            "resident_query_pending": (after >> 54) & 1,
            "resident_drops": (after >> 55) & 0x1ff,
        }
        prefix_entries = before_decoded["configured_entries"]
        if (prefix_entries not in range(1, 257)
                or any(before_decoded[key] for key in (
                    "busy", "entry_held", "read_pending", "next_index",
                    "accepted_entries", "accepted_triggers",
                    "dropped_triggers", "resident_query_pending",
                    "resident_drops"))):
            raise ValueError("instruction-prefix baseline is not clean and configured")
        if (after_decoded["configured_entries"] != prefix_entries
                or after_decoded["next_index"] != prefix_entries
                or after_decoded["accepted_triggers"] != 0xff
                or after_decoded["dropped_triggers"]
                or any(after_decoded[key] for key in (
                    "busy", "entry_held", "read_pending",
                    "resident_query_pending"))):
            raise ValueError("instruction-prefix replay did not drain cleanly")
        if not (after_decoded["accepted_entries"]
                or after_decoded["resident_drops"]):
            raise ValueError("instruction-prefix triggers processed no entries")
    elif icache_statuses:
        raise ValueError("unexpected I-cache status marker for non-instruction mode")

    fields = (
        "trial", "enabled", "hooks", "woken", "hook_cycles", "admitted", "filtered",
        "triggers", "dropped", "wake_to_entry", "load_cycles", "wake_to_load",
        "roundtrip",
    )
    rows = [dict(zip(fields, map(int, match.groups()))) for match in ROW.finditer(text)]
    if len(rows) != 512 or [row["trial"] for row in rows] != list(range(512)):
        raise ValueError("expected exactly 512 ordered trials")
    if mode == "off":
        if any(row["enabled"] for row in rows):
            raise ValueError("replay-off stability run contains an enabled trial")
    else:
        for start in range(0, len(rows), 4):
            pattern = [row["enabled"] for row in rows[start:start + 4]]
            expected = [0, 1, 1, 0] if (start // 4) % 2 == 0 else [1, 0, 0, 1]
            if pattern != expected:
                raise ValueError(f"unbalanced trial block at {start}: {pattern}")

    analysis_rows = rows
    prewake_rows = []
    stretched_prewake_trials = 0
    filtered_prewake_blocks = 0
    if mode in ("data-prewake-equalized",
                "data-prewake-equalized-quiescent",
                "joint-prewake-quiescent",
                "joint-preseed-quiescent"):
        prewake_matches = PREWAKE_ROW.findall(text)
        if (len(prewake_matches) != len(rows)
                or [int(trial) for trial, _ in prewake_matches]
                != list(range(len(rows)))):
            raise ValueError("expected one ordered prewake duration per trial")
        for index, (_, cycles) in enumerate(prewake_matches):
            rows[index]["prewake_cycles"] = int(cycles)
        if any(row["prewake_cycles"] < expected_prewake_budget for row in rows):
            raise ValueError("prewake duration ended before its fixed budget")
        if mode in ("data-prewake-equalized-quiescent",
                    "joint-prewake-quiescent",
                    "joint-preseed-quiescent"):
            stretched_prewake_trials = sum(
                row["prewake_cycles"] > expected_prewake_max for row in rows
            )
            analysis_rows = []
            for start in range(0, len(rows), 4):
                block = rows[start:start + 4]
                if any(row["prewake_cycles"] > expected_prewake_max
                       for row in block):
                    filtered_prewake_blocks += 1
                else:
                    analysis_rows.extend(block)
            if len(analysis_rows) < 128:
                raise ValueError("fewer than 32 quiescent balanced blocks remain")
        prewake_rows = [
            {"enabled": row["enabled"],
             "prewake_cycles": row["prewake_cycles"]}
            for row in analysis_rows
        ]

    probe_rows = [
        (int(trial), int(preblock_status, 16), int(preblock_cycles),
         int(entry_status, 16), int(entry_cycles))
        for trial, preblock_status, preblock_cycles, entry_status, entry_cycles
        in PROBE_ROW.findall(text)
    ]
    if config["probe_status"]:
        if (len(probe_rows) != len(rows)
                or [row[0] for row in probe_rows] != list(range(len(rows)))):
            raise ValueError("expected one ordered preblock status per trial")
    elif probe_rows and any(preblock_status or preblock_cycles
                            or entry_status or entry_cycles
                            for _, preblock_status, preblock_cycles,
                            entry_status, entry_cycles in probe_rows):
        raise ValueError("disabled preblock probe reported nonzero data")

    admitted = filtered = accepted_triggers = 0
    expected_enabled_hooks = config.get("expected_hooks", 1)
    for index, row in enumerate(rows):
        if row["hooks"] != row["enabled"] * expected_enabled_hooks:
            raise ValueError(f"trial {index} has invalid hook count")
        if row["woken"] != 1:
            raise ValueError(f"trial {index} did not wake exactly one child")
        if row["wake_to_entry"] + row["load_cycles"] != row["wake_to_load"]:
            raise ValueError(f"trial {index} has inconsistent first-use timing")
        if row["wake_to_load"] > row["roundtrip"]:
            raise ValueError(f"trial {index} ends before first use")
        # PR_BP_PREVIEW_REPLAY_CONFIG sets the hardware clear bit before every
        # trial, so these are independent snapshots rather than deltas.
        expects_trigger = mode not in (
            "off", "instruction-select", "instruction-wake",
            "instruction-explicit", "instruction-explicit-roundtrip",
            "instruction-explicit-directed"
        )
        expected_entries = 0 if mode == "joint-follow-only" else config["lines"]
        expected_triggers = row["enabled"] if expects_trigger else 0
        if row["triggers"] != expected_triggers or row["dropped"] != 0:
            raise ValueError(f"trial {index} has invalid trigger/drop counters")
        if row["enabled"] and expects_trigger:
            if row["admitted"] + row["filtered"] != expected_entries:
                raise ValueError(f"trial {index} did not complete all replay entries")
            admitted += row["admitted"]
            filtered += row["filtered"]
            accepted_triggers += row["triggers"]
        elif row["admitted"] or row["filtered"]:
            raise ValueError(f"disabled trial {index} changed replay counters")

    rng = random.Random(0x7A66ED)
    result = {
        "purpose": (
            "Validate replay-off futex stability without claiming an A/B effect."
            if mode == "off" else
            "Measure selection-time instruction replay under the matched "
            "tagged-data workload without issuing a data tag."
            if mode == "instruction-select" else
            "Measure successful-wakeup instruction replay under the matched "
            "tagged-data workload without issuing a data tag."
            if mode == "instruction-wake" else
            "Measure an explicit parent-issued instruction-prefix hint "
            "immediately before the matched blocking handoff."
            if mode == "instruction-explicit" else
            "Measure matched explicit instruction-prefix hints immediately "
            "before both pipe wakes in the full synchronization roundtrip."
            if mode == "instruction-explicit-roundtrip" else
            "Measure direction-selected forward and reverse instruction "
            "subranges immediately before their corresponding pipe wakes."
            if mode == "instruction-explicit-directed" else
            "Measure an explicit parent-issued instruction prefix immediately "
            "before the same wake whose kernel hook launches tagged data replay."
            if mode == "joint-explicit" else
            "Measure an explicit instruction-prefix trigger immediately before "
            "a wake whose data footprint was drained during a bounded prewake."
            if mode == "joint-prewake-quiescent" else
            "Measure a wake after both instruction and data replay lanes were "
            "launched, drained, and equalized during a bounded preseed."
            if mode == "joint-preseed-quiescent" else
            "Measure a fully drained explicit data replay before publishing "
            "readiness and starting the later timed wake."
            if mode == "data-prewake" else
            "Measure fully drained data replay after equalizing both arms to "
            "the same pre-readiness physical-cycle budget."
            if mode == "data-prewake-equalized" else
            "Measure fully drained data replay after accepting only quiescent "
            "pre-readiness intervals with a bounded physical-cycle duration."
            if mode == "data-prewake-equalized-quiescent" else
            "Measure wake-time tagged data while the selection block is "
            "disabled for diagnostic isolation."
            if mode == "joint-split-one-hook" else
            "Measure one wake-time tagged command whose hardware follow "
            "launches instruction replay before ordered data replay."
            if mode == "joint-split" else
            "Measure the hardware-follow instruction path with an accepted "
            "zero-entry tagged command and no detached data traffic."
            if mode == "joint-follow-only" else
            "Measure a matched Linux wakeup with one tagged data replay "
            "while validating that every enabled tag completed."
        ),
        "transcript": str(path),
        "transcript_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": str(status_path),
        "status_sha256": hashlib.sha256(status_path.read_bytes()).hexdigest(),
        "identity": {key: status.get(key) for key in (
            "nbf_sha256", "transfer_sha256", "elf_sha256",
            "control_program_sha256", "bitstream_sha256"
        )},
        "config": config,
        "trials": len(rows),
        "trials_per_arm": len(rows) if mode == "off" else len(rows) // 2,
        "analyzed_trials": len(analysis_rows),
        "analyzed_trials_per_arm": (
            len(analysis_rows) if mode == "off" else len(analysis_rows) // 2
        ),
        "filtered_attempts": retry_markers,
        "stretched_prewake_trials": stretched_prewake_trials,
        "filtered_prewake_blocks": filtered_prewake_blocks,
        "counter_deltas": {
            "admitted_entries": admitted,
            "filtered_entries": filtered,
            "accepted_triggers": accepted_triggers,
            "dropped_triggers": 0,
        },
        "metrics": {
            metric: (summarize_disabled_metric(analysis_rows, metric)
                     if mode == "off" else
                     summarize_metric(analysis_rows, metric, rng,
                                      bootstrap_samples))
            for metric in METRICS
        },
    }
    if mode in ("data-prewake-equalized",
                "data-prewake-equalized-quiescent",
                "joint-prewake-quiescent",
                "joint-preseed-quiescent"):
        result["prewake_equalization"] = summarize_metric(
            prewake_rows, "prewake_cycles", rng, bootstrap_samples
        )
    if mode in ("instruction-wake", "instruction-explicit",
                "instruction-explicit-roundtrip",
                "instruction-explicit-directed", "joint-explicit",
                "joint-prewake-quiescent",
                "joint-preseed-quiescent"):
        result["icache_prefix_status"] = {
            "before": before_decoded,
            "after": after_decoded,
        }
    if config["probe_status"]:
        decoded = []
        for trial, raw_status, cycles, entry_status, entry_cycles in probe_rows:
            decoded.append({
                "enabled": rows[trial]["enabled"],
                "busy": raw_status & 1,
                "queued": (raw_status >> 1) & 0x3,
                "held": (raw_status >> 3) & 1,
                "next_index": (raw_status >> 4) & 0x3f,
                "admitted": (raw_status >> 10) & 0xffff,
                "filtered": (raw_status >> 26) & 0xffff,
                "triggers": (raw_status >> 42) & 0xff,
                "dropped": (raw_status >> 50) & 0xff,
                "status_bits_59_58": (raw_status >> 58) & 0x3,
                "uce_outstanding": (raw_status >> 60) & 0x7,
                "uce_complete": (raw_status >> 63) & 0x1,
                "probe_cycles": cycles,
                "entry_busy": entry_status & 1,
                "entry_queued": (entry_status >> 1) & 0x3,
                "entry_held": (entry_status >> 3) & 1,
                "entry_next_index": (entry_status >> 4) & 0x3f,
                "entry_admitted": (entry_status >> 10) & 0xffff,
                "entry_filtered": (entry_status >> 26) & 0xffff,
                "entry_triggers": (entry_status >> 42) & 0xff,
                "entry_dropped": (entry_status >> 50) & 0xff,
                "entry_status_bits_59_58": (entry_status >> 58) & 0x3,
                "entry_uce_outstanding": (entry_status >> 60) & 0x7,
                "entry_uce_complete": (entry_status >> 63) & 0x1,
                "entry_probe_cycles": entry_cycles,
            })
        enabled_probe = [row for row in decoded if row["enabled"]]
        disabled_probe = [row for row in decoded if not row["enabled"]]
        if any(row["triggers"] not in (0, 1) or row["dropped"]
               for row in enabled_probe):
            raise ValueError("enabled preblock probe has invalid trigger counters")
        if any((not row["triggers"]
                and (row["busy"] or row["queued"] or row["held"]
                     or row["admitted"] or row["filtered"]))
               for row in enabled_probe):
            raise ValueError("preblock replay state changed before trigger visibility")
        if any(row["admitted"] + row["filtered"] > config["lines"]
               for row in enabled_probe):
            raise ValueError("preblock replay counters exceed configured footprint")
        if any(row["triggers"] or row["dropped"] for row in disabled_probe):
            raise ValueError("disabled preblock probe has trigger counters")
        if any(row["entry_triggers"] != 1 or row["entry_dropped"]
               for row in enabled_probe):
            raise ValueError("enabled entry probe has invalid trigger counters")
        if any(row["entry_triggers"] or row["entry_dropped"]
               for row in disabled_probe):
            raise ValueError("disabled entry probe has trigger counters")
        if any(row["entry_admitted"] + row["entry_filtered"] > config["lines"]
               for row in enabled_probe):
            raise ValueError("entry replay counters exceed configured footprint")
        if any(row["uce_complete"] > row["uce_outstanding"]
               or row["entry_uce_complete"] > row["entry_uce_outstanding"]
               for row in decoded):
            raise ValueError("UCE complete count exceeds outstanding count")
        result["preblock_probe"] = {
            "enabled_trigger_visible_trials": sum(
                bool(row["triggers"]) for row in enabled_probe
            ),
            "enabled_trigger_not_visible_trials": sum(
                not row["triggers"] for row in enabled_probe
            ),
            "enabled_fully_admitted_trials": sum(
                row["triggers"] == 1
                and row["admitted"] + row["filtered"] == config["lines"]
                and not (row["busy"] or row["queued"] or row["held"])
                for row in enabled_probe
            ),
            "enabled_busy_trials": sum(row["busy"] for row in enabled_probe),
            "enabled_queued_trials": sum(bool(row["queued"])
                                           for row in enabled_probe),
            "enabled_held_trials": sum(row["held"] for row in enabled_probe),
            "enabled_admitted_median": statistics.median(
                row["admitted"] for row in enabled_probe
            ),
            "enabled_admitted_range": [
                min(row["admitted"] for row in enabled_probe),
                max(row["admitted"] for row in enabled_probe),
            ],
            "enabled_admitted_histogram": {
                str(value): sum(row["admitted"] == value
                                for row in enabled_probe)
                for value in sorted({row["admitted"] for row in enabled_probe})
            },
            "enabled_next_index_median": statistics.median(
                row["next_index"] for row in enabled_probe
            ),
            "enabled_next_index_range": [
                min(row["next_index"] for row in enabled_probe),
                max(row["next_index"] for row in enabled_probe),
            ],
            "probe_cycles_median": {
                "disabled": statistics.median(
                    row["probe_cycles"] for row in disabled_probe
                ),
                "enabled": statistics.median(
                    row["probe_cycles"] for row in enabled_probe
                ),
            },
            "uce_outstanding_histogram": {
                arm: {
                    str(value): sum(row["uce_outstanding"] == value
                                    for row in arm_rows)
                    for value in sorted({row["uce_outstanding"]
                                         for row in arm_rows})
                }
                for arm, arm_rows in (("disabled", disabled_probe),
                                      ("enabled", enabled_probe))
            },
            # These bits were the active-slot field in older FPGA images and
            # are drain-age buckets in the diagnostic image.  Keep the JSON
            # label neutral so historical transcripts remain interpretable.
            "status_bits_59_58_histogram": {
                arm: {
                    str(value): sum(row["status_bits_59_58"] == value
                                    for row in arm_rows)
                    for value in sorted({row["status_bits_59_58"]
                                         for row in arm_rows})
                }
                for arm, arm_rows in (("disabled", disabled_probe),
                                      ("enabled", enabled_probe))
            },
            "uce_complete_histogram": {
                arm: {
                    str(value): sum(row["uce_complete"] == value
                                    for row in arm_rows)
                    for value in sorted({row["uce_complete"]
                                         for row in arm_rows})
                }
                for arm, arm_rows in (("disabled", disabled_probe),
                                      ("enabled", enabled_probe))
            },
            "entry_busy_trials": sum(row["entry_busy"] for row in enabled_probe),
            "entry_queued_trials": sum(bool(row["entry_queued"])
                                        for row in enabled_probe),
            "entry_held_trials": sum(row["entry_held"] for row in enabled_probe),
            "entry_fully_admitted_trials": sum(
                row["entry_admitted"] + row["entry_filtered"] == config["lines"]
                and not (row["entry_busy"] or row["entry_queued"]
                         or row["entry_held"])
                for row in enabled_probe
            ),
            "entry_admitted_median": statistics.median(
                row["entry_admitted"] for row in enabled_probe
            ),
            "entry_admitted_range": [
                min(row["entry_admitted"] for row in enabled_probe),
                max(row["entry_admitted"] for row in enabled_probe),
            ],
            "entry_admitted_histogram": {
                str(value): sum(row["entry_admitted"] == value
                                for row in enabled_probe)
                for value in sorted({row["entry_admitted"]
                                     for row in enabled_probe})
            },
            "entry_next_index_median": statistics.median(
                row["entry_next_index"] for row in enabled_probe
            ),
            "entry_next_index_range": [
                min(row["entry_next_index"] for row in enabled_probe),
                max(row["entry_next_index"] for row in enabled_probe),
            ],
            "entry_probe_cycles_median": {
                "disabled": statistics.median(
                    row["entry_probe_cycles"] for row in disabled_probe
                ),
                "enabled": statistics.median(
                    row["entry_probe_cycles"] for row in enabled_probe
                ),
            },
            "entry_uce_outstanding_histogram": {
                arm: {
                    str(value): sum(row["entry_uce_outstanding"] == value
                                    for row in arm_rows)
                    for value in sorted({row["entry_uce_outstanding"]
                                         for row in arm_rows})
                }
                for arm, arm_rows in (("disabled", disabled_probe),
                                      ("enabled", enabled_probe))
            },
            "entry_status_bits_59_58_histogram": {
                arm: {
                    str(value): sum(row["entry_status_bits_59_58"] == value
                                    for row in arm_rows)
                    for value in sorted({row["entry_status_bits_59_58"]
                                         for row in arm_rows})
                }
                for arm, arm_rows in (("disabled", disabled_probe),
                                      ("enabled", enabled_probe))
            },
            "entry_uce_complete_histogram": {
                arm: {
                    str(value): sum(row["entry_uce_complete"] == value
                                    for row in arm_rows)
                    for value in sorted({row["entry_uce_complete"]
                                         for row in arm_rows})
                }
                for arm, arm_rows in (("disabled", disabled_probe),
                                      ("enabled", enabled_probe))
            },
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=20000)
    args = parser.parse_args()
    try:
        result = analyze(args.transcript, args.bootstrap_samples)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
