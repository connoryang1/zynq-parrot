#!/usr/bin/env python3
"""Run one tagged 32-line Linux replay experiment on the serialized PYNQ console."""

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
GUEST_ELF = "/tmp/scheduler_tagged_replay_benchmark_dynamic"
SHELL_PROMPT = re.compile(r"(?:^|\r?\n)(?:~ )?# ")
MAX_GUEST_COMMAND_LENGTH = 768


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def benchmark_command(mode, delay, gap, policy, lead_cycles):
    return (
        f"{GUEST_ELF} {mode} {delay} {gap} {policy} {lead_cycles}; "
        "rc=$?; echo TAGGED_REPLAY_EXIT rc=$rc"
    )


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
    parser.add_argument("--mode", choices=("data", "joint"), default="data")
    parser.add_argument("--delay", type=int, default=0)
    parser.add_argument("--gap", type=int, default=2)
    parser.add_argument("--policy", choices=("normal", "fifo"), default="fifo")
    parser.add_argument("--lead-cycles", type=int, default=0)
    parser.add_argument("--print-command", action="store_true")
    return parser.parse_args(argv)


def validate_args(args):
    for label, value in (("ELF", args.elf_sha256),
                         ("control program", args.control_sha256)):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{label} SHA-256 must be 64 lowercase hex digits")
    if args.bitstream_sha256 is not None and not re.fullmatch(
            r"[0-9a-f]{64}", args.bitstream_sha256):
        raise ValueError("bitstream SHA-256 must be 64 lowercase hex digits")
    if not 0 <= args.delay <= 65535:
        raise ValueError("delay must be in 0..65535")
    if not 0 <= args.gap <= 255:
        raise ValueError("gap must be in 0..255")
    if not 0 <= args.lead_cycles <= 1_000_000:
        raise ValueError("lead cycles must be in 0..1000000")
    if args.runtime_ms <= 0:
        raise ValueError("runtime limit must be positive")
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
    command = benchmark_command(
        args.mode, args.delay, args.gap, args.policy, args.lead_cycles
    )
    status = {
        "status": "running",
        "nbf_sha256": sha256(args.nbf),
        "transfer_sha256": sha256(args.transfer),
        "elf_sha256": args.elf_sha256,
        "control_program_sha256": args.control_sha256,
        "bitstream_sha256": args.bitstream_sha256,
        "mode": args.mode,
        "delay": args.delay,
        "gap": args.gap,
        "policy": args.policy,
        "lead_cycles": args.lead_cycles,
        "command": command,
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
            for transfer_command in args.transfer.read_text().splitlines():
                child.sendline(transfer_command)
                child.expect(SHELL_PROMPT, timeout=60)
            child.sendline(f"/bin/busybox sha256sum {GUEST_ELF}")
            child.expect_exact(f"{args.elf_sha256}  {GUEST_ELF}")
            child.expect(SHELL_PROMPT)
            child.sendline(command)
            child.expect(re.compile(r"TAGGED_REPLAY_EXIT rc=([0-9]+)\r*\n"),
                         timeout=1800)
            rc = int(child.match.group(1))
            if rc:
                raise RuntimeError(f"tagged replay benchmark exited {rc}")
            child.expect(SHELL_PROMPT)
            child.sendline("poweroff -f")
            child.expect(re.compile(r"CORE(?:\[0\])? PASS"), timeout=180)
            child.expect(pexpect.EOF, timeout=180)
        child.close()
        if child.exitstatus != 0 or child.signalstatus is not None:
            raise RuntimeError(
                f"interactive runner exit={child.exitstatus} signal={child.signalstatus}"
            )
        transcript = args.log.read_text(errors="replace")
        for marker in ("TAGGED_REPLAY_CHILD PASS", "TAGGED_REPLAY_PARENT PASS",
                       "BSG PASS"):
            if marker not in transcript:
                raise RuntimeError(f"required marker missing: {marker}")
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
    if args.print_command:
        print(benchmark_command(
            args.mode, args.delay, args.gap, args.policy, args.lead_cycles
        ))
        return 0
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
