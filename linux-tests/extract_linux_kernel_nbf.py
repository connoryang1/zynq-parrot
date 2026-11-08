#!/usr/bin/env python3
"""Extract one canonical skip-zero Linux payload from an NBF image."""

import argparse
from pathlib import Path

from splice_linux_kernel_nbf import MEMORY_COMMANDS, parse_line


def extract(source, output, size, base=0x80200000):
    """Reconstruct an exact payload, rejecting noncanonical overlapping writes."""
    if size <= 0 or size % 8:
        raise ValueError("kernel payload size must be positive and 8-byte aligned")
    end = base + size
    payload = bytearray(size)
    observed = set()
    for index, line in enumerate(Path(source).read_text(encoding="ascii").splitlines(),
                                 start=1):
        command, address, value = parse_line(line)
        width = MEMORY_COMMANDS.get(command)
        if width is None or address >= end or address + width <= base:
            continue
        if command != 3 or address % 8 or not (base <= address < end):
            raise ValueError(
                f"noncanonical payload write at line {index}: {line}")
        if address in observed:
            raise ValueError(f"duplicate payload write at 0x{address:x}")
        observed.add(address)
        offset = address - base
        payload[offset:offset + 8] = value.to_bytes(8, "little")
    if not observed:
        raise ValueError("source NBF contains no payload writes")
    Path(output).write_bytes(payload)
    return {"base": base, "bytes": size, "records": len(observed)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--size", required=True, type=lambda text: int(text, 0))
    parser.add_argument("--base", type=lambda text: int(text, 0),
                        default=0x80200000)
    args = parser.parse_args(argv)
    summary = extract(args.source, args.output, args.size, args.base)
    print("KERNEL_NBF_EXTRACT "
          + " ".join(f"{key}={value}" for key, value in summary.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
