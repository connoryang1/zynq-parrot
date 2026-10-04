#!/usr/bin/env python3
"""Patch a BlackParrot Linux NBF to use an accurately declared timer.

The maintained FPGA image provides a dedicated real-time clock, but historical
Linux NBFs select the divided core clock and declare a different frequency in
their embedded device tree.  This tool changes the selector and the matching
device-tree property together while preserving every other NBF write.
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import tempfile
from pathlib import Path


WIDTHS = {0: 1, 1: 2, 2: 4, 3: 8}
MTIMESEL_ADDRESS = 0x00308000
UNFREEZE = "02_0000000000200008_0000000000000000"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"


def parse(line: str) -> tuple[int, int, int]:
    fields = line.strip().split("_")
    if len(fields) != 3:
        raise ValueError(f"malformed NBF line: {line.rstrip()}")
    return tuple(int(field, 16) for field in fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frequency", type=int, default=8_000_000)
    parser.add_argument("--selector", type=int, default=2,
                        help="mtime source: 0=core, 1=core/16, 2=rt_clk")
    args = parser.parse_args()
    if not 1 <= args.frequency <= 0xFFFFFFFF:
        parser.error("frequency must fit a nonzero 32-bit device-tree cell")
    if not 0 <= args.selector <= 3:
        parser.error("selector must be in 0..3")

    lines = args.source.read_text(encoding="ascii").splitlines(keepends=True)
    memory: dict[int, int] = {}
    selector_indices = []
    for index, line in enumerate(lines):
        command, address, data = parse(line)
        if address == MTIMESEL_ADDRESS:
            selector_indices.append(index)
        if command not in WIDTHS or not 0x80000000 <= address < 0x90000000:
            continue
        width = WIDTHS[command]
        for offset, byte in enumerate(data.to_bytes(width, "little")):
            memory[address + offset] = byte
    if len(selector_indices) != 1:
        parser.error(f"expected one mtime selector write, found {len(selector_indices)}")

    addresses = sorted(memory)
    low, high = addresses[0], addresses[-1] + 1
    image = bytearray(high - low)
    for address, byte in memory.items():
        image[address - low] = byte
    fdt_offset = image.find(FDT_MAGIC)
    if fdt_offset < 0 or image.find(FDT_MAGIC, fdt_offset + 1) >= 0:
        parser.error("expected exactly one embedded device tree")
    total_size = struct.unpack(">I", image[fdt_offset + 4:fdt_offset + 8])[0]
    original = bytes(image[fdt_offset:fdt_offset + total_size])

    with tempfile.TemporaryDirectory() as directory:
        dtb = Path(directory) / "linux.dtb"
        dtb.write_bytes(original)
        subprocess.run(["fdtput", "-t", "i", str(dtb), "/cpus",
                        "timebase-frequency", str(args.frequency)], check=True)
        updated = dtb.read_bytes()
    if len(updated) != len(original):
        parser.error("device-tree patch changed blob size")

    fdt_address = low + fdt_offset
    changed_blocks = []
    for offset in range(0, len(original), 8):
        before = original[offset:offset + 8]
        after = updated[offset:offset + 8]
        if before != after:
            if len(after) != 8:
                parser.error("changed device-tree tail is not 8-byte aligned")
            changed_blocks.append(
                f"03_{fdt_address + offset:016x}_"
                f"{int.from_bytes(after, 'little'):016x}\n")
    lines[selector_indices[0]] = (
        f"02_{MTIMESEL_ADDRESS:016x}_{args.selector:016x}\n")
    unfreeze = [i for i, line in enumerate(lines) if line.strip() == UNFREEZE]
    if not unfreeze:
        parser.error("source contains no recognized final unfreeze command")
    insert = unfreeze[-1]
    args.output.write_text(
        "".join(lines[:insert] + changed_blocks + lines[insert:]),
        encoding="ascii")
    print(f"mtime selector: {args.selector}")
    print(f"timebase frequency: {args.frequency}")
    print(f"embedded DTB: 0x{fdt_address:x} ({total_size} bytes)")
    print(f"device-tree patch writes: {len(changed_blocks)}")


if __name__ == "__main__":
    main()
