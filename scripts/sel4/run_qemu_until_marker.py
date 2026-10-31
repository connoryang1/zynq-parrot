#!/usr/bin/env python3
"""Run a seL4 simulate script, capture its transcript, and exit QEMU on success."""

import argparse
from pathlib import Path
import sys

import pexpect


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("--marker", default="All is well in the universe")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("w", encoding="utf-8") as transcript:
        child = pexpect.spawn(
            str(build_dir / "simulate"),
            cwd=str(build_dir),
            encoding="utf-8",
            codec_errors="replace",
            timeout=args.timeout,
        )
        child.logfile_read = transcript
        outcome = child.expect_exact([args.marker, pexpect.EOF, pexpect.TIMEOUT])
        if outcome == 0:
            child.send("\x01x")
            child.expect(pexpect.EOF, timeout=10)
            child.close()
            print(args.marker)
            return 0 if child.exitstatus in (0, None) else child.exitstatus

        child.close(force=True)
        if outcome == 1:
            print("simulate exited before its success marker", file=sys.stderr)
        else:
            print("simulate timed out before its success marker", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
