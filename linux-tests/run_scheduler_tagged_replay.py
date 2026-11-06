#!/usr/bin/env python3
"""Run one tagged Linux replay experiment on the serialized PYNQ console."""

import argparse
import base64
import binascii
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
TIMER_GUARD_MARKER = "BP_REPLAY_TIMER_GUARD"
KERNEL_FAILURE_MARKER = re.compile(
    r"(?:BUG:|Kernel panic|Oops(?:[: ]|\r?\n)|scheduling while atomic|"
    r"Segmentation fault|unhandled signal [0-9]+|RT throttling activated)"
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def benchmark_command(mode, delay, gap, policy, lead_cycles, lines_per_base=8,
                      probe_status=False, layout="aligned", sync="pipe",
                      guest_diagnostic=False, trace_icache=False,
                      trace_icache_entry=False):
    prefix = "BP_TAGGED_REPLAY_DIAG=1 " if guest_diagnostic else ""
    trace_arg = (" trace-icache-entry" if trace_icache_entry else
                 " trace-icache" if trace_icache else "")
    return (
        f"{prefix}{GUEST_ELF} {mode} {delay} {gap} {policy} {lead_cycles} "
        f"{lines_per_base} {int(probe_status)} {layout} {sync}"
        f"{trace_arg}; "
        "rc=$?; echo TAGGED_REPLAY_EXIT rc=$rc"
    )


def validate_transfer(path, elf_sha256):
    """Accept only the generated base64 transfer for the bound guest ELF."""
    commands = path.read_text().splitlines()
    b64_path = GUEST_ELF + ".b64"
    if any(len(command) > MAX_GUEST_COMMAND_LENGTH for command in commands):
        raise ValueError(
            f"transfer command exceeds {MAX_GUEST_COMMAND_LENGTH} characters"
        )
    if len(commands) < 4 or commands[0] != f": > {b64_path}" or commands[-2:] != [
            f"base64 -d {b64_path} > {GUEST_ELF}", f"chmod +x {GUEST_ELF}"]:
        raise ValueError("transfer contains unexpected shell commands")
    payload = []
    pattern = re.compile(
        r"echo '([A-Za-z0-9+/=]+)' >> " + re.escape(b64_path)
    )
    for command in commands[1:-2]:
        match = pattern.fullmatch(command)
        if match is None:
            raise ValueError("transfer contains unexpected shell commands")
        payload.append(match.group(1))
    try:
        decoded = base64.b64decode("".join(payload), validate=True)
    except binascii.Error as error:
        raise ValueError("transfer contains invalid base64") from error
    if hashlib.sha256(decoded).hexdigest() != elf_sha256:
        raise ValueError("transfer payload does not match ELF SHA-256")


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
    parser.add_argument("--transfer-timeout-s", type=int, default=180)
    parser.add_argument("--mode", choices=("off", "data", "data-late",
                                            "instruction-select",
                                            "instruction-wake", "joint",
                                            "joint-split",
                                            "joint-split-one-hook",
                                            "joint-follow-only"),
                        default="data")
    parser.add_argument("--delay", type=int, default=0)
    parser.add_argument("--gap", type=int, default=2)
    parser.add_argument("--policy", choices=("normal", "fifo"), default="fifo")
    parser.add_argument("--lead-cycles", type=int, default=0)
    parser.add_argument("--lines-per-base", type=int, default=8)
    parser.add_argument("--probe-status", action="store_true")
    parser.add_argument("--layout", choices=("aligned", "skew"),
                        default="aligned")
    parser.add_argument("--sync", choices=("pipe", "futex"), default="pipe")
    parser.add_argument("--guest-diagnostic", action="store_true")
    trace_group = parser.add_mutually_exclusive_group()
    trace_group.add_argument("--trace-icache", action="store_true")
    trace_group.add_argument("--trace-icache-entry", action="store_true")
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
    if not 1 <= args.lines_per_base <= 8:
        raise ValueError("lines per base must be in 1..8")
    if args.runtime_ms <= 0:
        raise ValueError("runtime limit must be positive")
    if args.transfer_timeout_s <= 0:
        raise ValueError("transfer timeout must be positive")
    if not args.nbf.is_file() or not args.transfer.is_file():
        raise ValueError("NBF and transfer files must exist")
    validate_transfer(args.transfer, args.elf_sha256)
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
        args.mode, args.delay, args.gap, args.policy, args.lead_cycles,
        args.lines_per_base, args.probe_status, args.layout, args.sync,
        args.guest_diagnostic, args.trace_icache, args.trace_icache_entry,
    )
    status = {
        "status": "running",
        "nbf_sha256": sha256(args.nbf),
        "transfer_sha256": sha256(args.transfer),
        "elf_sha256": args.elf_sha256,
        "control_program_sha256": args.control_sha256,
        "bitstream_sha256": args.bitstream_sha256,
        "transfer_timeout_s": args.transfer_timeout_s,
        "mode": args.mode,
        "delay": args.delay,
        "gap": args.gap,
        "policy": args.policy,
        "lead_cycles": args.lead_cycles,
        "lines_per_base": args.lines_per_base,
        "probe_status": args.probe_status,
        "layout": args.layout,
        "sync": args.sync,
        "guest_diagnostic": args.guest_diagnostic,
        "trace_icache": args.trace_icache or args.trace_icache_entry,
        "trace_icache_entry": args.trace_icache_entry,
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
                child.expect(SHELL_PROMPT, timeout=args.transfer_timeout_s)
            child.sendline(f"/bin/busybox sha256sum {GUEST_ELF}")
            child.expect_exact(f"{args.elf_sha256}  {GUEST_ELF}")
            child.expect(SHELL_PROMPT)
            child.sendline(command)
            outcome = child.expect([
                re.compile(r"TAGGED_REPLAY_EXIT rc=([0-9]+)\r*\n"),
                re.compile(TIMER_GUARD_MARKER + r"[^\r\n]*"),
                KERNEL_FAILURE_MARKER,
            ], timeout=1800)
            if outcome == 1:
                raise RuntimeError(
                    "timer callback integrity guard fired: " + child.match.group(0)
                )
            if outcome == 2:
                raise RuntimeError(
                    "kernel failure marker: " + child.match.group(0)
                )
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
        if ((args.trace_icache or args.trace_icache_entry)
                and "TAGGED_REPLAY_ITRACE_PASS" not in transcript):
            raise RuntimeError("required instruction-trace marker missing")
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
            args.mode, args.delay, args.gap, args.policy, args.lead_cycles,
            args.lines_per_base, args.probe_status, args.layout, args.sync,
            args.guest_diagnostic, args.trace_icache,
            args.trace_icache_entry,
        ))
        return 0
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
