#!/usr/bin/env python3
"""Create an aligned interactive-shell variant of a BlackParrot Linux NBF."""

from __future__ import annotations

import argparse
from pathlib import Path


WIDTHS = {0: 1, 1: 2, 2: 4, 3: 8}
UNFREEZE = "02_0000000000200008_0000000000000000"
DEFAULT_OLD = "console=hvc0 loglevel=8 root=/dev/ram0"
DEFAULT_NEW = "console=hvc0 loglevel=8 rdinit=/bin/sh"


def parse_line(line: str) -> tuple[int, int, int]:
    fields = line.strip().split("_")
    if len(fields) != 3:
        raise ValueError(f"malformed NBF line: {line.rstrip()}")
    return tuple(int(field, 16) for field in fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--old", default=DEFAULT_OLD)
    parser.add_argument("--new", default=DEFAULT_NEW)
    args = parser.parse_args()

    old = args.old.encode("ascii")
    new = args.new.encode("ascii")
    if len(old) != len(new):
        parser.error("old and new boot arguments must have equal byte lengths")

    lines = args.source.read_text(encoding="ascii").splitlines(keepends=True)
    writes = []
    low = None
    high = 0
    for line in lines:
        command, address, data = parse_line(line)
        if command not in WIDTHS or address < 0x80000000:
            continue
        width = WIDTHS[command]
        writes.append((address, width, data))
        low = address if low is None else min(low, address)
        high = max(high, address + width)

    if low is None:
        parser.error("source contains no DRAM writes")
    image = bytearray(high - low)
    for address, width, data in writes:
        image[address - low : address - low + width] = data.to_bytes(width, "little")

    matches = []
    offset = image.find(old)
    while offset >= 0:
        matches.append(offset)
        offset = image.find(old, offset + 1)
    if len(matches) != 1:
        parser.error(f"expected one old bootargs match, found {len(matches)}")

    address = low + matches[0]
    patch_start = address & ~0x7
    patch_end = (address + len(old) + 7) & ~0x7
    block = bytearray(image[patch_start - low : patch_end - low])
    within = address - patch_start
    block[within : within + len(new)] = new

    patch = []
    for offset in range(0, len(block), 8):
        value = int.from_bytes(block[offset : offset + 8], "little")
        patch.append(f"03_{patch_start + offset:016x}_{value:016x}\n")

    unfreeze_indices = [
        index for index, line in enumerate(lines) if line.strip() == UNFREEZE
    ]
    if not unfreeze_indices:
        parser.error("source contains no recognized unfreeze command")
    insert = unfreeze_indices[-1]
    args.output.write_text(
        "".join(lines[:insert] + patch + lines[insert:]), encoding="ascii"
    )
    print(f"bootargs address: 0x{address:x}")
    print(f"aligned patch: 0x{patch_start:x}..0x{patch_end:x} ({len(patch)} writes)")


if __name__ == "__main__":
    main()
