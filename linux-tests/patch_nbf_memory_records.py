#!/usr/bin/env python3
"""Replace exact NBF memory records while preserving every other byte."""

import argparse
import hashlib
import re
from pathlib import Path


MEMORY = re.compile(r"^03_([0-9a-fA-F]{16})_([0-9a-fA-F]{16})$")


def parse_replacement(text):
    """Parse ADDRESS:OLD_DATA:NEW_DATA as unsigned 64-bit hexadecimal values."""
    parts = text.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            "replacement must be ADDRESS:OLD_DATA:NEW_DATA"
        )
    try:
        values = tuple(int(part, 0) for part in parts)
    except ValueError as error:
        raise argparse.ArgumentTypeError("replacement values must be integers") from error
    if any(value < 0 or value >= 1 << 64 for value in values):
        raise argparse.ArgumentTypeError("replacement values must fit in 64 bits")
    return values


def patch(lines, replacements):
    """Apply each expected-old replacement exactly once."""
    by_address = {}
    for address, old_data, new_data in replacements:
        if address in by_address:
            raise ValueError(f"duplicate replacement address 0x{address:016x}")
        if old_data == new_data:
            raise ValueError(f"replacement at 0x{address:016x} does not change data")
        by_address[address] = (old_data, new_data, 0)
    output = []
    for line in lines:
        match = MEMORY.fullmatch(line)
        if match:
            address = int(match.group(1), 16)
            if address in by_address:
                old_data, new_data, count = by_address[address]
                observed = int(match.group(2), 16)
                if observed != old_data:
                    raise ValueError(
                        f"record 0x{address:016x} contains 0x{observed:016x}, "
                        f"expected 0x{old_data:016x}"
                    )
                count += 1
                by_address[address] = (old_data, new_data, count)
                line = f"03_{address:016x}_{new_data:016x}"
        output.append(line)
    missing = [address for address, (_old, _new, count) in by_address.items()
               if count != 1]
    if missing:
        raise ValueError(
            "replacement records must appear exactly once: "
            + ", ".join(f"0x{address:016x}" for address in missing)
        )
    return output


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replace", action="append", type=parse_replacement,
                        required=True)
    args = parser.parse_args(argv)
    if not args.source.is_file():
        raise SystemExit(f"missing source NBF: {args.source}")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite output: {args.output}")
    try:
        result = patch(args.source.read_text().splitlines(), args.replace)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    args.output.write_text("\n".join(result) + "\n")
    print(f"SOURCE_SHA256={sha256(args.source)}")
    print(f"OUTPUT_SHA256={sha256(args.output)}")
    print(f"REPLACED_RECORDS={len(args.replace)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
