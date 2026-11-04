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
    r"TAGGED_REPLAY_CONFIG mode=(off|data|data-late|instruction-select|"
    r"instruction-wake|joint|joint-split) "
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
LAYOUT_CONFIG = re.compile(r"TAGGED_REPLAY_CONFIG .* layout=(aligned|skew)")
SYNC_CONFIG = re.compile(r"TAGGED_REPLAY_CONFIG .* sync=(pipe|futex)")
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
    layout_configs = LAYOUT_CONFIG.findall(text)
    if len(layout_configs) > 1:
        raise ValueError("expected at most one footprint layout")
    config["layout"] = layout_configs[0] if layout_configs else "aligned"
    sync_configs = SYNC_CONFIG.findall(text)
    if len(sync_configs) > 1:
        raise ValueError("expected at most one synchronization style")
    config["sync"] = sync_configs[0] if sync_configs else "pipe"
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
    if status.get("layout", "aligned") != config["layout"]:
        raise ValueError("status layout does not match configuration")
    if status.get("sync", "pipe") != config["sync"]:
        raise ValueError("status sync does not match configuration")
    required = ("TAGGED_REPLAY_CHILD PASS", "TAGGED_REPLAY_PARENT PASS", "BSG PASS")
    for marker in required:
        if marker not in text:
            raise ValueError(f"missing marker {marker!r}")
    if not re.search(r"\bCORE(?:\[0\])? PASS\b", text):
        raise ValueError("missing CORE PASS")
    for marker in ("BUG:", "Kernel panic", "Oops:", "BP_REPLAY_TIMER_GUARD",
                   "scheduling while atomic",
                   "Segmentation fault", "RT throttling activated"):
        if marker in text:
            raise ValueError(f"contains kernel failure marker {marker!r}")
    retry_markers = len(re.findall(r"^TAGGED_REPLAY_RETRY ", text, re.MULTILINE))
    retry_pass = re.findall(r"TAGGED_REPLAY_CHILD PASS retries=(\d+)", text)
    if retry_pass != [str(retry_markers)]:
        raise ValueError("retry count does not match filtered attempts")

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
    for index, row in enumerate(rows):
        if row["hooks"] != row["enabled"]:
            raise ValueError(f"trial {index} has invalid hook count")
        if row["woken"] != 1:
            raise ValueError(f"trial {index} did not wake exactly one child")
        if row["wake_to_entry"] + row["load_cycles"] != row["wake_to_load"]:
            raise ValueError(f"trial {index} has inconsistent first-use timing")
        if row["wake_to_load"] > row["roundtrip"]:
            raise ValueError(f"trial {index} ends before first use")
        # PR_BP_PREVIEW_REPLAY_CONFIG sets the hardware clear bit before every
        # trial, so these are independent snapshots rather than deltas.
        expects_data = mode not in (
            "off", "instruction-select", "instruction-wake"
        )
        expected_triggers = row["enabled"] if expects_data else 0
        if row["triggers"] != expected_triggers or row["dropped"] != 0:
            raise ValueError(f"trial {index} has invalid trigger/drop counters")
        if row["enabled"] and expects_data:
            if row["admitted"] + row["filtered"] != config["lines"]:
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
            "Measure wake-time tagged data followed by selection-time "
            "instruction replay under the matched workload."
            if mode == "joint-split" else
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
        "filtered_attempts": retry_markers,
        "counter_deltas": {
            "admitted_entries": admitted,
            "filtered_entries": filtered,
            "accepted_triggers": accepted_triggers,
            "dropped_triggers": 0,
        },
        "metrics": {
            metric: (summarize_disabled_metric(rows, metric)
                     if mode == "off" else
                     summarize_metric(rows, metric, rng, bootstrap_samples))
            for metric in METRICS
        },
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
