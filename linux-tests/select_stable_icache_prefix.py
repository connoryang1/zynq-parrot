#!/usr/bin/env python3
"""Select a stable post-switch instruction prefix across replay-off traces."""

import argparse
import hashlib
import json
import re
from pathlib import Path

from analyze_tagged_icache_trace_pair import IDENTITY_KEYS, load_trace


PRIVILEGED_START = 0x80000000
PRIVILEGED_END = 0x81000000


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(paths, kernel_sha256, selection_floor, limit, anchor_paddr=None):
    if len(paths) < 2:
        raise ValueError("stable selection requires at least two traces")
    if not re.fullmatch(r"[0-9a-f]{64}", kernel_sha256):
        raise ValueError("kernel SHA-256 must be 64 lowercase hex digits")
    if ((selection_floor is None) == (anchor_paddr is None)
            or (selection_floor is not None and selection_floor < 0)
            or (anchor_paddr is not None
                and (anchor_paddr & 63
                     or not PRIVILEGED_START <= anchor_paddr < PRIVILEGED_END))
            or not 1 <= limit <= 256):
        raise ValueError("invalid selection floor or limit")
    traces = [load_trace(path, "off", 0) for path in paths]
    reference = traces[0]["status"]
    for trace in traces[1:]:
        for key in IDENTITY_KEYS:
            if key == "nbf_sha256":
                continue
            if trace["status"].get(key) != reference.get(key):
                raise ValueError(f"replay-off trace identity mismatch: {key}")

    if anchor_paddr is None:
        floors = [selection_floor] * len(traces)
    else:
        floors = []
        for trace in traces:
            anchor = next((record["relative"] for record in trace["records"]
                           if (record["paddr"] & ~63) == anchor_paddr), None)
            if anchor is None:
                raise ValueError(
                    f"anchor 0x{anchor_paddr:016x} is absent from "
                    f"{trace['path']}"
                )
            floors.append(anchor)

    first_by_trace = []
    for trace, floor in zip(traces, floors):
        first = {}
        for record in trace["records"]:
            address = record["paddr"] & ~63
            if (record["relative"] >= floor
                    and PRIVILEGED_START <= address < PRIVILEGED_END):
                first.setdefault(address, record["relative"])
        first_by_trace.append(first)
    common = set(first_by_trace[0])
    for first in first_by_trace[1:]:
        common &= set(first)
    ranked = sorted(
        (max(first[address] - floor
             for first, floor in zip(first_by_trace, floors)), address)
        for address in common
    )
    if len(ranked) < limit:
        raise ValueError(
            f"only {len(ranked)} stable post-floor privileged lines are available"
        )
    selected = ranked[:limit]
    return {
        "purpose": (
            "Select a stable post-switch shared instruction prefix from "
            "multiple matched replay-off entry traces."
        ),
        "input_identity": {
            "traces": [
                {
                    "transcript": str(path),
                    "transcript_sha256": sha256(path),
                    "status_sha256": sha256(
                        path.with_suffix(path.suffix + ".status.json")
                    ),
                    "nbf_sha256": trace["status"].get("nbf_sha256"),
                }
                for path, trace in zip(paths, traces)
            ],
            "elf_sha256": reference.get("elf_sha256"),
            "transfer_sha256": reference.get("transfer_sha256"),
            "control_program_sha256": reference.get("control_program_sha256"),
            "bitstream_sha256": reference.get("bitstream_sha256"),
            "kernel_sha256": kernel_sha256,
        },
        "selection": {
            "floor_relative_cycle": selection_floor,
            "anchor_paddr": anchor_paddr,
            "anchor_paddr_hex": (
                f"0x{anchor_paddr:016x}" if anchor_paddr is not None else None
            ),
            "trace_floor_relative_cycles": floors,
            "stable_lines_available": len(ranked),
            "selected_lines": limit,
            "trace_count": len(traces),
        },
        "fixed_shared_prefix": {
            "policy": (
                (f"first {limit} privileged lines present at or after anchor "
                 f"0x{anchor_paddr:016x} in every matched replay-off entry "
                 "trace, ranked by latest first occurrence relative to the "
                 "per-trace anchor")
                if anchor_paddr is not None else
                (f"first {limit} privileged lines present at or after relative "
                 f"cycle {selection_floor} in every matched replay-off entry "
                 "trace, ranked by latest first occurrence")
            ),
            "line_count": limit,
            "lines": [
                {
                    "rank": rank,
                    "relative": relative,
                    "trace_first_relatives": [
                        first[address] for first in first_by_trace
                    ],
                    "trace_relative_to_anchor": [
                        first[address] - floor
                        for first, floor in zip(first_by_trace, floors)
                    ],
                    "paddr": address,
                    "paddr_hex": f"0x{address:016x}",
                    "cache_set": (address // 64) % 64,
                }
                for rank, (relative, address) in enumerate(selected)
            ],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", nargs="+", type=Path)
    parser.add_argument("--kernel-sha256", required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--selection-floor", type=int)
    selection.add_argument(
        "--anchor-paddr", type=lambda value: int(value, 0),
        help="align each trace on this cache-line physical address",
    )
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = select(
        args.trace, args.kernel_sha256, args.selection_floor, args.limit,
        args.anchor_paddr,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"wrote {args.output} with "
        f"{result['fixed_shared_prefix']['line_count']} stable lines"
    )


if __name__ == "__main__":
    main()
