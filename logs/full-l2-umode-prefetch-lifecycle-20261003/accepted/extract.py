#!/usr/bin/env python3
"""Extract translated repeated-handoff prefetch state from the FST."""
import json
import os
import statistics
import subprocess
from bisect import bisect_right
from pathlib import Path

HERE = Path(__file__).resolve().parent
FST = HERE / "dump.fst"
EVENTS = HERE / "events.txt"
WANT_DCACHE = {
    "prefetch_buffer_v_r", "prefetch_buffer_hit_tv",
    "prefetch_buffer_write", "prefetch_req",
}
WANT_UCE = {"prefetch_valid_r", "prefetch_sent_r", "prefetch_drop"}
WANT_PIPE = {
    "prefetch_mmu_r", "dtlb_v_lo", "dtlb_load_miss_lo",
    "prefetch_ptag_allowed", "eaddr",
}
SIM_TIME_PER_CORE_CYCLE = 50000

def short(name):
    return name.rsplit(".", 1)[-1].split("[")[0]

if os.environ.get("REUSE_EVENTS"):
    events = []
    for line in EVENTS.read_text().splitlines():
        time, name, value = line.split()
        events.append((int(time), name, value))
    ids = {name: name for _, name, _ in events}
else:
    proc = subprocess.Popen(
        ["fst2vcd", str(FST)], stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="ascii",
        errors="replace", bufsize=1,
    )
    scopes, ids, events = [], {}, []
    timestamp = 0
    header = True
    for raw in proc.stdout:
        line = raw.strip()
        if header:
            if line.startswith("$scope "):
                scopes.append(line.split()[2])
            elif line.startswith("$upscope"):
                scopes.pop()
            elif line.startswith("$var "):
                fields = line.split()
                ident, ref = fields[3], fields[4]
                full = ".".join(scopes + [ref])
                if ((ref in WANT_DCACHE and ".pipe_mem.dcache." in full)
                        or (ref in WANT_UCE and ".dcache_uce." in full)
                        or (ref in WANT_PIPE and ".pipe_mem." in full
                            and ".pipe_mem.dcache." not in full)):
                    ids[ident] = full
            elif line.startswith("$enddefinitions"):
                header = False
            continue
        if line.startswith("#"):
            timestamp = int(line[1:])
        elif line and line[0] in "01xz":
            ident, value = line[1:], line[0]
            if ident in ids:
                events.append((timestamp, ids[ident], value))
        elif line.startswith("b"):
            fields = line.split()
            if len(fields) == 2 and fields[1] in ids:
                events.append((timestamp, ids[fields[1]], fields[0][1:]))
    if proc.wait():
        raise SystemExit("fst2vcd failed")
    found = {short(name) for name in ids.values()}
    missing = (WANT_DCACHE | WANT_UCE | WANT_PIPE) - found
    if missing:
        raise SystemExit(f"missing signals: {sorted(missing)}")
    with EVENTS.open("w") as out:
        for time, name, value in events:
            out.write(f"{time} {name} {value}\n")

def signal_events(suffix):
    selected = [(time, value) for time, name, value in events
                if short(name) == suffix]
    return ([item[0] for item in selected], [item[1] for item in selected])

def asserted_times(suffix):
    times, values = signal_events(suffix)
    return [time for time, value in zip(times, values) if value == "1"]

def state_at(samples, time):
    times, values = samples
    index = bisect_right(times, time) - 1
    return values[index] if index >= 0 else None

def integer(value):
    if value is None or "x" in value or "z" in value:
        return None
    return int(value, 2)

def ones(value):
    return value.count("1") if value is not None else None

def count_between(samples, lo, hi):
    return sum(lo <= value <= hi for value in samples)

def latency_summary(start_times, end_times):
    if len(start_times) != len(end_times):
        raise SystemExit("cannot pair latency events")
    values = sorted((end - start) // SIM_TIME_PER_CORE_CYCLE
                    for start, end in zip(start_times, end_times))
    return {
        "minimum_cycles": values[0],
        "median_cycles": statistics.median(values),
        "p95_cycles": values[round((len(values) - 1) * 0.95)],
        "maximum_cycles": values[-1],
        "mean_cycles": statistics.mean(values),
    }

all_attempts = asserted_times("prefetch_mmu_r")
requests = asserted_times("prefetch_req")
hits = asserted_times("prefetch_buffer_hit_tv")
writes = asserted_times("prefetch_buffer_write")
drops = asserted_times("prefetch_drop")
if len(all_attempts) < 6:
    raise SystemExit("too few prefetch instructions")
# A boot-time ORI can match the hint encoding before the program enters its
# lifecycle loop. Discard everything before the uniquely largest gap, then use
# the next five long gaps to split the six launches.
all_gaps = [(all_attempts[i] - all_attempts[i - 1], i)
            for i in range(1, len(all_attempts))]
preamble_gap, lifecycle_begin = max(all_gaps)
instructions = all_attempts[lifecycle_begin:]
gaps = [(instructions[i] - instructions[i - 1], i)
        for i in range(1, len(instructions))]
cuts = sorted(index for _, index in sorted(gaps, reverse=True)[:5])
groups, begin = [], 0
for end in cuts + [len(instructions)]:
    groups.append(instructions[begin:end])
    begin = end
