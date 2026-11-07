#!/usr/bin/env python3
"""Replace one exact contiguous I-cache prefix table in a Linux NBF."""

import argparse
import hashlib
import json
import re
from pathlib import Path


MEMORY = re.compile(r"^03_([0-9a-fA-F]{16})_([0-9a-fA-F]{16})$")


def load_prefix(path):
    data = json.loads(path.read_text())
    try:
        entries = data["fixed_shared_prefix"]["lines"]
        lines = [int(entry.get("paddr", entry.get("paddr_hex")), 0)
                 if isinstance(entry.get("paddr", entry.get("paddr_hex")), str)
                 else entry.get("paddr", entry.get("paddr_hex"))
                 for entry in entries]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{path}: invalid fixed_shared_prefix") from error
    declared = data["fixed_shared_prefix"].get("line_count", len(lines))
    if (not lines or len(lines) != declared or len(lines) != len(set(lines))
            or any(not isinstance(line, int) or line < 0 or line >= 1 << 64
                   or line & 0x3f for line in lines)):
        raise ValueError(f"{path}: prefix lines must be unique aligned addresses")
    return lines


def patch(lines, current, replacement, linux_payload_base=0x80200000):
    if len(current) != len(replacement):
        raise ValueError("current and replacement prefixes have different lengths")
    records = {}
    for index, line in enumerate(lines):
        match = MEMORY.fullmatch(line)
        if match:
            address = int(match.group(1), 16)
            records.setdefault(address, []).append(
                (index, int(match.group(2), 16))
            )
    candidates = []
    for address, occurrences in records.items():
        if (len(occurrences) == 1 and occurrences[0][1] == current[0]
            and all(
            len(records.get(address + 8 * offset, [])) == 1
            and records[address + 8 * offset][0][1] == expected
            for offset, expected in enumerate(current)
        )):
            candidates.append(address)
    if len(candidates) != 1:
        raise ValueError(
            f"expected one exact contiguous prefix table, found {len(candidates)}"
        )
    base = candidates[0]
    if base + 8 * len(current) > linux_payload_base:
        raise ValueError("prefix table overlaps the Linux payload boundary")
    output = list(lines)
    changed = []
    for offset, (old, new) in enumerate(zip(current, replacement)):
        if old == new:
            continue
        address = base + 8 * offset
        index, observed = records[address][0]
        if observed != old:
            raise ValueError(f"prefix record changed during patch at 0x{address:x}")
        output[index] = f"03_{address:016x}_{new:016x}"
        changed.append(address)
    if not changed:
        raise ValueError("replacement prefix does not change the NBF")
    return output, base, changed


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("current_prefix", type=Path)
    parser.add_argument("replacement_prefix", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--linux-payload-base", type=lambda value: int(value, 0),
                        default=0x80200000)
    args = parser.parse_args(argv)
    for path in (args.source, args.current_prefix, args.replacement_prefix):
        if not path.is_file():
            raise SystemExit(f"missing input: {path}")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite output: {args.output}")
    try:
        current = load_prefix(args.current_prefix)
        replacement = load_prefix(args.replacement_prefix)
        result, base, changed = patch(
            args.source.read_text().splitlines(), current, replacement,
            args.linux_payload_base,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    args.output.write_text("\n".join(result) + "\n")
    print(f"SOURCE_SHA256={sha256(args.source)}")
    print(f"OUTPUT_SHA256={sha256(args.output)}")
    print(f"TABLE_BASE=0x{base:016x}")
    print(f"CHANGED_RECORDS={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
