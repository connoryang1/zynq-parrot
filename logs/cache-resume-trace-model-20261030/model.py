#!/usr/bin/env python3
"""Trace-driven timing model for Linux context-resume instruction recovery.

The demand sequence comes from the accepted physical miss-recorder logs.  The
model intentionally keeps the unmeasured detached full-line latency visible as
an input and labels its cycle-saving result as a proportional upper bound.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import heapq
import json
import lzma
import re
from pathlib import Path
from typing import Iterable


HEADER_RE = re.compile(r"^TRACE_HEADER\s+(.*)$")
RECORD_RE = re.compile(r"^TRACE_RECORD\s+(.*)$")
PRIVILEGED_START = 0x8000_0000
PRIVILEGED_END = 0x8100_0000
LINE_BYTES = 64
SETS = 64
WAYS = 8
COLD_INSTRUCTION_PENALTY_CYCLES = 6609.0


@dataclasses.dataclass(frozen=True)
class Record:
    seq: int
    side: str
    relative: int
    paddr: int


@dataclasses.dataclass(frozen=True)
class Trace:
    path: Path
    sha256: str
    header: dict[str, int]
    records: tuple[Record, ...]
    outcome: str | None


@dataclasses.dataclass(frozen=True)
class Timing:
    slots: int = 4
    first_beat_latency: int = 41
    beats_per_line: int = 8
    install_cycles: int = 19
    translation_cycles: int = 0


def parse_fields(text: str) -> dict[str, int | str]:
    result: dict[str, int | str] = {}
    for item in text.split():
        key, value = item.split("=", 1)
        result[key] = value if key == "side" else int(value, 0)
    return result


def parse_trace(path: Path) -> Trace:
    stored = path.read_bytes()
    data = lzma.decompress(stored) if path.suffix == ".xz" else stored
    header = None
    records: list[Record] = []
    outcome = None
    for raw in data.decode(errors="replace").splitlines():
        line = raw.replace("\r", "")
        match = HEADER_RE.match(line)
        if match:
            header = parse_fields(match.group(1))
            continue
        match = RECORD_RE.match(line)
        if match:
            values = parse_fields(match.group(1))
            records.append(
                Record(
                    seq=int(values["seq"]),
                    side=str(values["side"]),
                    relative=int(values["relative"]),
                    paddr=int(values["paddr"]),
                )
            )
            continue
        if line.startswith(("TRACE_PASS", "TRACE_TRUNCATED")):
            outcome = line.split()[0]
    if header is None:
        raise ValueError(f"{path}: missing TRACE_HEADER")
    expected = int(header["i_count"]) + int(header["d_count"])
    if len(records) != expected:
        raise ValueError(f"{path}: parsed {len(records)} records, expected {expected}")
    return Trace(
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        header={key: int(value) for key, value in header.items()},
        records=tuple(records),
        outcome=outcome,
    )


def instruction_records(trace: Trace) -> list[Record]:
    return [record for record in trace.records if record.side == "I"]


def split_training_trace(trace: Trace) -> dict[str, list[Record]]:
    boundary = trace.header["peer_begin"] - trace.header["start"]
    records = instruction_records(trace)
    return {
        "source_to_peer": [record for record in records if record.relative <= boundary],
        "peer_to_source": [record for record in records if record.relative > boundary],
    }


def ordered_unique(records: Iterable[Record], privileged_only: bool = False) -> list[int]:
    result = []
    seen = set()
    for record in records:
        address = record.paddr & ~(LINE_BYTES - 1)
        if privileged_only and not PRIVILEGED_START <= address < PRIVILEGED_END:
            continue
        if address not in seen:
            seen.add(address)
            result.append(address)
    return result


def per_set_recent_prefix(records: Iterable[Record]) -> list[int]:
    """Select the prior trace's eight MRU privileged lines per set.

    Selection models capacity; replay order remains prior first-use order so a
    stable scheduler prefix is not delayed behind its prior tail.
    """
    recency: dict[int, list[int]] = collections.defaultdict(list)
    first_order: list[int] = []
    first_seen = set()
    for record in records:
        address = record.paddr & ~(LINE_BYTES - 1)
        if not PRIVILEGED_START <= address < PRIVILEGED_END:
            continue
        cache_set = (address // LINE_BYTES) % SETS
        if address in recency[cache_set]:
            recency[cache_set].remove(address)
        recency[cache_set].append(address)
        recency[cache_set] = recency[cache_set][-WAYS:]
        if address not in first_seen:
            first_seen.add(address)
            first_order.append(address)
    selected = {address for lines in recency.values() for address in lines}
    return [address for address in first_order if address in selected]


def schedule_replay(addresses: list[int], trigger: int, timing: Timing) -> dict[int, dict[str, int]]:
    """Schedule ordered full-line reads, one response channel and one installer."""
    if timing.slots < 1:
        raise ValueError("slots must be positive")
    slot_free = [trigger + timing.translation_cycles] * timing.slots
    heapq.heapify(slot_free)
    next_issue = trigger + timing.translation_cycles
    response_channel_free = trigger
    installer_free = trigger
    schedule: dict[int, dict[str, int]] = {}
    for rank, address in enumerate(addresses):
        available = heapq.heappop(slot_free)
        issue = max(next_issue, available)
        first_beat = max(issue + timing.first_beat_latency, response_channel_free)
        final_beat = first_beat + timing.beats_per_line
        response_channel_free = final_beat
        heapq.heappush(slot_free, final_beat)
        install_start = max(final_beat, installer_free)
        ready = install_start + timing.install_cycles
        installer_free = ready
        next_issue = issue + 1
        schedule[address] = {
            "rank": rank,
            "issue": issue,
            "first_beat": first_beat,
            "final_beat": final_beat,
            "install_start": install_start,
            "ready": ready,
        }
    return schedule


def evaluate(
    name: str,
    demand_records: list[Record],
    replay_addresses: list[int],
    trigger: int,
    timing: Timing,
    retained_addresses: Iterable[int] = (),
    notes: Iterable[str] = (),
) -> dict:
    retained = {address & ~(LINE_BYTES - 1) for address in retained_addresses}
    replay = [address for address in replay_addresses if address not in retained]
    schedule = schedule_replay(replay, trigger, timing)
    ready_by = {address: trigger for address in retained}
    ready_by.update({address: event["ready"] for address, event in schedule.items()})
    demand_lines = [record.paddr & ~(LINE_BYTES - 1) for record in demand_records]
    first_demand: dict[int, int] = {}
    for record, address in zip(demand_records, demand_lines):
        first_demand.setdefault(address, record.relative)
    predicted = retained | set(replay_addresses)
    used_predicted = predicted & set(first_demand)
    ready_unique = {
        address
        for address in used_predicted
        if ready_by.get(address, 1 << 60) <= first_demand[address]
    }
    late_unique = used_predicted - ready_unique
    unused = predicted - set(first_demand)
    ready_records = 0
    late_records = 0
    uncovered_records = 0
    for record, address in zip(demand_records, demand_lines):
        if address not in predicted:
            uncovered_records += 1
        elif ready_by.get(address, 1 << 60) <= record.relative:
            ready_records += 1
        else:
            late_records += 1
    return {
        "mechanism": name,
        "trigger_cycle": trigger,
        "timing": dataclasses.asdict(timing),
        "demand_records": len(demand_records),
        "demand_unique_lines": len(first_demand),
        "predicted_lines": len(predicted),
        "retained_lines": len(retained),
        "issued_lines": len(schedule),
        "ready_before_first_demand_unique": len(ready_unique),
        "late_at_first_demand_unique": len(late_unique),
        "unused_predicted_unique": len(unused),
        "uncovered_unique": len(set(first_demand) - predicted),
        "ready_demand_records": ready_records,
        "late_demand_records": late_records,
        "uncovered_demand_records": uncovered_records,
        "first_ready_cycle": min(ready_by.values()) if ready_by else None,
        "last_ready_cycle": max(ready_by.values()) if ready_by else None,
        "notes": list(notes),
    }


def mechanism_rows(
    window: str,
    demand: list[Record],
    training: list[Record],
    timing: Timing,
    fixed_shared_prefix: list[int] | None = None,
    dispatch_lead: int = 6,
    shared_trigger: int = 0,
) -> list[dict]:
    demand_order = ordered_unique(demand)
    training_order = ordered_unique(training)
    shared_prefix = per_set_recent_prefix(training)
    first_demand = min(record.relative for record in demand)
    dispatch_trigger = max(0, first_demand - dispatch_lead)
    rows = [
        evaluate(
            "dispatch_replay_oracle_order",
            demand,
            demand_order,
            dispatch_trigger,
            timing,
            notes=(
                "Optimistic address-order ceiling; dispatch does not actually know the future demand sequence.",
                f"Trigger is {dispatch_lead} cycles before the first measured demand.",
            ),
        ),
        evaluate(
            "syscall_shared_prefix",
            demand,
            shared_prefix,
            shared_trigger,
            timing,
            notes=(
                "Prediction is the preceding full-window trace's privileged eight-MRU-lines-per-set set in prior first-use order.",
                "Trigger cycle zero represents syscall/scheduler entry.",
            ),
        ),
    ]
    if fixed_shared_prefix is not None:
        rows.append(
            evaluate(
                "syscall_fixed_shared_prefix",
                demand,
                fixed_shared_prefix,
                shared_trigger,
                timing,
                notes=(
                    "Prediction is one eight-MRU-lines-per-set table trained on the complete preceding run.",
                    "The same immutable table and replay order are used for both handoff directions.",
                ),
            )
        )
    for count in (1, 2, 4):
        rows.append(
            evaluate(
                f"trained_retention_{count}",
                demand,
                [],
                0,
                timing,
                retained_addresses=training_order[:count],
                notes=("Retained lines are the preceding trace phase's first unique instruction lines.",),
            )
        )
    rows.append(
        evaluate(
            "hybrid_shared_plus_oracle_retention_4",
            demand,
            shared_prefix,
            shared_trigger,
            timing,
            retained_addresses=demand_order[:4],
            notes=(
                "Shared prefix is trace-trained; four immediately needed retained lines are an oracle upper bound.",
                "This separates the value of immediate retention from background replay.",
            ),
        )
    )
    for row in rows:
        row["window"] = window
    return rows


def aggregate_rows(rows_by_window: dict[str, list[dict]]) -> list[dict]:
    mechanisms = [row["mechanism"] for row in next(iter(rows_by_window.values()))]
    total_records = sum(
        row["demand_records"]
        for row in [values[0] for values in rows_by_window.values()]
    )
    result = []
    for mechanism in mechanisms:
        selected = [
            next(row for row in window_rows if row["mechanism"] == mechanism)
            for window_rows in rows_by_window.values()
        ]
        ready_records = sum(row["ready_demand_records"] for row in selected)
        result.append(
            {
                "mechanism": mechanism,
                "ready_before_demand_unique": sum(
                    row["ready_before_first_demand_unique"] for row in selected
                ),
                "late_unique": sum(row["late_at_first_demand_unique"] for row in selected),
                "unused_unique": sum(row["unused_predicted_unique"] for row in selected),
                "uncovered_unique": sum(row["uncovered_unique"] for row in selected),
                "ready_demand_records": ready_records,
                "total_demand_records": total_records,
                "potential_cold_penalty_coverage": ready_records / total_records,
                "prediction_useful_fraction": (
                    1.0
                    - sum(row["unused_predicted_unique"] for row in selected)
                    / sum(row["predicted_lines"] for row in selected)
                    if sum(row["predicted_lines"] for row in selected)
                    else None
                ),
                "prediction_timely_fraction": (
                    sum(row["ready_before_first_demand_unique"] for row in selected)
                    / sum(row["predicted_lines"] for row in selected)
                    if sum(row["predicted_lines"] for row in selected)
                    else None
                ),
                "proportional_upper_bound_cycles_saved":
                    COLD_INSTRUCTION_PENALTY_CYCLES * ready_records / total_records,
            }
        )
    return result


def build_result(raw_dir: Path) -> dict:
    paths = {
        "source_to_peer": raw_dir / "cache-miss-trace-to-peer.log.xz",
        "peer_to_source": raw_dir / "cache-miss-trace-from-peer.log.xz",
        "training": raw_dir / "cache-miss-trace-pass-1.log.xz",
    }
    traces = {name: parse_trace(path) for name, path in paths.items()}
    expected_hashes = {
        "source_to_peer": "47cddccb742f3068f3053f5d231252d308ce808474735f756e31662392d76152",
        "peer_to_source": "d40f789a1d38d5f3f8d87702f1ca491e81055e8348a1f8c298dbe48552f70377",
        "training": "c2e44955e4eac46bee0569648ed9c50a651b1e9194d14023a998a84be3eaa175",
    }
    for name, expected in expected_hashes.items():
        if traces[name].sha256 != expected:
            raise ValueError(f"{name}: SHA-256 {traces[name].sha256}, expected {expected}")
    demand = {
        "source_to_peer": instruction_records(traces["source_to_peer"]),
        "peer_to_source": instruction_records(traces["peer_to_source"]),
    }
    training = split_training_trace(traces["training"])
    fixed_shared_prefix = per_set_recent_prefix(
        instruction_records(traces["training"])
    )
    privileged_instruction_records = sum(
        1
        for records in demand.values()
        for record in records
        if PRIVILEGED_START <= record.paddr < PRIVILEGED_END
    )
    if privileged_instruction_records != 153:
        raise ValueError(
            "privileged address classification no longer reproduces 153/157"
        )

    primary_timing = Timing()
    primary = {
        window: mechanism_rows(
            window,
            demand[window],
            training[window],
            primary_timing,
            fixed_shared_prefix=fixed_shared_prefix,
        )
        for window in demand
    }

    sensitivity = []
    for latency in (41, 57, 82, 164, 200):
        for slots in (1, 2, 4, 5):
            for install in (17, 19, 25):
                timing = Timing(
                    slots=slots,
                    first_beat_latency=latency,
                    install_cycles=install,
                )
                rows = {
                    window: mechanism_rows(
                        window,
                        demand[window],
                        training[window],
                        timing,
                        fixed_shared_prefix=fixed_shared_prefix,
                    )
                    for window in demand
                }
                for aggregate in aggregate_rows(rows):
                    sensitivity.append(
                        {
                            "first_beat_latency": latency,
                            "slots": slots,
                            "install_cycles": install,
                            **aggregate,
                        }
                    )

    trigger_sensitivity = []
    for trigger in (0, 256, 1000, 2177, 2238):
        rows = {
            window: mechanism_rows(
                window,
                demand[window],
                training[window],
                primary_timing,
                fixed_shared_prefix=fixed_shared_prefix,
                shared_trigger=trigger,
            )
            for window in demand
        }
        shared = next(
            row
            for row in aggregate_rows(rows)
            if row["mechanism"] == "syscall_shared_prefix"
        )
        trigger_sensitivity.append({"shared_prefix_trigger_cycle": trigger, **shared})

    translation_sensitivity = []
    for translation in (0, 41, 82, 164):
        timing = dataclasses.replace(primary_timing, translation_cycles=translation)
        rows = {
            window: mechanism_rows(
                window,
                demand[window],
                training[window],
                timing,
                fixed_shared_prefix=fixed_shared_prefix,
            )
            for window in demand
        }
        for mechanism in ("syscall_shared_prefix", "dispatch_replay_oracle_order"):
            aggregate = next(
                row for row in aggregate_rows(rows) if row["mechanism"] == mechanism
            )
            translation_sensitivity.append(
                {"translation_cycles": translation, **aggregate}
            )

    dispatch_lead_sensitivity = []
    for lead in (6, 57, 256, 1000, 2238):
        rows = {
            window: mechanism_rows(
                window,
                demand[window],
                training[window],
                primary_timing,
                fixed_shared_prefix=fixed_shared_prefix,
                dispatch_lead=lead,
            )
            for window in demand
        }
        dispatch = next(
            row
            for row in aggregate_rows(rows)
            if row["mechanism"] == "dispatch_replay_oracle_order"
        )
        dispatch_lead_sensitivity.append({"dispatch_lead_cycles": lead, **dispatch})

    return {
        "purpose": "Compare trace-timed dispatch replay, shared-prefix replay, retention, and a hybrid before selecting RTL.",
        "input_identity": {
            name: {
                "path": str(trace.path),
                "sha256": trace.sha256,
                "outcome": trace.outcome,
                "instruction_records": len(instruction_records(trace)),
            }
            for name, trace in traces.items()
        },
        "measured_inputs": {
            "demand_addresses_and_deadlines": "physical PYNQ-Z2 Linux accepted-miss records",
            "instruction_demand_records": sum(len(records) for records in demand.values()),
            "privileged_instruction_records": privileged_instruction_records,
            "cache_line_bytes": LINE_BYTES,
            "cache_sets": SETS,
            "cache_ways": WAYS,
            "fixed_shared_prefix_lines": len(fixed_shared_prefix),
            "fpga_facing_installer_median_cycles": 19,
            "fpga_facing_installer_observed_max_cycles": 25,
            "cold_instruction_penalty_cycles": COLD_INSTRUCTION_PENALTY_CYCLES,
        },
        "fixed_shared_prefix": {
            "policy": "eight MRU privileged instruction lines per cache set from the complete preceding run, replayed in prior first-use order",
            "line_count": len(fixed_shared_prefix),
            "lines": [
                {
                    "rank": rank,
                    "paddr": address,
                    "paddr_hex": f"0x{address:016x}",
                    "cache_set": (address // LINE_BYTES) % SETS,
                }
                for rank, address in enumerate(fixed_shared_prefix)
            ],
        },
        "primary_assumptions": {
            **dataclasses.asdict(primary_timing),
            "first_beat_latency_status": "41 cycles is a physical demand load-to-use proxy, not a measured detached full-line endpoint",
            "response_channel": "one serialized eight-beat 64-byte channel",
            "installer": "one demand-independent serial instruction-line installer",
            "translation": "zero-cycle optimistic hit; translation delay is exposed by Timing",
            "demand_priority": "a replay line counts only if installed by its recorded demand; the fixed baseline demand timeline is not rescheduled",
        },
        "primary_by_window": primary,
        "primary_table": aggregate_rows(primary),
        "trigger_sensitivity": trigger_sensitivity,
        "translation_sensitivity": translation_sensitivity,
        "dispatch_lead_sensitivity": dispatch_lead_sensitivity,
        "timing_sensitivity": sensitivity,
        "limits": [
            "The recorder timestamps accepted demand requests, not response completion or stall release.",
            "The model does not feed predicted savings back into later demand timestamps; rows are coverage comparisons, not a cycle-accurate Linux execution replay.",
            "The proportional cycle estimate scales the measured 6,609-cycle cold-instruction penalty by covered demand records and is an upper bound, not a measured speedup.",
            "Dispatch replay uses oracle future address order to isolate timing; real prediction can only be worse.",
            "Hybrid retention uses the current trace's first four lines as an oracle upper bound; trained retention rows show the preceding-trace result.",
            "Physical detached full-line latency and an instruction-cache installer remain unmeasured and unimplemented.",
            "The two sliced demand windows are independent fresh boots; their sum matches the complete run within 1.01 percent but is not one continuous execution.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(__file__).with_name("raw"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("results.json"),
    )
    args = parser.parse_args()
    result = build_result(args.raw_dir)
    text = json.dumps(result, indent=2) + "\n"
    args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