split_times = [(instructions[index - 1] + instructions[index]) // 2
               for index in cuts]
starts = [instructions[0]] + [value + 1 for value in split_times]
ends = split_times + [events[-1][0]]

dtlb_v = signal_events("dtlb_v_lo")
dtlb_miss = signal_events("dtlb_load_miss_lo")
ptag_allowed = signal_events("prefetch_ptag_allowed")
eaddr = signal_events("eaddr")
side_valid = signal_events("prefetch_buffer_v_r")
uce_valid = signal_events("prefetch_valid_r")
uce_sent = signal_events("prefetch_sent_r")

epochs = []
for number, (group, lo, hi) in enumerate(zip(groups, starts, ends), 1):
    def values_in(samples):
        return [state_at(samples, lo - 1)] + [
            value for time, value in zip(*samples) if lo <= time <= hi]
    attempts = []
    for time in group:
        attempts.append({
            "hit": integer(state_at(dtlb_v, time)),
            "miss": integer(state_at(dtlb_miss, time)),
            "allowed": integer(state_at(ptag_allowed, time)),
            "address": integer(state_at(eaddr, time)),
        })
    miss_pages = sorted({item["address"] >> 12 for item in attempts
                         if item["miss"] == 1 and item["address"] is not None})
    request_times = [time for time in requests if lo <= time <= hi]
    write_times = [time for time in writes if lo <= time <= hi]
    hit_times = [time for time in hits if lo <= time <= hi]
    responses = len(write_times)
    useful_hits = count_between(hits, lo, hi)
    epochs.append({
        "epoch": number,
        "logical_prefetch_hints_from_checked_program": 512,
        "translation_stage_attempts_including_replays": len(group),
        "translation_stage_hit_attempts": sum(item["hit"] == 1
                                               for item in attempts),
        "translation_stage_miss_attempts": sum(item["miss"] == 1
                                                for item in attempts),
        "translation_stage_allowed_attempts": sum(item["allowed"] == 1
                                                   for item in attempts),
        "dtlb_miss_virtual_pages": [f"0x{page:x}" for page in miss_pages],
        "dcache_prefetch_request_episodes": len(request_times),
        "detached_prefetches_completed_and_consumed": useful_hits,
        "side_buffer_write_episodes": responses,
        "side_buffer_hits": useful_hits,
        "logical_hints_without_useful_detached_completion": 512 - useful_hits,
        "request_to_side_buffer_write": latency_summary(request_times, write_times),
        "side_buffer_write_to_demand": latency_summary(write_times, hit_times),
        "request_to_demand": latency_summary(request_times, hit_times),
        "uce_drops": count_between(drops, lo, hi),
        "maximum_side_buffer_valid_entries": max(
            ones(value) for value in values_in(side_valid) if value is not None),
        "maximum_uce_valid_entries": max(
            ones(value) for value in values_in(uce_valid) if value is not None),
        "maximum_uce_sent_entries": max(
            ones(value) for value in values_in(uce_sent) if value is not None),
        "end_side_buffer_valid_entries": ones(state_at(side_valid, hi)),
        "end_uce_valid_entries": ones(state_at(uce_valid, hi)),
        "end_uce_sent_entries": ones(state_at(uce_sent, hi)),
    })

summary = {
    "signal_count": len(ids),
    "event_count": len(events),
    "discarded_preamble_prefetch_attempts": lifecycle_begin,
    "preamble_to_lifecycle_gap": preamble_gap,
    "five_largest_instruction_gaps": sorted(
        (gap for gap, _ in gaps), reverse=True)[:5],
    "median_intra_epoch_instruction_gap": statistics.median(
        gap for gap, index in gaps if index not in cuts),
    "total": {
        "logical_prefetch_hints_from_checked_program": 512 * len(epochs),
        "translation_stage_attempts_including_replays": len(instructions),
        "dcache_prefetch_request_episodes": sum(
            e["dcache_prefetch_request_episodes"] for e in epochs),
        "detached_prefetches_completed_and_consumed": sum(
            e["detached_prefetches_completed_and_consumed"] for e in epochs),
        "side_buffer_write_episodes": len(writes),
        "side_buffer_hits": len(hits),
        "useful_hint_fraction": len(hits) / (512 * len(epochs)),
        "uce_drops": len(drops),
    },
    "epochs": epochs,
}
(HERE / "analysis.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, indent=2, sort_keys=True))
if len(epochs) != 6 or any(
        epoch["logical_prefetch_hints_from_checked_program"] != 512
        or epoch["uce_drops"] != 0
        or epoch["side_buffer_write_episodes"] != epoch["side_buffer_hits"]
        or epoch["dcache_prefetch_request_episodes"] != epoch["side_buffer_hits"]
        or epoch["detached_prefetches_completed_and_consumed"] != epoch["side_buffer_hits"]
        or epoch["end_side_buffer_valid_entries"] != 0
        or epoch["end_uce_valid_entries"] != 0
        or epoch["end_uce_sent_entries"] != 0
        for epoch in epochs):
    raise SystemExit("unexpected translated lifecycle result")
