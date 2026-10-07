#!/usr/bin/env python3
"""Audit the banked full-line request, response, and installation pipeline."""

import collections
import json
import lzma
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
VCD = HERE / "events.vcd.xz"
BEGIN_PC = 0x80000C90
END_PC = 0x80000C9C
IDS = {
    "core_clk": "3!", "uce_clk": "M'", "instret": "q)", "pc": "t)",
    "thread": "=,", "addr": "&'", "tag_v": "9'", "tag_y": ":'",
    "allocate": "Tb!", "free_slot": "Cb!", "issue": "Fb!",
    "issue_slot": "Db!", "response": "Gb!", "response_slot": "Ib!",
    "install_state": ";e!", "install_slot": "<e!", "araddr": "[!",
    "arvalid": "\\!", "arready": "]!", "arid": "^!", "arlen": "_!",
    "rvalid": "b!", "rready": "c!", "rid": "d!", "rlast": "e!",
}


def integer(value):
    if value is None or not value or set(value.lower()) & set("xz"):
        return None
    return int(value, 2)


def samples():
    values = {}
    old_clock = {IDS["core_clk"]: None, IDS["uce_clk"]: None}
    sampled = {"core": [], "uce": []}
    timestamp = None
    changes = []

    def flush():
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

    with lzma.open(VCD, "rt") as source:
        for raw in source:
            line = raw.strip()
            if not line or line.startswith("$"):
                continue
            if line.startswith("#"):
                flush()
                timestamp = int(line[1:])
                changes = []
            elif line.startswith("b"):
                parts = line.split()
                if len(parts) == 2:
                    changes.append((parts[1], parts[0][1:]))
            else:
                changes.append((line[1:], line[0]))
        flush()
    return sampled


def stats(values):
    counts = collections.Counter(values)
    return {
        "count": len(values),
        "minimum_cycles": min(values),
        "median_cycles": statistics.median(values),
        "mean_cycles": statistics.mean(values),
        "maximum_cycles": max(values),
        "distribution": {str(value): count for value, count in sorted(counts.items())},
    }


def parse_run_cycles(path):
    text = path.read_text()
    match = re.search(
        r"Benchmark: DEPENDENT mode=0x0*3 streams=0x0*3 nodes=0x0*21 cycles=0x([0-9a-fA-F]+)",
        text,
    )
    if not match or "[BSG-PASS]" not in text or "CORE PASS" not in text:
        raise ValueError(f"{path}: missing checked benchmark verdict")
    return int(match.group(1), 16)


