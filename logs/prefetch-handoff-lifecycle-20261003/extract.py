#!/usr/bin/env python3
"""Extract repeated-handoff prefetch state from the preserved FST."""
import json
import os
import statistics
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FST = HERE / "lifecycle.fst"
WANT_DCACHE = {
    "prefetch_buffer_v_r",
    "prefetch_buffer_hit_tv", "prefetch_buffer_write",
    "prefetch_buffer_write_match", "prefetch_buffer_write_slot",
    "prefetch_buffer_replace_r", "prefetch_req",
}
WANT_UCE = {
    "prefetch_valid_r", "prefetch_sent_r", "prefetch_sent_count",
    "prefetch_demand_match", "prefetch_drop",
    "cache_req_v_i", "cache_req_yumi_o",
}

EVENTS = HERE / "events.txt"
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
                        or (ref in WANT_UCE and ".dcache_uce." in full)):
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

    found = {name.rsplit(".", 1)[-1].split("[")[0]
             for name in ids.values()}
    missing = (WANT_DCACHE | WANT_UCE) - found
    if missing:
        raise SystemExit(f"missing signals: {sorted(missing)}")

    with EVENTS.open("w") as out:
        for time, name, value in events:
            out.write(f"{time} {name} {value}\n")

def times_for(suffix, asserted="1"):
    return [t for t, name, value in events
            if name.rsplit(".", 1)[-1].split("[")[0] == suffix
            and value == asserted]

hits = times_for("prefetch_buffer_hit_tv")
writes = times_for("prefetch_buffer_write")
requests = times_for("prefetch_req")
drops = times_for("prefetch_drop")
demand_matches = times_for("prefetch_demand_match")

# Six epochs are separated by a displacement sweep. Split at the five largest
# hit-to-hit gaps so this remains independent of a guessed cycle threshold.
gaps = [(hits[i] - hits[i - 1], i) for i in range(1, len(hits))]
cuts = sorted(i for _, i in sorted(gaps, reverse=True)[:5])
groups, begin = [], 0
for end in cuts + [len(hits)]:
    groups.append(hits[begin:end])
    begin = end

def count_between(samples, lo, hi):
    return sum(lo <= value <= hi for value in samples)

def signal_events(suffix):
    return [(t, value) for t, name, value in events
            if name.rsplit(".", 1)[-1].split("[")[0] == suffix]

def state_at(samples, time):
    state = None
    for event_time, value in samples:
        if event_time > time:
            break
        state = value
    return state

def ones(value):
    return value.count("1") if value is not None else None

side_valid = signal_events("prefetch_buffer_v_r")
uce_valid = signal_events("prefetch_valid_r")
uce_sent = signal_events("prefetch_sent_r")
split_times = [(hits[index - 1] + hits[index]) // 2 for index in cuts]
range_starts = [requests[0]] + [value + 1 for value in split_times]
range_ends = split_times + [events[-1][0]]

epochs = []
for number, (group, lo, hi) in enumerate(
        zip(groups, range_starts, range_ends), 1):
    window_values = lambda samples: [state_at(samples, lo - 1)] + [
        value for time, value in samples if lo <= time <= hi]
    epochs.append({
        "epoch": number,
        "first_hit_time": group[0],
        "last_hit_time": group[-1],
        "side_buffer_hits": len(group),
        "side_buffer_writes": count_between(writes, lo, hi),
        "prefetch_requests": count_between(requests, lo, hi),
        "uce_drops": count_between(drops, lo, hi),
        "uce_demand_matches": count_between(demand_matches, lo, hi),
        "maximum_side_buffer_valid_entries": max(
            ones(value) for value in window_values(side_valid) if value is not None),
        "maximum_uce_valid_entries": max(
            ones(value) for value in window_values(uce_valid) if value is not None),
        "maximum_uce_sent_entries": max(
            ones(value) for value in window_values(uce_sent) if value is not None),
        "end_side_buffer_valid_entries": ones(state_at(side_valid, hi)),
        "end_uce_valid_entries": ones(state_at(uce_valid, hi)),
        "end_uce_sent_entries": ones(state_at(uce_sent, hi)),
    })

summary = {
    "signal_count": len(ids),
    "event_count": len(events),
    "total": {
        "side_buffer_hits": len(hits),
        "side_buffer_writes": len(writes),
        "prefetch_requests": len(requests),
        "uce_drops": len(drops),
        "uce_demand_matches": len(demand_matches),
    },
    "five_largest_hit_gaps": sorted((gap for gap, _ in gaps), reverse=True)[:5],
    "median_intra_epoch_hit_gap": statistics.median(
        gap for gap, index in gaps if index not in cuts
    ),
    "epochs": epochs,
}
if len(groups) != 6 or any(epoch["side_buffer_hits"] != 512
                           or epoch["prefetch_requests"] != 512
                           or epoch["side_buffer_writes"] != 1024
                           or epoch["uce_drops"] != 0
                           for epoch in epochs):
    raise SystemExit("unexpected per-epoch lifecycle counts")
(HERE / "analysis.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, indent=2, sort_keys=True))
