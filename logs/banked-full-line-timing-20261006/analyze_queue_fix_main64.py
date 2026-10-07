#!/usr/bin/env python3
"""Verify fixed four-slot behavior through the FPGA-facing 64-bit wrapper."""

import collections
import hashlib
import json
import lzma
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
VCD = HERE / "events-k4-fixed-main64.vcd.xz"
RUN_LOG = HERE / "k4-fixed-main64-run.log"
FIXED_MINIMAL = HERE / "results-queue-fix.json"
TEN_MINIMAL = HERE / "results.json"
TEN_MAIN64 = HERE / "results-main64.json"

EXPECTED_VCD_SHA256 = "3accdf4a4714a94b24a7c53858a81fb2c0cee0bde3492ec75564f6fafb0808e1"
EXPECTED_RUN_SHA256 = "32e36dbf9bbf926a611f9015cbdb02ae96286b490645e1c97d08047bfa4f9113"
BEGIN_PC = 0x80000C90
END_PC = 0x80000C9C
WINDOW_SEARCH_START = 14_800_000_000
IDS = {
    "clock": "{_", "instret": "n'", "pc": "q'", "thread": "*c",
    "prefetch_v": "@;\"", "valid": "A;\"", "free_v": "];\"",
    "accept": "p;\"", "allocate": "q;\"", "drop": "r;\"",
    "install_state": "S>\"", "araddr": "%2", "arid": "&2",
    "arvalid": "(2", "arready": ")2", "pipe_replay": "os",
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
        raise ValueError("fixed 64-bit run lacks checked pass markers")
    return int(match.group(1), 16)


def main():
    if sha256(VCD) != EXPECTED_VCD_SHA256 or sha256(RUN_LOG) != EXPECTED_RUN_SHA256:
        raise ValueError("fixed 64-bit evidence identity mismatch")
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
    if trace_cycles != run_cycles or run_cycles != 905:
        raise ValueError(f"cycle mismatch: trace={trace_cycles}, run={run_cycles}")

    window = [(when, row) for when, row in sampled if begin <= when <= end]
    accepted = sum(row["accept"] == 1 for _, row in window)
    allocated = sum(row["allocate"] == 1 for _, row in window)
    drops = sum(row["drop"] == 1 for _, row in window)
    addresses = [
        (when, row["arid"], row["araddr"])
        for when, row in window if row["arvalid"] == 1 and row["arready"] == 1
    ]
    if accepted != 33 or allocated != 33 or drops != 0:
        raise ValueError("fixed 64-bit hint accounting failed")
    if len(addresses) != 33 or any(identifier in (None, 0) for _, identifier, _ in addresses):
        raise ValueError("fixed 64-bit run contains an ordinary or malformed AXI request")

    occupancy = [bin(row["valid"] or 0).count("1") for _, row in window]
    install_drop_entries = []
    previous_state = None
    for when, row in window:
        state = row["install_state"]
        if state == 7 and previous_state != 7:
            install_drop_entries.append((when - begin) / period)
        previous_state = state
    if install_drop_entries:
        raise ValueError(f"fixed 64-bit run entered installer drop: {install_drop_entries}")

    fixed_minimal = json.loads(FIXED_MINIMAL.read_text())["window"]["cycles"]
    ten_minimal = json.loads(TEN_MINIMAL.read_text())["window"]["cycles"]
    ten_main64 = json.loads(TEN_MAIN64.read_text())["window"]["cycles"]
    result = {
        "method": (
            "Sample the fixed four-slot trace through black-parrot-example's FPGA-facing 64-bit "
            "HP0 path and require complete hint/AXI accounting with no ordinary fallback."
        ),
        "provenance": {
            "historical_top_commit": "03955af94db78af86c271b560052f74f66879a88",
            "tested_fix_black_parrot_commit": "d4c20786dd98f5fdbc285adb43f0fe38631dbbe0",
            "test_elf_sha256": "0770ad121dfd1dcc6e7a56822a7dd2b12f3c25f7feadb2cdff073d1243a25e9b",
            "filtered_vcd_xz_sha256": sha256(VCD),
            "run_log_sha256": sha256(RUN_LOG),
        },
        "configuration": {
            "wrapper": "black-parrot-example",
            "physical_axi_data_width_bits": 64,
            "prefetch_slots": 4,
            "streams": 3,
            "nodes": 33,
            "synthetic_request_to_first_beat_nominal_cycles": 40,
        },
        "window": {
            "begin_timestamp": begin,
            "end_timestamp": end,
            "clock_period_ps": period,
            "cycles": trace_cycles,
        },
        "accounting": {
            "visible_uce_hint_request_cycles": sum(row["prefetch_v"] == 1 for _, row in window),
            "accepted_hints": accepted,
            "allocated_hints": allocated,
            "uce_accepted_drop_pulses": drops,
            "memory_pipe_replay_cycles": sum(row["pipe_replay"] == 1 for _, row in window),
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
            "all_slots_full_samples": occupancy.count(4),
            "all_slots_full_fraction": occupancy.count(4) / len(occupancy),
        },
        "wrapper_comparison": {
            "fixed_four_slot_minimal32_cycles": fixed_minimal,
            "fixed_four_slot_main64_cycles": run_cycles,
            "fixed_main64_minus_minimal32_cycles": run_cycles - fixed_minimal,
            "ten_slot_minimal32_cycles": ten_minimal,
            "ten_slot_main64_cycles": ten_main64,
            "ten_slot_main64_minus_minimal32_cycles": ten_main64 - ten_minimal,
            "fixed_four_slot_excess_over_same_wrapper_ten_slots": run_cycles - ten_main64,
            "fixed_four_slot_slowdown_over_same_wrapper_ten_slots": run_cycles / ten_main64,
        },
        "limits": [
            "The wrapper matches the FPGA interface width but still uses synthetic memory rather than physical DDR.",
            "The run reached guest/core/host pass markers before the pre-existing DPI finalization assertion.",
        ],
    }
    text = json.dumps(result, indent=2) + "\n"
    (HERE / "results-queue-fix-main64.json").write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
