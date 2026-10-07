#!/usr/bin/env python3
"""Verify the fixed five-slot prefetch replay result."""

import collections
import hashlib
import json
import lzma
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
VCD = HERE / "events-k5-fixed.vcd.xz"
RUN_LOG = HERE / "k5-fixed-run.log"
THREE_SLOT_RESULT = HERE / "results-queue-fix-k3.json"
FOUR_SLOT_RESULT = HERE / "results-queue-fix.json"
TEN_SLOT_RESULT = HERE / "results.json"

EXPECTED_VCD_SHA256 = "af0354561aa5216d575e182cb4b00c56efd689723c5b294b1a0d0f3b0d5c599d"
EXPECTED_RUN_SHA256 = "f6f9f87e26ac546632b836d9e6918c83f386fa226672c79b88ff9a74d83a2fc8"
BEGIN_PC = 0x80000C90
END_PC = 0x80000C9C
WINDOW_SEARCH_START = 74_990_000_000

IDS = {
    "clock": "N'",
    "instret": "r)",
    "pc": "u)",
    "thread": "7+",
    "prefetch_v": "Ya!",
    "valid": "Za!",
    "free_v": "za!",
    "accept": "/b!",
    "allocate": "0b!",
    "drop": "1b!",
    "install_state": "td!",
    "araddr": "w%",
    "arid": "x%",
    "arvalid": "{%",
    "arready": "|%",
    "pipe_replay": "|;",
    "dcache_prefetch_replay": "j^",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integer(value):
    if value is None or not value or set(value.lower()) & set("xz"):
        return None
    return int(value, 2)


def samples():
    values = {}
    old_clock = None
    sampled = []
    timestamp = None
    changes = []

    def flush():
        nonlocal changes, old_clock
        if timestamp is None:
            return
        for identifier, value in changes:
            values[identifier] = value
        clock = values.get(IDS["clock"])
        if clock == "1" and old_clock == "0" and timestamp >= WINDOW_SEARCH_START:
            sampled.append(
                (timestamp, {name: integer(values.get(ident)) for name, ident in IDS.items()})
            )
        old_clock = clock
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


def parse_run_cycles():
    text = RUN_LOG.read_text()
    match = re.search(
        r"Benchmark: DEPENDENT mode=0x0*3 streams=0x0*3 nodes=0x0*21 cycles=0x([0-9a-fA-F]+)",
        text,
    )
    if not match or "[BSG-PASS]" not in text or "CORE PASS" not in text or "BSG PASS" not in text:
        raise ValueError("fixed run lacks checked guest/core/host pass markers")
    return int(match.group(1), 16)


def main():
    if sha256(VCD) != EXPECTED_VCD_SHA256 or sha256(RUN_LOG) != EXPECTED_RUN_SHA256:
        raise ValueError("fixed-run evidence identity mismatch")

    sampled = samples()
    retired = [
        (when, row["pc"], row["thread"])
        for when, row in sampled if row["instret"] == 1
    ]
    begins = [when for when, pc, thread in retired if pc == BEGIN_PC and thread == 0]
    if len(begins) != 1:
        raise ValueError(f"expected one measured begin, found {begins}")
    begin = begins[0]
    ends = [when for when, pc, thread in retired if pc == END_PC and thread == 0 and when > begin]
    if len(ends) != 1:
        raise ValueError(f"expected one measured end, found {ends}")
    end = ends[0]
    period = 50_000
    trace_cycles = (end - begin) // period
    run_cycles = parse_run_cycles()
    if trace_cycles != run_cycles or run_cycles != 802:
        raise ValueError(f"cycle mismatch: trace={trace_cycles}, run={run_cycles}")

    window = [(when, row) for when, row in sampled if begin <= when <= end]
    accepted = sum(row["accept"] == 1 for _, row in window)
    allocated = sum(row["allocate"] == 1 for _, row in window)
    drops = sum(row["drop"] == 1 for _, row in window)
    visible_requests = sum(row["prefetch_v"] == 1 for _, row in window)
    replay_cycles = sum(row["pipe_replay"] == 1 for _, row in window)
    addresses = [
        (when, row["arid"], row["araddr"])
        for when, row in window if row["arvalid"] == 1 and row["arready"] == 1
    ]
    if accepted != 33 or allocated != 33 or drops != 0:
        raise ValueError("fixed hint acceptance accounting failed")
    if len(addresses) != 33 or any(identifier in (None, 0) for _, identifier, _ in addresses):
        raise ValueError("fixed run contains missing IDs or ordinary AXI fallbacks")

    occupancy = [bin(row["valid"] or 0).count("1") for _, row in window]
    install_drop_entries = []
    previous_state = None
    for when, row in window:
        state = row["install_state"]
        if state == 7 and previous_state != 7:
            install_drop_entries.append((when - begin) / period)
        previous_state = state
    if install_drop_entries:
        raise ValueError(f"fixed run entered installer drop state: {install_drop_entries}")

    three_slot = json.loads(THREE_SLOT_RESULT.read_text())
    four_slot = json.loads(FOUR_SLOT_RESULT.read_text())
    ten_slot_cycles = json.loads(TEN_SLOT_RESULT.read_text())["window"]["cycles"]
    three_slot_cycles = three_slot["window"]["cycles"]
    four_slot_cycles = four_slot["window"]["cycles"]
    three_slot_excess = three_slot_cycles - ten_slot_cycles
    four_slot_excess = four_slot_cycles - ten_slot_cycles
    fourth_slot_savings = three_slot_cycles - four_slot_cycles
    fifth_slot_savings = four_slot_cycles - run_cycles
    result = {
        "method": (
            "Sample the retained fixed five-slot VCD on rising core/UCE clocks inside the exact "
            "measured run_window; require all 33 hints to allocate, all 33 AXI requests to carry "
            "nonzero prefetch IDs, and no UCE or installer drop."
        ),
        "provenance": {
            "historical_top_commit": "03955af94db78af86c271b560052f74f66879a88",
            "historical_black_parrot_commit": "259b88587afe31a15db521f672d7626c26119642",
            "tested_fix_black_parrot_commit": "d4c20786dd98f5fdbc285adb43f0fe38631dbbe0",
            "test_elf_sha256": "0770ad121dfd1dcc6e7a56822a7dd2b12f3c25f7feadb2cdff073d1243a25e9b",
            "filtered_vcd_xz_sha256": sha256(VCD),
            "run_log_sha256": sha256(RUN_LOG),
        },
        "fix": {
            "file": "bp_be/src/v/bp_be_calculator/bp_be_pipe_mem.sv",
            "cause": (
                "A hint dispatched while the D-cache was idle could reach the memory pipe after "
                "dcache_busy asserted. dcache_pkt_v suppressed that hint, but only a hint that "
                "entered the D-cache could assert the old replay signal, so the unissued hint retired."
            ),
            "change": (
                "Pipeline the late dcache_busy suppression alongside the hint identity and include "
                "it in cache_replay_v_o."
            ),
        },
        "window": {
            "begin_timestamp": begin,
            "end_timestamp": end,
            "clock_period_ps": period,
            "cycles": trace_cycles,
        },
        "accounting": {
            "visible_uce_hint_request_cycles": visible_requests,
            "accepted_hints": accepted,
            "allocated_hints": allocated,
            "uce_accepted_drop_pulses": drops,
            "memory_pipe_replay_cycles": replay_cycles,
            "dcache_prefetch_replay_cycles": sum(
                row["dcache_prefetch_replay"] == 1 for _, row in window
            ),
            "axi_prefetch_line_requests": len(addresses),
            "axi_ordinary_requests": sum(identifier == 0 for _, identifier, _ in addresses),
            "axi_id_distribution": {
                str(identifier): count
                for identifier, count in sorted(collections.Counter(row[1] for row in addresses).items())
            },
            "installer_drop_state_entries": len(install_drop_entries),
        },
        "queue_behavior": {
            "slot_occupancy_samples": {
                str(level): count for level, count in sorted(collections.Counter(occupancy).items())
            },
            "all_slots_full_samples": occupancy.count(5),
            "all_slots_full_fraction": occupancy.count(5) / len(occupancy),
        },
        "comparison": {
            "fixed_three_slot_cycles": three_slot_cycles,
            "fixed_four_slot_cycles": four_slot_cycles,
            "fixed_five_slot_cycles": run_cycles,
            "ten_slot_cycles": ten_slot_cycles,
            "cycles_saved_by_fourth_slot": fourth_slot_savings,
            "runtime_reduction_from_fourth_slot": fourth_slot_savings / three_slot_cycles,
            "cycles_saved_by_fifth_slot": fifth_slot_savings,
            "runtime_reduction_from_fifth_slot": fifth_slot_savings / four_slot_cycles,
            "three_slot_excess_over_ten_slots": three_slot_excess,
            "four_slot_excess_over_ten_slots": four_slot_excess,
            "five_slot_excess_over_ten_slots": run_cycles - ten_slot_cycles,
            "fraction_of_three_slot_excess_removed_by_fourth_slot": (
                fourth_slot_savings / three_slot_excess
            ),
            "fraction_of_three_slot_excess_removed_by_fifth_slot": (
                fifth_slot_savings / three_slot_excess
            ),
            "five_slot_matches_ten_slot_cycles": run_cycles == ten_slot_cycles,
            "three_slot_slowdown_over_ten_slots": three_slot_cycles / ten_slot_cycles,
            "four_slot_slowdown_over_ten_slots": four_slot_cycles / ten_slot_cycles,
            "five_slot_slowdown_over_ten_slots": run_cycles / ten_slot_cycles,
            "visible_hint_request_cycle_reduction_from_four_slots": (
                four_slot["accounting"]["visible_uce_hint_request_cycles"]
                - visible_requests
            ),
            "memory_pipe_replay_cycle_reduction_from_four_slots": (
                four_slot["accounting"]["memory_pipe_replay_cycles"] - replay_cycles
            ),
        },
        "limits": [
            "The result uses the synthetic 40-cycle memory model and 32-bit minimal wrapper, not physical DDR.",
            "The run reached checked guest, core, and host pass markers before the pre-existing DPI finalization assertion made the process exit nonzero.",
            "Matching ten slots is specific to this three-stream trace and does not establish the physical FPGA or Linux endpoint.",
        ],
    }
    text = json.dumps(result, indent=2) + "\n"
    (HERE / "results-queue-fix-k5.json").write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
