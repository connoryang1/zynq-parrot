#!/usr/bin/env python3
"""Reject selected CSR instructions in executable ELF sections."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


def csr_number(text: str) -> int:
    value = text.lower()
    if value.startswith("0x"):
        value = value[2:]
    number = int(value, 16)
    if number < 0 or number > 0xFFF:
        raise argparse.ArgumentTypeError(f"CSR is outside 12 bits: {text}")
    return number


parser = argparse.ArgumentParser()
parser.add_argument("--objdump", required=True)
parser.add_argument("--section", action="append", default=[])
parser.add_argument("elf", type=Path)
parser.add_argument("csrs", nargs="+", type=csr_number)
args = parser.parse_args()

if not args.elf.is_file():
    parser.error(f"ELF not found: {args.elf}")

command = [args.objdump, "-d"]
for section in args.section:
    command.extend(["-j", section])
command.append(str(args.elf))
result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
if result.returncode:
    raise SystemExit(result.stderr or f"objdump exited {result.returncode}")

wanted = set(args.csrs)
instruction = re.compile(r"^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{8})\s+(.*)$")
collisions = []
for line in result.stdout.splitlines():
    match = instruction.match(line)
    if not match:
        continue
    word = int(match.group(2), 16)
    if word & 0x7F != 0x73 or (word >> 12) & 0x7 == 0:
        continue
    csr = (word >> 20) & 0xFFF
    if csr in wanted:
        collisions.append((int(match.group(1), 16), word, csr, match.group(3)))

for address, word, csr, disassembly in collisions:
    print(f"ELF_CSR_COLLISION elf={args.elf} address=0x{address:x} "
          f"instruction=0x{word:08x} csr=0x{csr:03x} disassembly={disassembly}")
if collisions:
    raise SystemExit(1)

sections = ",".join(args.section) if args.section else "all-executable"
csrs = ",".join(f"{csr:03x}" for csr in sorted(wanted))
print(f"ELF_CSR_COLLISION_FREE elf={args.elf} sections={sections} csrs={csrs}")
