#!/usr/bin/env python3
"""Extract an exact-image shared I-cache prefix from one tagged trace."""

import argparse
import hashlib
import json
import re
from pathlib import Path


HEADER = re.compile(
    r"^TAGGED_REPLAY_ITRACE_HEADER trial=(\d+) enabled=(\d+) "
    r"i_count=(\d+) d_count=(\d+) i_overflow=(\d+) d_overflow=(\d+) "
    r"armed=(\d+) status=0x([0-9a-fA-F]{16})$", re.MULTILINE
)
RECORD = re.compile(
    r"^TAGGED_REPLAY_ITRACE_RECORD index=(\d+) relative=(\d+) "
    r"paddr=0x([0-9a-fA-F]+) raw=0x([0-9a-fA-F]{16})$", re.MULTILINE
)
PASS = re.compile(r"^TAGGED_REPLAY_ITRACE_PASS records=(\d+)$", re.MULTILINE)
PRIVILEGED_START = 0x80000000
PRIVILEGED_END = 0x81000000


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(path, kernel_sha256, selection_floor, limit):
    """Fail closed and return the emitter-compatible exact-trace result."""
    if not re.fullmatch(r"[0-9a-f]{64}", kernel_sha256):
        raise ValueError("kernel SHA-256 must be 64 lowercase hex digits")
    if selection_floor < 0 or not 1 <= limit <= 256:
        raise ValueError("invalid selection floor or prefix limit")
    status_path = path.with_suffix(path.suffix + ".status.json")
    if not status_path.is_file():
        raise ValueError("missing runner status")
    status = json.loads(status_path.read_text())
    if (status.get("status") != "PASS" or status.get("mode") != "off"
            or not status.get("trace_icache")):
        raise ValueError("trace must be a passing replay-off I-cache capture")

    text = path.read_text(errors="replace").replace("\r", "")
    headers = HEADER.findall(text)
    passes = PASS.findall(text)
    if len(headers) != 1 or len(passes) != 1:
        raise ValueError("expected exactly one instruction-trace header and PASS")
    trial, enabled, icount, dcount, ioverflow, doverflow, armed, raw = headers[0]
    del dcount, raw
    icount = int(icount)
    if (int(trial) != 0 or int(enabled) or int(ioverflow)
            or int(doverflow) or int(armed) or int(passes[0]) != icount):
        raise ValueError("instruction-trace header is not a clean disabled capture")

    matches = RECORD.findall(text)
    if len(matches) != icount or [int(row[0]) for row in matches] != list(range(icount)):
        raise ValueError("instruction-trace records are incomplete or unordered")
    selected = []
    seen = set()
    for _, relative, paddr, _ in matches:
        relative = int(relative)
        address = int(paddr, 16)
        if relative < selection_floor:
            continue
        if not PRIVILEGED_START <= address < PRIVILEGED_END:
            continue
        address &= ~63
        if address in seen:
            continue
        seen.add(address)
        selected.append((relative, address))
        if len(selected) == limit:
            break
    if len(selected) != limit:
        raise ValueError("trace lacks enough post-floor privileged instruction lines")

    policy = (
        f"first {limit} unique privileged I-miss lines at or after exact-trace "
        f"relative cycle {selection_floor}, in demand order"
    )
    return {
        "purpose": "Bind a best-case shared prefix to one exact tagged-futex trace.",
        "input_identity": {
            "transcript": str(path),
            "transcript_sha256": sha256(path),
            "status": str(status_path),
            "status_sha256": sha256(status_path),
            "kernel_sha256": kernel_sha256,
        },
        "selection": {
            "floor_relative_cycle": selection_floor,
            "captured_instruction_records": icount,
            "selected_lines": limit,
        },
        "fixed_shared_prefix": {
            "policy": policy,
            "line_count": limit,
            "lines": [
                {
                    "rank": rank,
                    "relative": relative,
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
    parser.add_argument("trace", type=Path)
    parser.add_argument("--kernel-sha256", required=True)
    parser.add_argument("--selection-floor", type=int, required=True)
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = extract(
        args.trace, args.kernel_sha256, args.selection_floor, args.limit
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {args.output} with {args.limit} exact-trace lines")


if __name__ == "__main__":
    main()
