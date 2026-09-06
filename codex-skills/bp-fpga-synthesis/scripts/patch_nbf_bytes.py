#!/usr/bin/env python3
"""Overlay binary probe bytes onto a BlackParrot NBF using aligned writes."""

from __future__ import annotations

import argparse
from pathlib import Path


WIDTHS = {0: 1, 1: 2, 2: 4, 3: 8}
UNFREEZE = "02_0000000000200008_0000000000000000"


def parse_line(line: str) -> tuple[int, int, int]:
    fields = line.strip().split("_")
    if len(fields) != 3:
        raise ValueError(f"malformed NBF line: {line.rstrip()}")
    return tuple(int(field, 16) for field in fields)


def parse_patch(value: str) -> tuple[int, Path]:
    try:
        address_text, filename = value.split(":", 1)
        return int(address_text, 0), Path(filename)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError(
            "patch must be ADDRESS:FILE (for example 0x8000070c:jump.bin)"
        ) from error


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patch an NBF while avoiding unsafe byte/halfword loader writes"
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--patch",
        action="append",
        required=True,
        type=parse_patch,
        metavar="ADDRESS:FILE",
        help="binary bytes to overlay; repeat for multiple regions",
    )
    args = parser.parse_args()

    lines = args.source.read_text(encoding="ascii").splitlines(keepends=True)
    patches = [(address, path.read_bytes()) for address, path in args.patch]
    touched_blocks: set[int] = set()
    for address, data in patches:
        if not data:
            parser.error(f"patch at 0x{address:x} is empty")
        start = address & ~0x7
        end = (address + len(data) + 7) & ~0x7
        touched_blocks.update(range(start, end, 8))

    blocks = {address: bytearray(8) for address in touched_blocks}
    saw_memory_write = False
    for line in lines:
        command, address, data = parse_line(line)
        if command not in WIDTHS:
            continue
        saw_memory_write = True
        encoded = data.to_bytes(WIDTHS[command], "little")
        for offset, byte in enumerate(encoded):
            byte_address = address + offset
            block_address = byte_address & ~0x7
            if block_address in blocks:
                blocks[block_address][byte_address - block_address] = byte

    if not saw_memory_write:
        parser.error("source contains no memory writes")

    for address, data in patches:
        for offset, byte in enumerate(data):
            byte_address = address + offset
            block_address = byte_address & ~0x7
            blocks[block_address][byte_address - block_address] = byte

    aligned_writes = []
    for address in sorted(touched_blocks):
        value = int.from_bytes(blocks[address], "little")
        aligned_writes.append(f"03_{address:016x}_{value:016x}\n")

    unfreeze_indices = [
        index for index, line in enumerate(lines) if line.strip() == UNFREEZE
    ]
    if not unfreeze_indices:
        parser.error("source contains no recognized unfreeze command")
    insert = unfreeze_indices[-1]
    args.output.write_text(
        "".join(lines[:insert] + aligned_writes + lines[insert:]),
        encoding="ascii",
    )

    for address, data in patches:
        print(f"patch: 0x{address:x}..0x{address + len(data):x} ({len(data)} bytes)")
    print(f"aligned writes: {len(aligned_writes)}")


if __name__ == "__main__":
    main()
