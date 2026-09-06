#!/usr/bin/env python3
"""Keep NBF configuration records and memory below a handoff cutoff."""
import argparse
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--cutoff", type=lambda x: int(x, 0), default=0x80210000)
    a = p.parse_args()
    kept = []
    dropped = 0
    for line in a.source.read_text(encoding="ascii").splitlines(True):
        fields = line.strip().split("_")
        if len(fields) != 3:
            raise SystemExit(f"malformed NBF: {line!r}")
        command, address = int(fields[0], 16), int(fields[1], 16)
        # Commands 0..3 are memory writes. Keep firmware and a small Linux
        # entry window; retain all non-memory configuration/unfreeze records.
        if command <= 3 and address >= a.cutoff:
            dropped += 1
            continue
        kept.append(line)
    a.output.write_text("".join(kept), encoding="ascii")
    print(f"kept={len(kept)} dropped_memory_writes={dropped} cutoff=0x{a.cutoff:x}")


if __name__ == "__main__":
    main()
