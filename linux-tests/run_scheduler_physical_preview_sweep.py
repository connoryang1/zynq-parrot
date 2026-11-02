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
MAX_GUEST_COMMAND_LENGTH = 768


def cell_plan():
    """Alternate timing order by set group while covering every cell once."""
    cells = []
    for group in range(8):
        timings = ("early", "late") if group % 2 == 0 else ("late", "early")
        cells.extend((group, timing) for timing in timings)
    return cells


def selected_cells(start_cell, only_timing=None, only_group=None):
    """Return a disjoint suffix, optionally filtered to one timing."""
    if only_timing in ("instruction", "counter", "trigger", "wake-trigger",
                       "wake-data", "wake-early-data"):
        cells = [(group, only_timing) for group in range(8)]
        if start_cell < 0 or start_cell >= len(cells):
            raise ValueError(
                f"start cell must be in 0..{len(cells) - 1} for {only_timing}"
            )
        cells = cells[start_cell:]
        if only_group is not None:
            cells = [cell for cell in cells if cell[0] == only_group]
        if not cells:
            raise ValueError("cell selection is empty")
        return cells
    cells = cell_plan()
    if start_cell < 0 or start_cell >= len(cells):
        raise ValueError(f"start cell must be in 0..{len(cells) - 1}")
    cells = cells[start_cell:]
    if only_timing is not None:
        cells = [cell for cell in cells if cell[1] == only_timing]
    if only_group is not None:
        cells = [cell for cell in cells if cell[0] == only_group]
    if not cells:
        raise ValueError("cell selection is empty")
    return cells


def cell_exit_pattern(group, timing):
    """Match board markers despite the UART bridge's repeated CR bytes."""
    return re.compile(
        rf"PHYSICAL_CELL_EXIT group={group} timing={timing} rc=([0-9]+)\r*\n"
    )


def benchmark_command(group, timing, footprint, policy="normal",
                      replay_state="persistent", arm="alternating", lines=4,
                      lead_cycles=0):
    """Build the guest command while preserving the historical default CLI."""
    guest_args = f"{group} {timing}"
    if (footprint != "target" or policy != "normal"
            or replay_state != "persistent" or arm != "alternating"
            or lines != 4 or lead_cycles):
        guest_args += f" {footprint}"
    if (policy != "normal" or replay_state != "persistent"
            or arm != "alternating" or lines != 4 or lead_cycles):
        guest_args += f" {policy}"
    if replay_state != "persistent":
        guest_args += f" {replay_state}"
    elif arm != "alternating" or lines != 4 or lead_cycles:
        guest_args += " persistent"
    if arm != "alternating":
        guest_args += f" {arm}"
    elif lines != 4 or lead_cycles:
        guest_args += " alternating"
    if lines != 4:
        guest_args += f" {lines}"
    elif lead_cycles:
        guest_args += " 4"
    if lead_cycles:
        guest_args += f" {lead_cycles}"
    return (
        f"{GUEST_ELF} {guest_args}; "
        f"rc=$?; echo PHYSICAL_CELL_EXIT group={group} "
        f"timing={timing} rc=$rc"
    )


def elf_hash_command():
    """Use BusyBox directly so an absent applet symlink cannot skip the gate."""
    return f"/bin/busybox sha256sum {GUEST_ELF}"


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
    parser.add_argument("--bitstream-sha256")
    parser.add_argument("--runtime-ms", type=int, default=3_600_000)
    parser.add_argument("--footprint", choices=("target", "hot-proxy"),
                        default="target")
    parser.add_argument("--policy", choices=("normal", "fifo"),
                        default="normal")
    parser.add_argument("--replay-state", choices=("persistent", "isolated"),
                        default="isolated")
    parser.add_argument("--arm", choices=("alternating", "disabled", "enabled"),
                        default="alternating")
    parser.add_argument("--lines", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--lead-cycles", type=int, choices=range(0, 1_000_001),
                        default=0)
    parser.add_argument("--only-timing",
                        choices=("early", "late", "instruction", "counter",
                                 "trigger", "wake-trigger", "wake-data",
                                 "wake-early-data"))
    parser.add_argument("--start-cell", type=int, default=0,
                        help="zero-based cell-plan index for a recovered suffix run")
    parser.add_argument("--only-group", type=int, choices=range(8))
    parser.add_argument("--print-plan", action="store_true")
    return parser.parse_args(argv)


def validate_args(args):
    for label, value in (("ELF", args.elf_sha256),
                         ("control program", args.control_sha256)):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{label} SHA-256 must be 64 lowercase hex digits")
    if args.bitstream_sha256 is not None and not re.fullmatch(
            r"[0-9a-f]{64}", args.bitstream_sha256):
        raise ValueError("bitstream SHA-256 must be 64 lowercase hex digits")
    if args.runtime_ms <= 0:
        raise ValueError("runtime limit must be positive")
    selected_cells(args.start_cell, args.only_timing, args.only_group)
    if not args.nbf.is_file() or not args.transfer.is_file():
        raise ValueError("NBF and transfer files must exist")
    if any(len(command) > MAX_GUEST_COMMAND_LENGTH
           for command in args.transfer.read_text().splitlines()):
        raise ValueError(
            f"transfer command exceeds {MAX_GUEST_COMMAND_LENGTH} characters"
        )
    if not args.log.parent.is_dir():
        raise ValueError("log parent directory must exist before board launch")


def run(args):
    repo = Path(__file__).resolve().parents[1]
    runner = repo / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh"
    env = os.environ.copy()
    env["PYNQ_CONTROL_PROGRAM_SHA256"] = args.control_sha256
    env["PYNQ_CONTROL_PROGRAM_TIMEOUT_MS"] = str(args.runtime_ms)
    if args.bitstream_sha256 is not None:
        env["PYNQ_BITSTREAM_SHA256"] = args.bitstream_sha256
    status_path = args.log.with_suffix(args.log.suffix + ".status.json")
    status = {
        "status": "running",
        "nbf_sha256": sha256(args.nbf),
        "transfer_sha256": sha256(args.transfer),
        "elf_sha256": args.elf_sha256,
        "control_program_sha256": args.control_sha256,
        "bitstream_sha256": args.bitstream_sha256,
        "footprint": args.footprint,
        "policy": args.policy,
        "replay_state": args.replay_state,
        "arm": args.arm,
        "lines": args.lines,
        "lead_cycles": args.lead_cycles,
        "cells": [f"{group}:{timing}"
                  for group, timing in selected_cells(
                      args.start_cell, args.only_timing, args.only_group)],
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
            # Invoke the applet through the required BusyBox binary. One
            # otherwise healthy boot lacked the optional /usr/bin symlink,
            # and waiting for a hash that could never print wasted the arm.
            child.sendline(elf_hash_command())
            child.expect_exact(f"{args.elf_sha256}  {GUEST_ELF}")
            child.expect(SHELL_PROMPT)
            for group, timing in selected_cells(
                    args.start_cell, args.only_timing, args.only_group):
                child.sendline(benchmark_command(
                    group, timing, args.footprint, args.policy,
                    args.replay_state, args.arm, args.lines, args.lead_cycles
                ))
                child.expect(cell_exit_pattern(group, timing), timeout=900)
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
        for group, timing in selected_cells(
                args.start_cell, args.only_timing, args.only_group):
            print(group, timing)
        return 0
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
