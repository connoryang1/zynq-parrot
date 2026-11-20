#!/usr/bin/env python3
"""Emit a bounded, deterministic compressed transfer for the fixed guest path."""

import argparse
import base64
import gzip
from pathlib import Path

from run_scheduler_pipe_hint import GUEST_ELF


def commands(elf):
    payload = base64.b64encode(gzip.compress(elf.read_bytes(), mtime=0)).decode("ascii")
    return [f": > {GUEST_ELF}.b64", *(
        f"echo '{payload[index:index + 512]}' >> {GUEST_ELF}.b64"
        for index in range(0, len(payload), 512)),
        f"base64 -d {GUEST_ELF}.b64 > {GUEST_ELF}.gz",
        f"/bin/busybox gunzip -c {GUEST_ELF}.gz > {GUEST_ELF}",
        f"chmod +x {GUEST_ELF}"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    args = parser.parse_args()
    print("\n".join(commands(args.elf)))
