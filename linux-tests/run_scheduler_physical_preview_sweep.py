#!/usr/bin/env python3
"""Run one complete physical-preview Linux sweep through the serialized PYNQ console."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import pexpect


DEFAULT_HOST = "xilinx@192.168.4.35"
DEFAULT_CONTROL_SHA = "2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30"
GUEST_ELF = "/tmp/scheduler_physical_preview_benchmark_dynamic"
SHELL_PROMPT = re.compile(r"(?:^|\r?\n)(?:~ )?# ")


def cell_plan():
    """Alternate timing order by set group while covering every cell once."""
    cells = []
    for group in range(8):
        timings = ("early", "late") if group % 2 == 0 else ("late", "early")
        cells.extend((group, timing) for timing in timings)
    return cells


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nbf", type=Path)
    parser.add_argument("transfer", type=Path)
    parser.add_argument("elf_sha256")
    parser.add_argument("log", type=Path)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--control-sha256", default=DEFAULT_CONTROL_SHA)
    parser.add_argument("--runtime-ms", type=int, default=3_600_000)
    parser.add_argument("--print-plan", action="store_true")
    return parser.parse_args(argv)


def validate_args(args):
    for label, value in (("ELF", args.elf_sha256),
                         ("control program", args.control_sha256)):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{label} SHA-256 must be 64 lowercase hex digits")
    if args.runtime_ms <= 0:
        raise ValueError("runtime limit must be positive")
    if not args.nbf.is_file() or not args.transfer.is_file():
        raise ValueError("NBF and transfer files must exist")


def run(args):
    repo = Path(__file__).resolve().parents[1]
    runner = repo / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh"
    env = os.environ.copy()
    env["PYNQ_CONTROL_PROGRAM_SHA256"] = args.control_sha256
    env["PYNQ_CONTROL_PROGRAM_TIMEOUT_MS"] = str(args.runtime_ms)
    status_path = args.log.with_suffix(args.log.suffix + ".status.json")
    status = {
        "status": "running",
        "nbf_sha256": sha256(args.nbf),
        "transfer_sha256": sha256(args.transfer),
        "elf_sha256": args.elf_sha256,
        "cells": [f"{group}:{timing}" for group, timing in cell_plan()],
    }
    child = None
    try:
        child = pexpect.spawn(
            str(runner),
            [args.host, str(args.nbf)],
            env=env,
            encoding="utf-8",
            timeout=300,
        )
        child.setwinsize(50, 180)
        with args.log.open("w") as log:
            child.logfile_read = log
            child.expect(SHELL_PROMPT)
            for command in args.transfer.read_text().splitlines():
                child.sendline(command)
                child.expect(SHELL_PROMPT, timeout=60)
            child.sendline(f"sha256sum {GUEST_ELF}")
            child.expect_exact(f"{args.elf_sha256}  {GUEST_ELF}")
            child.expect(SHELL_PROMPT)
            for group, timing in cell_plan():
                child.sendline(
                    f"{GUEST_ELF} {group} {timing}; "
                    f"rc=$?; echo PHYSICAL_CELL_EXIT group={group} "
                    f"timing={timing} rc=$rc"
                )
                child.expect(
                    rf"PHYSICAL_CELL_EXIT group={group} timing={timing} rc=([0-9]+)\r?\n",
                    timeout=900,
                )
                rc = int(child.match.group(1))
                if rc:
                    raise RuntimeError(
                        f"benchmark cell group={group} timing={timing} exited {rc}"
                    )
                child.expect(SHELL_PROMPT)
            child.sendline("poweroff -f")
            child.expect(re.compile(r"CORE(?:\[0\])? PASS"), timeout=180)
            child.expect(pexpect.EOF, timeout=180)
        child.close()
        if child.exitstatus != 0 or child.signalstatus is not None:
            raise RuntimeError(
                f"interactive runner exit={child.exitstatus} signal={child.signalstatus}"
            )
        text = args.log.read_text(errors="replace")
        if "BSG PASS" not in text:
            raise RuntimeError("host BSG PASS marker missing")
        status.update(status="PASS", runner_exit=0)
    except (Exception, KeyboardInterrupt) as error:
        status.update(
            status="FAIL",
            error=repr(error),
            recovery=(
                "Power-cycle the board, wait for PYNQ readiness, and reload the "
                "verified overlay before another run."
            ),
        )
        raise
    finally:
        status_path.write_text(json.dumps(status, indent=2) + "\n")
        if child is not None and child.isalive():
            child.close(force=True)


def main(argv=None):
    args = parse_args(argv)
    try:
        validate_args(args)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if args.print_plan:
        for group, timing in cell_plan():
            print(group, timing)
        return 0
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
