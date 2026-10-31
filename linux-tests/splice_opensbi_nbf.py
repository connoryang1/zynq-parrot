#!/usr/bin/env python3
"""Combine donor OpenSBI records with an exact base kernel/DTB NBF payload."""

import argparse
import hashlib
from pathlib import Path
import re


MEMORY = re.compile(r"^03_([0-9a-fA-F]{16})_([0-9a-fA-F]{16})$")
DEFAULT_CUTOFF = 0x80200000


def split_main_records(lines, source):
    first = next((index for index, line in enumerate(lines)
                  if MEMORY.fullmatch(line)), None)
    if first is None:
        raise ValueError(f"{source}: no memory records")
    end = first
    while end < len(lines) and MEMORY.fullmatch(lines[end]):
        end += 1
    if not lines[:first] or not lines[:first][-1].startswith("fe_"):
        raise ValueError(f"{source}: missing load fence before memory records")
    if end == len(lines) or not lines[end].startswith("fe_"):
        raise ValueError(f"{source}: missing load fence after memory records")
    return lines[:first], lines[first:end], lines[end:]


def record_address(record):
    match = MEMORY.fullmatch(record)
    if not match:
        raise ValueError(f"invalid memory record: {record}")
    return int(match.group(1), 16)


def require_unique(records, label):
    addresses = [record_address(record) for record in records]
    if len(addresses) != len(set(addresses)):
        raise ValueError(f"{label}: duplicate selected memory address")


def splice(base_lines, donor_lines, cutoff=DEFAULT_CUTOFF):
    base_prefix, base_main, base_tail = split_main_records(base_lines, "base")
    donor_prefix, donor_main, _ = split_main_records(donor_lines, "donor")
    if base_prefix != donor_prefix:
        raise ValueError("base and donor boot-control preambles differ")

    donor_low = [record for record in donor_main
                 if record_address(record) < cutoff]
    base_high = [record for record in base_main
                 if record_address(record) >= cutoff]
    if not donor_low or record_address(donor_low[0]) != 0x80000000:
        raise ValueError("donor does not begin with OpenSBI at 0x80000000")
    if not any(record_address(record) == cutoff for record in base_high):
        raise ValueError(f"base has no payload entry at 0x{cutoff:x}")
    require_unique(donor_low, "donor OpenSBI")
    require_unique(base_high, "base payload")
    return base_prefix + donor_low + base_high + base_tail, donor_low, base_high


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("donor", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cutoff", type=lambda value: int(value, 0),
                        default=DEFAULT_CUTOFF)
    args = parser.parse_args()
    base_lines = args.base.read_text().splitlines()
    donor_lines = args.donor.read_text().splitlines()
    output, donor_low, base_high = splice(base_lines, donor_lines, args.cutoff)
    args.output.write_text("\n".join(output) + "\n")
    print(f"DONOR_OPENSBI_RECORDS={len(donor_low)}")
    print(f"BASE_PAYLOAD_RECORDS={len(base_high)}")
    print(f"BASE_SHA256={sha256(args.base)}")
    print(f"DONOR_SHA256={sha256(args.donor)}")
    print(f"OUTPUT_SHA256={sha256(args.output)}")


if __name__ == "__main__":
    main()
