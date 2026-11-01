#!/usr/bin/env python3
"""Replace one exact Linux payload in an NBF while preserving all collateral."""

import argparse
from pathlib import Path


MEMORY_COMMANDS = {0: 1, 1: 2, 2: 4, 3: 8}


def parse_line(line):
    fields = line.strip().split("_")
    if len(fields) != 3:
        raise ValueError(f"malformed NBF line: {line.rstrip()}")
    return tuple(int(field, 16) for field in fields)


def nonzero_blocks(payload, base):
    """Return the canonical skip-zero 64-bit writes for one payload."""
    if len(payload) % 8:
        raise ValueError("kernel payload length must be 8-byte aligned")
    return {
        base + offset: int.from_bytes(payload[offset:offset + 8], "little")
        for offset in range(0, len(payload), 8)
        if any(payload[offset:offset + 8])
    }


def splice(source, old_payload, new_payload, output, base=0x80200000):
    """Fail closed unless source contains the exact old canonical payload."""
    old_data = Path(old_payload).read_bytes()
    new_data = Path(new_payload).read_bytes()
    if len(old_data) != len(new_data):
        raise ValueError(
            f"payload size differs: old={len(old_data)} new={len(new_data)}"
        )
    end = base + len(old_data)
    expected = nonzero_blocks(old_data, base)
    replacement = nonzero_blocks(new_data, base)
    lines = Path(source).read_text(encoding="ascii").splitlines(keepends=True)
    observed = {}
    indices = []
    for index, line in enumerate(lines):
        command, address, data = parse_line(line)
        width = MEMORY_COMMANDS.get(command)
        if width is None:
            continue
        overlaps = address < end and address + width > base
        if not overlaps:
            continue
        if command != 3 or address % 8 or not (base <= address < end):
            raise ValueError(
                f"noncanonical payload write at line {index + 1}: {line.rstrip()}"
            )
        if address in observed:
            raise ValueError(f"duplicate payload write at 0x{address:x}")
        observed[address] = data
        indices.append(index)
    if observed != expected:
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        wrong = sorted(
            address for address in set(expected) & set(observed)
            if expected[address] != observed[address]
        )
        raise ValueError(
            "source NBF does not encode the exact old payload: "
            f"missing={len(missing)} extra={len(extra)} wrong={len(wrong)}"
        )
    if not indices:
        raise ValueError("source NBF contains no payload writes")
    first = indices[0]
    index_set = set(indices)
    replacement_lines = [
        f"03_{address:016x}_{replacement[address]:016x}\n"
        for address in sorted(replacement)
    ]
    result = []
    for index, line in enumerate(lines):
        if index == first:
            result.extend(replacement_lines)
        if index not in index_set:
            result.append(line)
    Path(output).write_text("".join(result), encoding="ascii")
    return {
        "base": base,
        "bytes": len(old_data),
        "old_records": len(expected),
        "new_records": len(replacement),
        "preserved_records": len(lines) - len(indices),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("old_payload", type=Path)
    parser.add_argument("new_payload", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base", type=lambda text: int(text, 0),
                        default=0x80200000)
    args = parser.parse_args(argv)
    summary = splice(
        args.source, args.old_payload, args.new_payload, args.output, args.base
    )
    print(
        "KERNEL_NBF_SPLICE "
        + " ".join(f"{key}={value}" for key, value in summary.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
