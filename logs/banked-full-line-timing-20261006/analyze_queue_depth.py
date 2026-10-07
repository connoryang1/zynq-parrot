#!/usr/bin/env python3
"""Explain the four-slot collapse from the retained exact event trace."""

import collections
import hashlib
import json
import lzma
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
VCD = HERE / "events-k4.vcd.xz"
RUN_LOG = HERE / "k4-trace-run.log"
TEN_SLOT_RESULTS = HERE / "results.json"

EXPECTED_VCD_SHA256 = "f42821bdc0321c4910fc7a661d1c70bddea275f083b92991d17d7cd3edbff53d"
EXPECTED_RUN_SHA256 = "c803e3475479959fd5f0dcc5fb3f2bf9a1fd845a698c2bb823820b4bc4536427"
BEGIN_PC = 0x80000C90
END_PC = 0x80000C9C
HINT_PC = 0x800005A4
MEASURED_NODES_BASE = 0x8000D000

# These are the three 11-node slices embedded in the exact ELF. They are
# retained here rather than regenerated from a mutable source checkout.
EXPECTED_NODE_INDICES = (
    (1081, 605, 648, 958, 1255, 789, 764, 494, 759, 185, 592),
    (212, 68, 47, 201, 471, 857, 135, 202, 861, 570, 264),
    (395, 847, 1024, 285, 141, 60, 716, 92, 43, 216, 722),
)

