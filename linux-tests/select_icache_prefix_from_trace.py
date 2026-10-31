#!/usr/bin/env python3
"""Select a bounded exact-order I-cache replay prefix from one FPGA trace."""

import argparse
import json
import re
from pathlib import Path


HEADER = re.compile(
    r"TRACE_HEADER .*?i_count=(\d+) d_count=(\d+) "
    r"i_overflow=(\d+) d_overflow=(\d+) armed=(\d+)"
)
RECORD = re.compile(
    r"TRACE_RECORD seq=(\d+) side=([ID]) index=(\d+) .*?"
    r"paddr=0x([0-9a-fA-F]+)"
)


def select(text, start_line, limit):
    """Return an emitter-compatible table starting at one observed I line."""
    header = HEADER.search(text)
    if not header:
        raise ValueError("missing TRACE_HEADER")
    icount, _, ioverflow, doverflow, armed = map(int, header.groups())
    if ioverflow or doverflow or armed:
        raise ValueError("trace overflowed or remained armed")
    if "TRACE_PASS" not in text:
        raise ValueError("missing TRACE_PASS")
    irecords = []
    for match in RECORD.finditer(text):
        if match.group(2) == "I":
            irecords.append(int(match.group(4), 16))
    if len(irecords) != icount:
        raise ValueError(
            f"I-record count mismatch: header={icount} parsed={len(irecords)}"
        )
    try:
        start = irecords.index(start_line)
    except ValueError as error:
        raise ValueError(f"start line 0x{start_line:x} not observed") from error
    selected = []
    for address in irecords[start:]:
        if address not in selected:
            selected.append(address)
        if len(selected) == limit:
            break
    if len(selected) != limit:
        raise ValueError(f"only {len(selected)} unique lines remain after start")
    return {
        "purpose": (
            "Select exact-kernel post-trigger instruction misses for a bounded "
            "joint preview experiment."
        ),
        "fixed_shared_prefix": {
            "policy": (
                f"first {limit} unique I-side accepted misses beginning with "
                f"observed post-trigger line 0x{start_line:x} in a complete "
                "replay-disabled FPGA trace"
            ),
            "line_count": limit,
            "lines": [
                {
                    "rank": rank,
                    "paddr": address,
                    "cache_set": (address // 64) % 64,
                }
                for rank, address in enumerate(selected)
            ],
        },
    }


def address(text):
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("address must be an integer") from error
    if value < 0 or value >= 1 << 56 or value & 63:
        raise argparse.ArgumentTypeError("address must be a 56-bit cache-line address")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--start-line", required=True, type=address)
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 256:
        parser.error("--limit must be in 1..256")
    try:
        result = select(args.trace.read_text(errors="replace"),
                        args.start_line, args.limit)
    except ValueError as error:
        parser.error(str(error))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
