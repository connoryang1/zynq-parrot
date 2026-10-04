#!/usr/bin/env python3
"""Summarize completed lifecycle epochs in a host-time-limited trace.

The ordinary lifecycle analyzer assumes six complete epochs.  This variant
uses only the retained selected-signal event stream, treats gaps over 100
million simulator time units as epoch boundaries, and labels the final group
partial when the trace ends before the next boundary.
"""
import json
import statistics
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVENTS = HERE / "events.txt"
CORE_CYCLE_TIME = 50_000
BOUNDARY_GAP = 100_000_000


def short(name):
    return name.rsplit(".", 1)[-1].split("[")[0]


signals = defaultdict(list)
last_time = 0
for line in EVENTS.read_text().splitlines():
    timestamp, name, value = line.split()
    timestamp = int(timestamp)
    signals[short(name)].append((timestamp, value))
    last_time = timestamp


def asserted(name):
    return [time for time, value in signals[name] if value == "1"]


def state_at(name, timestamp):
    samples = signals[name]
    index = bisect_right(samples, (timestamp, "~")) - 1
    return samples[index][1] if index >= 0 else None


def integer(value):
    if value is None or "x" in value or "z" in value:
        return None
    return int(value, 2)


def occupancy(name, lo, hi):
    values = [state_at(name, lo - 1)]
    values += [value for time, value in signals[name] if lo <= time <= hi]
    return max(value.count("1") for value in values if value is not None)


all_attempts = asserted("prefetch_mmu_r")
all_gaps = [(all_attempts[i] - all_attempts[i - 1], i)
            for i in range(1, len(all_attempts))]
preamble_gap, lifecycle_begin = max(all_gaps)
attempts = all_attempts[lifecycle_begin:]
gaps = [(attempts[i] - attempts[i - 1], i)
        for i in range(1, len(attempts))]
cuts = [index for gap, index in gaps if gap > BOUNDARY_GAP]
split_times = [(attempts[index - 1] + attempts[index]) // 2
               for index in cuts]
groups = []
begin = 0
for end in cuts + [len(attempts)]:
    groups.append(attempts[begin:end])
    begin = end
starts = [attempts[0]] + [time + 1 for time in split_times]
ends = split_times + [last_time]

epochs = []
for number, (group, lo, hi) in enumerate(zip(groups, starts, ends), 1):
    attempt_state = [{
        "hit": integer(state_at("dtlb_v_lo", time)),
        "miss": integer(state_at("dtlb_load_miss_lo", time)),
        "allowed": integer(state_at("prefetch_ptag_allowed", time)),
        "address": integer(state_at("eaddr", time)),
    } for time in group]
    count = lambda name: sum(lo <= time <= hi for time in asserted(name))
    response_beats = count("prefetch_buffer_write")
    hits = count("prefetch_buffer_hit_tv")
    epochs.append({
        "epoch": number,
        "complete_boundary_observed": number <= len(cuts),
        "translation_stage_attempts_including_replays": len(group),
        "translation_stage_hit_attempts": sum(x["hit"] == 1 for x in attempt_state),
        "translation_stage_miss_attempts": sum(x["miss"] == 1 for x in attempt_state),
        "translation_stage_allowed_attempts": sum(x["allowed"] == 1 for x in attempt_state),
        "dtlb_miss_virtual_pages": [f"0x{page:x}" for page in sorted({
            x["address"] >> 12 for x in attempt_state
            if x["miss"] == 1 and x["address"] is not None})],
        "dcache_prefetch_request_attempts": count("prefetch_req"),
        "side_buffer_response_beats": response_beats,
        "detached_prefetches_completed": response_beats // 2,
        "side_buffer_hits": hits,
        "uce_drops": count("prefetch_drop"),
        "maximum_side_buffer_valid_entries": occupancy("prefetch_buffer_v_r", lo, hi),
        "maximum_uce_valid_entries": occupancy("prefetch_valid_r", lo, hi),
        "maximum_uce_sent_entries": occupancy("prefetch_sent_r", lo, hi),
        "end_side_buffer_valid_entries": state_at("prefetch_buffer_v_r", hi).count("1"),
        "end_uce_valid_entries": state_at("prefetch_valid_r", hi).count("1"),
        "end_uce_sent_entries": state_at("prefetch_sent_r", hi).count("1"),
        "active_span_cycles": (group[-1] - group[0]) // CORE_CYCLE_TIME,
    })

summary = {
    "result": "host wall-time limit before guest verdict",
    "last_trace_time": last_time,
    "last_trace_core_cycle": last_time // CORE_CYCLE_TIME,
    "discarded_preamble_prefetch_attempts": lifecycle_begin,
    "preamble_to_lifecycle_gap": preamble_gap,
    "epoch_boundary_gaps_cycles": [gap // CORE_CYCLE_TIME for gap, _ in gaps
                                    if gap > BOUNDARY_GAP],
    "median_intra_epoch_attempt_gap_cycles": statistics.median(
        gap // CORE_CYCLE_TIME for gap, _ in gaps if gap <= BOUNDARY_GAP),
    "epochs": epochs,
}
(HERE / "partial-analysis.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, indent=2, sort_keys=True))