def main():
    sampled = samples()
    core_all = sampled["core"]
    retire = [
        (when, row["pc"], row["thread"])
        for when, row in core_all if row["instret"] == 1
    ]
    begins = [when for when, pc, thread in retire if pc == BEGIN_PC and thread == 0]
    if len(begins) != 1:
        raise ValueError(f"expected one measured begin PC, found {begins}")
    begin = begins[0]
    ends = [when for when, pc, thread in retire if pc == END_PC and thread == 0 and when > begin]
    if len(ends) != 1:
        raise ValueError(f"expected one measured end PC after begin, found {ends}")
    end = ends[0]
    core = [(when, row) for when, row in core_all if begin <= when <= end]
    uce = [(when, row) for when, row in sampled["uce"] if begin <= when <= end]

    periods = [b[0] - a[0] for a, b in zip(core_all, core_all[1:])]
    clock_period = statistics.mode(periods)
    measured_cycles = (end - begin) // clock_period

    allocations = []
    issues = []
    publications = []
    responses = []
    for when, row in uce:
        if row["allocate"] == 1:
            allocations.append({"timestamp": when, "slot": row["free_slot"], "address": row["addr"]})
        if row["issue"] == 1:
            issues.append({"timestamp": when, "slot": row["issue_slot"]})
        if row["response"] == 1:
            responses.append({"timestamp": when, "slot": row["response_slot"]})
        if row["install_state"] == 6 and row["tag_v"] == 1 and row["tag_y"] == 1:
            publications.append({"timestamp": when, "slot": row["install_slot"]})

    addresses = []
    beats = []
    for when, row in core:
        if row["arvalid"] == 1 and row["arready"] == 1:
            addresses.append({
                "timestamp": when, "id": row["arid"], "address": row["araddr"],
                "length": row["arlen"],
            })
        if row["rvalid"] == 1 and row["rready"] == 1:
            beats.append({"timestamp": when, "id": row["rid"], "last": row["rlast"]})

    if not (len(allocations) == len(issues) == len(addresses) == len(publications) == 33):
        raise ValueError(
            "incomplete request accounting: "
            f"alloc={len(allocations)} issue={len(issues)} ar={len(addresses)} "
            f"publish={len(publications)}"
        )
    if len(beats) != 33 * 16 or len(responses) != 33 * 8:
        raise ValueError("unexpected physical/internal response shape")
    if set(address["length"] for address in addresses) != {15}:
        raise ValueError("AXI bursts are not uniformly 16 beats")

    # AXI IDs can be reused after a response. Match each beat to the oldest
    # not-yet-complete address transaction carrying that ID.
    by_id = collections.defaultdict(list)
    for address in addresses:
        by_id[address["id"]].append({"address": address, "first": None, "last": None, "beats": 0})
    position = collections.defaultdict(int)
    for beat in beats:
        transaction = by_id[beat["id"]][position[beat["id"]]]
        transaction["beats"] += 1
        if transaction["first"] is None:
            transaction["first"] = beat["timestamp"]
        if beat["last"] == 1:
            transaction["last"] = beat["timestamp"]
            position[beat["id"]] += 1
    transactions = sorted(
        (transaction for group in by_id.values() for transaction in group),
        key=lambda transaction: transaction["address"]["timestamp"],
    )
    if any(transaction["beats"] != 16 or transaction["last"] is None for transaction in transactions):
        raise ValueError("incomplete AXI burst")

    # The testbench translates CPU DRAM addresses by one fixed dummy-DRAM base.
    physical_offsets = {
        (transaction["address"]["address"] - allocation["address"]) & 0xFFFFFFFF
        for allocation, transaction in zip(allocations, transactions)
    }
    if len(physical_offsets) != 1:
        raise ValueError(f"nonconstant physical mapping: {physical_offsets}")
    physical_offset = physical_offsets.pop()

    installer_intervals = []
    active = None
    for when, row in uce:
        state = row["install_state"]
        if state not in (None, 0) and active is None:
            active = {"start": when, "slot": row["install_slot"]}
        if state == 0 and active is not None:
            active["end"] = when
            active["cycles"] = (when - active["start"]) / clock_period
            installer_intervals.append(active)
            active = None
    if len(installer_intervals) != 33:
        raise ValueError("incomplete installer accounting")

    rows = []
    for number, (allocation, transaction) in enumerate(zip(allocations, transactions)):
        next_allocation = min(
            (later["timestamp"] for later in allocations[number + 1:]
             if later["slot"] == allocation["slot"]),
            default=end + clock_period,
        )
        line_responses = [
            response for response in responses
            if response["slot"] == allocation["slot"]
            and allocation["timestamp"] <= response["timestamp"] < next_allocation
        ]
        line_publications = [
            publication for publication in publications
            if publication["slot"] == allocation["slot"]
            and allocation["timestamp"] <= publication["timestamp"] < next_allocation
        ]
        line_installers = [
            interval for interval in installer_intervals
            if interval["slot"] == allocation["slot"]
            and allocation["timestamp"] <= interval["start"] < next_allocation
        ]
        if len(line_responses) != 8 or len(line_publications) != 1 or len(line_installers) != 1:
            raise ValueError(f"slot lifecycle mismatch for line {number}")
        stages = {
            "allocation": allocation["timestamp"],
            "axi_address": transaction["address"]["timestamp"],
            "axi_first_32bit_beat": transaction["first"],
            "axi_final_32bit_beat": transaction["last"],
            "uce_first_64bit_response": line_responses[0]["timestamp"],
            "uce_final_64bit_response": line_responses[-1]["timestamp"],
            "installer_start": line_installers[0]["start"],
            "tag_publication": line_publications[0]["timestamp"],
            "installer_idle": line_installers[0]["end"],
        }
        rows.append({
            "line": number,
            "slot": allocation["slot"],
            "cpu_address": allocation["address"],
            "axi_address": transaction["address"]["address"],
            "axi_id": transaction["address"]["id"],
            "timestamps": stages,
            "cycles_from_allocation": {
                name: (timestamp - allocation["timestamp"]) / clock_period
                for name, timestamp in stages.items() if name != "allocation"
            },
        })

    def metric(stage):
        return stats([row["cycles_from_allocation"][stage] for row in rows])

    ar_to_first = [
        (transaction["first"] - transaction["address"]["timestamp"]) / clock_period
        for transaction in transactions
    ]
    first_to_final = [
        (transaction["last"] - transaction["first"]) / clock_period
        for transaction in transactions
    ]
    final_to_publish = [
        (row["timestamps"]["tag_publication"] - row["timestamps"]["axi_final_32bit_beat"])
        / clock_period for row in rows
    ]

    k4_cycles = parse_run_cycles(HERE / "k4-nontrace-run.log")
    k10_cycles = parse_run_cycles(HERE / "k10-trace-run.log")
    result = {
        "method": (
            "Sample retained accepted VCD evidence on rising core/UCE clocks within the fifth "
            "run_window PC interval; pair each accepted hint, AXI burst, UCE response, installer, "
            "and accepted tag publication by request order and slot lifecycle."
        ),
        "provenance": {
            "top_commit": "03955af94db78af86c271b560052f74f66879a88",
            "black_parrot_commit": "259b88587afe31a15db521f672d7626c26119642",
            "subsystem_commit": "f9762c5b41f193173d134ac8a20b9e126ceac1e9",
            "test_elf_sha256": "0770ad121dfd1dcc6e7a56822a7dd2b12f3c25f7feadb2cdff073d1243a25e9b",
            "test_nbf_sha256": "0af4a7a93375fd14537a55cbe63ca421382c7eae3857f976d61ebb2afb41639c",
            "filtered_vcd_xz_sha256": "76a4e81e0ef51b34cb64b57330e4d3b0803b164c14939afddb207c849f4d59a4",
            "trace_model_sha256": "c87db985ffe9699e889c419cdaa80ed608c6e640585057d41cd303156fad56fb",
        },
        "configuration": {
            "resident_threads": 3,
            "logical_contexts": 10,
            "prefetch_slots": 10,
            "synthetic_request_to_first_beat_nominal_cycles": 40,
            "physical_axi_data_width_bits": 32,
            "line_bytes": 64,
            "axi_beats_per_line": 16,
            "uce_response_width_bits": 64,
            "uce_responses_per_line": 8,
        },
        "window": {
            "begin_timestamp": begin,
            "end_timestamp": end,
            "cycles": measured_cycles,
        },
        "accounting": {
            "accepted_hints": len(allocations),
            "issued_hints": len(issues),
            "axi_bursts": len(addresses),
            "axi_32bit_beats": len(beats),
            "uce_64bit_responses": len(responses),
            "accepted_tag_publications": len(publications),
            "physical_address_offset_low32": physical_offset,
        },
        "latency_cycles": {
            "allocation_to_axi_address": metric("axi_address"),
            "axi_address_to_first_32bit_beat": stats(ar_to_first),
            "first_to_final_32bit_beat": stats(first_to_final),
            "allocation_to_first_32bit_beat": metric("axi_first_32bit_beat"),
            "allocation_to_final_32bit_beat": metric("axi_final_32bit_beat"),
            "allocation_to_first_64bit_uce_response": metric("uce_first_64bit_response"),
            "allocation_to_final_64bit_uce_response": metric("uce_final_64bit_response"),
            "final_32bit_beat_to_tag_publication": stats(final_to_publish),
            "allocation_to_tag_publication": metric("tag_publication"),
            "installer_active": stats([interval["cycles"] for interval in installer_intervals]),
        },
        "queue_depth_control": {
            "four_slot_cycles": k4_cycles,
            "ten_slot_cycles": k10_cycles,
            "four_slot_slowdown": k4_cycles / k10_cycles,
            "recorded_claimed_banked_cycles": 771,
            "ten_slot_reproduction_difference_from_claim": k10_cycles - 771,
        },
        "lines": rows,
        "limits": [
            "The latency trace uses the synthetic 40-cycle memory model, not physical DDR.",
            "The delayed waveform gate changes only testbench instrumentation and is excluded from the DUT.",
            "The 32-bit AXI width belongs to black-parrot-minimal-example, not the 64-bit FPGA wrapper; the UCE receives paired 64-bit responses.",
            "The companion events-k4.vcd.xz trace and analyze_queue_depth.py account for the four-slot control per transaction.",
        ],
    }
    text = json.dumps(result, indent=2) + "\n"
    (HERE / "results.json").write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
