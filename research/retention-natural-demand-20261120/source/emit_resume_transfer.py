#!/usr/bin/env python3
"""Emit a bounded, deterministic compressed transfer for the fixed guest path."""

import argparse
import base64
import gzip
from pathlib import Path

from run_scheduler_pipe_hint import GUEST_ELF, embedded_commands, sha256


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
    parser.add_argument("--embedded-source",
                        help="copy this simple name from /opt/bp-resume in a separately bound image")
    parser.add_argument("--zlib-library", type=Path,
                        help="bind an embedded libz.so.1; requires --embedded-source")
    args = parser.parse_args()
    if args.zlib_library is not None and args.embedded_source is None:
        parser.error("--zlib-library requires --embedded-source")
    if args.embedded_source is None:
        result = commands(args.elf)
    else:
        try:
            result = embedded_commands(sha256(args.elf), args.embedded_source,
                                       sha256(args.zlib_library) if args.zlib_library else None)
        except ValueError as error:
            parser.error(str(error))
    print("\n".join(result))