IDS = {
    "core_clk": "3!", "uce_clk": "M'", "instret": "q)", "pc": "t)",
    "thread": "=,", "addr": "&'", "araddr": "[!",
    "prefetch_v": "Qa!", "free_v": "na!", "duplicate": "pa!",
    "accept": "#b!", "drop": "%b!", "valid": "Ra!", "complete": "Ua!",
    "allocate": "$b!", "free_slot": "qa!", "issue": "ta!",
    "issue_slot": "ra!", "response": "ua!", "response_slot": "wa!",
    "install_state": "id!", "install_slot": "jd!",
    "tag_v": "9'", "tag_y": ":'", "arvalid": "\\!", "arready": "]!",
    "arid": "^!", "rvalid": "b!", "rready": "c!", "rid": "d!",
    "rlast": "e!",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integer(value):
    if value is None or not value or set(value.lower()) & set("xz"):
        return None
    return int(value, 2)


def read_samples():
    values = {}
    old_clock = {IDS["core_clk"]: None, IDS["uce_clk"]: None}
    sampled = {"core": [], "uce": []}
    timestamp = None
    changes = []

    def flush():
        nonlocal changes
        if timestamp is None:
            return
        for identifier, value in changes:
            values[identifier] = value
        for domain, clock_name in (("core", "core_clk"), ("uce", "uce_clk")):
            identifier = IDS[clock_name]
            value = values.get(identifier)
            if value == "1" and old_clock[identifier] == "0":
                sampled[domain].append(
                    (timestamp, {name: integer(values.get(ident)) for name, ident in IDS.items()})
                )
            old_clock[identifier] = value
        changes = []

    with lzma.open(VCD, "rt") as source:
        for raw in source:
            line = raw.strip()
            if not line or line.startswith("$"):
                continue
            if line.startswith("#"):
                flush()
                timestamp = int(line[1:])
            elif line.startswith("b"):
                parts = line.split()
                if len(parts) == 2:
                    changes.append((parts[1], parts[0][1:]))
            else:
                changes.append((line[1:], line[0]))
        flush()
    return sampled


def cycle(timestamp, begin, period):
    return (timestamp - begin) / period


def summary(values):
    counts = collections.Counter(values)
    return {
        "count": len(values),
        "minimum": min(values),
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "maximum": max(values),
        "distribution": {str(value): count for value, count in sorted(counts.items())},
    }


def parse_run_cycles():
    text = RUN_LOG.read_text()
    match = re.search(
        r"Benchmark: DEPENDENT mode=0x0*3 streams=0x0*3 nodes=0x0*21 cycles=0x([0-9a-fA-F]+)",
        text,
    )
    if not match or "[BSG-PASS]" not in text or "CORE PASS" not in text or "BSG PASS" not in text:
        raise ValueError("four-slot log lacks the checked guest/host pass markers")
    return int(match.group(1), 16)


def main():
    if sha256(VCD) != EXPECTED_VCD_SHA256 or sha256(RUN_LOG) != EXPECTED_RUN_SHA256:
        raise ValueError("retained evidence identity mismatch")

    sampled = read_samples()
    periods = [b[0] - a[0] for a, b in zip(sampled["core"], sampled["core"][1:])]
    period = statistics.mode(periods)
    retired = [
        (when, row["pc"], row["thread"])
        for when, row in sampled["core"] if row["instret"] == 1
    ]
    begins = [when for when, pc, thread in retired if pc == BEGIN_PC and thread == 0]
    if len(begins) != 1:
        raise ValueError(f"expected one measured begin, found {begins}")
    begin = begins[0]
    ends = [when for when, pc, thread in retired if pc == END_PC and thread == 0 and when > begin]
    if len(ends) != 1:
        raise ValueError(f"expected one measured end, found {ends}")
    end = ends[0]
    measured_cycles = (end - begin) // period
    run_cycles = parse_run_cycles()
    if measured_cycles != run_cycles or run_cycles != 2241:
        raise ValueError(f"cycle mismatch: trace={measured_cycles}, run={run_cycles}")

    core = [(when, row) for when, row in sampled["core"] if begin <= when <= end]
    uce = [(when, row) for when, row in sampled["uce"] if begin <= when <= end]
    allocations = [
        (when, row["free_slot"], row["addr"])
        for when, row in uce if row["allocate"] == 1
    ]
    issues = [(when, row["issue_slot"]) for when, row in uce if row["issue"] == 1]
    publications = [
        (when, row["install_slot"])
        for when, row in uce
        if row["install_state"] == 6 and row["tag_v"] == 1 and row["tag_y"] == 1
    ]
    addresses = [
        (when, row["arid"], row["araddr"])
        for when, row in core if row["arvalid"] == 1 and row["arready"] == 1
    ]
    final_beats = [
        (when, row["rid"])
        for when, row in core if row["rvalid"] == 1 and row["rready"] == 1 and row["rlast"] == 1
    ]
    accepted = sum(row["accept"] == 1 for _, row in uce)
    drops = sum(row["drop"] == 1 for _, row in uce)
    if not (len(allocations) == len(issues) == accepted == 31 and len(addresses) == len(final_beats) == 63):
        raise ValueError("unexpected four-slot request accounting")
    if drops != 0:
        raise ValueError("UCE reported an accepted hint drop")

    prefetch_addresses = [entry for entry in addresses if entry[1] != 0]
    ordinary_addresses = [entry for entry in addresses if entry[1] == 0]
    ordinary_beats = [entry for entry in final_beats if entry[1] == 0]
    if (len(prefetch_addresses) != 31 or len(ordinary_addresses) != 32
            or len(ordinary_beats) != 32):
        raise ValueError("unexpected prefetch/ordinary AXI split")
    offsets = {
        (axi_address - cpu_address) & 0xFFFFFFFF
        for (_, _, cpu_address), (_, _, axi_address) in zip(allocations, prefetch_addresses)
    }
    if len(offsets) != 1:
        raise ValueError(f"nonconstant CPU-to-AXI mapping: {offsets}")
    physical_offset = offsets.pop()

    expected = []
    for stream, indices in enumerate(EXPECTED_NODE_INDICES):
        for position, node_index in enumerate(indices):
            expected.append({
                "stream": stream,
                "position": position,
                "node_index": node_index,
                "cpu_address": MEASURED_NODES_BASE + 64 * node_index,
            })
    expected_by_address = {row["cpu_address"]: row for row in expected}
    allocated_counts = collections.Counter(address for _, _, address in allocations)
    request_rows = [(when, row) for when, row in uce if row["prefetch_v"] == 1]
    request_counts = collections.Counter(row["addr"] for _, row in request_rows)
    if set(request_counts) != set(expected_by_address):
        raise ValueError("the UCE did not observe exactly the 33 expected hint addresses")
    missing = [row.copy() for row in expected if not allocated_counts[row["cpu_address"]]]
    if [(row["stream"], row["position"], row["node_index"]) for row in missing] != [
        (2, 2, 1024), (2, 7, 92)
    ]:
        raise ValueError(f"unexpected unaccepted hints: {missing}")

    hint_retirements = [
        (when, thread) for when, pc, thread in retired
        if begin <= when <= end and pc == HINT_PC
    ]
    missing_rows = []
    for row in missing:
        address = row["cpu_address"]
        attempts = [(when, sample) for when, sample in request_rows if sample["addr"] == address]
        if len(attempts) != 2 or any(sample["free_v"] != 0 for _, sample in attempts):
            raise ValueError(f"missing hint was not twice refused at full capacity: {address:#x}")
        if any(sample["accept"] != 0 or sample["drop"] != 0 for _, sample in attempts):
            raise ValueError(f"missing hint had an unexpected terminal handshake: {address:#x}")
        retirement = next(
            when for when, thread in hint_retirements
            if thread == row["stream"] and when > attempts[-1][0]
        )
        row.update({
            "request_attempt_cycles": [cycle(when, begin, period) for when, _ in attempts],
            "attempts_all_four_slots_full": True,
            "uce_accept_count": 0,
            "uce_drop_count": 0,
            "hint_retire_cycle": cycle(retirement, begin, period),
            "last_attempt_to_retirement_cycles": cycle(retirement - attempts[-1][0], 0, period),
        })
        missing_rows.append(row)

    ordinary_groups = collections.defaultdict(list)
    for address_entry, beat_entry in zip(ordinary_addresses, ordinary_beats):
        address_time, _, axi_address = address_entry
        response_time, _ = beat_entry
        ordinary_groups[axi_address & ~63].append((address_time, axi_address, response_time))
    if sorted(len(group) for group in ordinary_groups.values()) != [16, 16]:
        raise ValueError("ordinary fallback is not exactly two 16-word line fills")

    fallback_rows = []
    for axi_line, group in sorted(ordinary_groups.items(), key=lambda item: item[1][0][0]):
        group.sort()
        if [address - axi_line for _, address, _ in group] != list(range(0, 64, 4)):
            raise ValueError("fallback did not walk a complete 64-byte line")
        response_latencies = [(response - address_time) / period for address_time, _, response in group]
        cpu_line = (axi_line - physical_offset) & 0xFFFFFFFF
        if cpu_line not in {row["cpu_address"] for row in missing_rows}:
            raise ValueError(f"ordinary fill does not match a missing hint: {cpu_line:#x}")
        span = (group[-1][2] - group[0][0]) / period
        fallback_rows.append({
            "cpu_address": cpu_line,
            "axi_address": axi_line,
            "first_address_cycle": cycle(group[0][0], begin, period),
            "final_address_cycle": cycle(group[-1][0], begin, period),
            "final_response_cycle": cycle(group[-1][2], begin, period),
            "word_requests": len(group),
            "request_spacing_cycles": [
                (later[0] - earlier[0]) / period for earlier, later in zip(group, group[1:])
            ],
            "address_to_response_cycles": response_latencies,
            "first_address_to_final_response_cycles": span,
        })

    occupancy = [bin(row["valid"] or 0).count("1") for _, row in uce]
    complete_backlog = [bin(row["complete"] or 0).count("1") for _, row in uce]
    allocation_gaps = [
        (later[0] - earlier[0]) / period for earlier, later in zip(allocations, allocations[1:])
    ]
    install_busy = sum(row["install_state"] not in (None, 0) for _, row in uce)
    install_drop_entries = []
    previous_state = None
    for when, row in uce:
        state = row["install_state"]
        if state == 7 and previous_state != 7:
            install_drop_entries.append(cycle(when, begin, period))
        previous_state = state

    in_flight = 0
    maximum_in_flight = 0
    for _, row in core:
        if row["arvalid"] == 1 and row["arready"] == 1:
            in_flight += 1
        if row["rvalid"] == 1 and row["rready"] == 1 and row["rlast"] == 1:
            in_flight -= 1
        maximum_in_flight = max(maximum_in_flight, in_flight)
    if in_flight != 0:
        raise ValueError("AXI transactions remain at the measured end")

    ten_slot = json.loads(TEN_SLOT_RESULTS.read_text())["window"]["cycles"]
    extra = measured_cycles - ten_slot
    fallback_span = sum(row["first_address_to_final_response_cycles"] for row in fallback_rows)
    if ten_slot != 802 or fallback_span != 1346:
        raise ValueError("unexpected ten-slot control or fallback span")

    result = {
        "method": (
            "Sample the retained four-slot VCD on rising core/UCE clocks inside the exact fifth "
            "run_window; compare all expected graph-line hints with UCE allocation handshakes, "
            "then map ordinary AXI reads back to CPU lines with the measured fixed address offset."
        ),
        "provenance": {
            "top_commit": "03955af94db78af86c271b560052f74f66879a88",
            "black_parrot_commit": "259b88587afe31a15db521f672d7626c26119642",
            "subsystem_commit": "f9762c5b41f193173d134ac8a20b9e126ceac1e9",
            "test_elf_sha256": "0770ad121dfd1dcc6e7a56822a7dd2b12f3c25f7feadb2cdff073d1243a25e9b",
            "filtered_vcd_xz_sha256": sha256(VCD),
            "trace_run_log_sha256": sha256(RUN_LOG),
        },
        "configuration": {
            "resident_threads": 3,
            "logical_contexts": 10,
            "prefetch_slots": 4,
            "streams": 3,
            "nodes_per_stream": 11,
            "total_nodes": 33,
            "synthetic_request_to_first_beat_nominal_cycles": 40,
            "physical_axi_data_width_bits": 32,
            "line_bytes": 64,
        },
        "window": {
            "begin_timestamp": begin,
            "end_timestamp": end,
            "clock_period_ps": period,
            "cycles": measured_cycles,
        },
        "accounting": {
            "expected_hints": len(expected),
            "observed_hint_request_cycles": len(request_rows),
            "unique_hint_addresses": len(request_counts),
            "accepted_hints": len(allocations),
            "issued_prefetches": len(issues),
            "uce_accepted_drop_pulses": drops,
            "prefetch_axi_lines": len(prefetch_addresses),
            "ordinary_axi_word_requests": len(ordinary_addresses),
            "tag_publications": len(publications),
            "installer_drop_state_entries": len(install_drop_entries),
            "installer_drop_entry_cycles": install_drop_entries,
            "valid_slots_at_measured_end": occupancy[-1],
            "physical_address_offset_low32": physical_offset,
        },
        "missing_hint_allocations": missing_rows,
        "ordinary_fallback_line_fills": fallback_rows,
        "queue_behavior": {
            "slot_occupancy_samples": {
                str(level): count for level, count in sorted(collections.Counter(occupancy).items())
            },
            "all_slots_full_samples": occupancy.count(4),
            "all_slots_full_fraction": occupancy.count(4) / len(occupancy),
            "complete_slot_backlog_samples": {
                str(level): count
                for level, count in sorted(collections.Counter(complete_backlog).items())
            },
            "installer_busy_cycles": install_busy,
            "installer_busy_fraction": install_busy / len(uce),
            "allocation_gap_cycles": summary(allocation_gaps),
            "maximum_axi_transactions_in_flight": maximum_in_flight,
        },
        "ten_slot_comparison": {
            "four_slot_cycles": measured_cycles,
            "ten_slot_cycles": ten_slot,
            "extra_cycles": extra,
            "four_slot_slowdown": measured_cycles / ten_slot,
            "sum_of_two_serial_fallback_spans_cycles": fallback_span,
            "fallback_span_fraction_of_extra_cycles": fallback_span / extra,
            "extra_cycles_not_inside_fallback_spans": extra - fallback_span,
        },
        "interpretation": [
            "All 33 intended addresses reached the UCE, but two hint instructions retired after capacity-backpressured attempts without an allocation handshake.",
            "The same two CPU lines are the only ordinary fills; each becomes sixteen serialized 32-bit reads in the minimal wrapper.",
            "The two serialized fill spans account for 93.5% of the four-slot runtime increase over the ten-slot control.",
            "Four accepted full-line prefetches enter the installer drop state while ordinary fallback credits are outstanding; this is a secondary consequence of the two missed allocations.",
        ],
        "limits": [
            "The trace uses the synthetic 40-cycle memory model and the 32-bit minimal wrapper, not physical DDR or the 64-bit FPGA wrapper.",
            "The run reached checked guest, core, and host pass markers before a pre-existing DPI finalization assertion made the process exit nonzero.",
            "Summed fallback spans are an explanatory timeline attribution, not a counterfactual rerun with only those two events removed.",
        ],
    }
    text = json.dumps(result, indent=2) + "\n"
    (HERE / "results-queue-depth.json").write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
