#!/usr/bin/env python3
"""Transfer and run one exact cache-miss trace capture on serialized PYNQ."""

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
GUEST_ELF = "/tmp/cache_miss_trace_capture_dynamic"
PIPE_GUEST_ELF = "/tmp/scheduler_physical_preview_trace_capture_dynamic"
SHELL_PROMPT = re.compile(r"(?:^|\r?\n)(?:~ )?# ")
EXIT_MARKER = re.compile(r"TRACE_CAPTURE_EXIT rc=([0-9]+)\r*\n")


def sha256(path):
    """Return the lowercase SHA-256 of one local file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_command(window, samples, preview_mode="legacy", summary_only=False,
                    allow_overflow=False, final_addresses=False):
    """Build the bounded guest command from validated arguments."""
    command = f"{GUEST_ELF} --window {window}"
    if samples != 1:
        command += f" --samples {samples}"
    if preview_mode != "legacy":
        command += f" --preview-mode {preview_mode}"
    if summary_only:
        command += " --summary-only"
    if allow_overflow:
        command += " --allow-overflow"
    if final_addresses:
        command += " --final-addresses"
    return command + "; rc=$?; echo TRACE_CAPTURE_EXIT rc=$rc"


def guest_elf(args):
    """Return the fixed guest path for the selected bounded capture."""
    if args.program == "physical-preview-pipe":
        return PIPE_GUEST_ELF
    return GUEST_ELF


def guest_command(args):
    """Build the selected guest command without accepting shell text."""
    if args.program == "physical-preview-pipe":
        return (f"{PIPE_GUEST_ELF} {args.group} {args.preview_mode}; rc=$?; "
                "echo TRACE_CAPTURE_EXIT rc=$rc")
    return capture_command(args.window, args.samples, args.cache_preview_mode,
                           args.cache_summary_only,
                           args.cache_allow_overflow,
                           args.cache_final_addresses)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nbf", type=Path)
    parser.add_argument("transfer", type=Path)
    parser.add_argument("elf_sha256")
    parser.add_argument("log", type=Path)
    parser.add_argument("--window", choices=("full", "to-peer", "from-peer"),
                        default="full")
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--program",
                        choices=("cache-miss", "physical-preview-pipe"),
                        default="cache-miss")
    parser.add_argument("--group", type=int, default=0)
    parser.add_argument("--preview-mode",
                        choices=("disabled", "trigger", "wake-trigger"),
                        default="disabled")
    parser.add_argument("--cache-preview-mode",
                        choices=("legacy", "disabled", "trigger",
                                 "wake-trigger"),
                        default="legacy")
    parser.add_argument("--cache-summary-only", action="store_true")
    parser.add_argument("--cache-allow-overflow", action="store_true")
    parser.add_argument("--cache-final-addresses", action="store_true")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--control-sha256", default=DEFAULT_CONTROL_SHA)
    parser.add_argument("--bitstream-sha256")
    parser.add_argument("--runtime-ms", type=int, default=600_000)
    return parser.parse_args(argv)


def validate_args(args):
    for label, value in (("ELF", args.elf_sha256),
                         ("control program", args.control_sha256)):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{label} SHA-256 must be 64 lowercase hex digits")
    if args.bitstream_sha256 is not None and not re.fullmatch(
            r"[0-9a-f]{64}", args.bitstream_sha256):
        raise ValueError("bitstream SHA-256 must be 64 lowercase hex digits")
    if not args.nbf.is_file() or not args.transfer.is_file():
        raise ValueError("NBF and transfer files must exist")
    if not 1 <= args.samples <= 10_000:
        raise ValueError("samples must be in 1..10000")
    if not 0 <= args.group <= 7:
        raise ValueError("group must be in 0..7")
    if args.program == "physical-preview-pipe" and args.samples != 1:
        raise ValueError("physical-preview-pipe supports exactly one sample")
    if (args.cache_allow_overflow or args.cache_final_addresses) \
            and not args.cache_summary_only:
        raise ValueError("cache overflow/address capture requires summary-only timing")
    if args.program != "cache-miss" and (
            args.cache_preview_mode != "legacy" or args.cache_summary_only
            or args.cache_allow_overflow or args.cache_final_addresses):
        raise ValueError("cache options require the cache-miss program")
    if args.runtime_ms <= 0:
        raise ValueError("runtime limit must be positive")


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
        "window": args.window,
        "samples": args.samples,
        "program": args.program,
        "group": args.group,
        "preview_mode": args.preview_mode,
        "cache_preview_mode": args.cache_preview_mode,
        "cache_summary_only": args.cache_summary_only,
        "cache_allow_overflow": args.cache_allow_overflow,
        "cache_final_addresses": args.cache_final_addresses,
    }
    program = guest_elf(args)
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
            child.sendline(f"sha256sum {program}")
            child.expect_exact(f"{args.elf_sha256}  {program}")
            child.expect(SHELL_PROMPT)
            child.sendline(guest_command(args))
            child.expect(EXIT_MARKER, timeout=300)
            rc = int(child.match.group(1))
            if rc:
                raise RuntimeError(f"trace capture exited {rc}")
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
        guest_marker = ("TRACE_PASS" if args.program == "physical-preview-pipe"
                        else "TRACE_CAPTURE_PASS")
        if guest_marker not in text:
            raise RuntimeError(f"guest {guest_marker} marker missing")
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
        run(args)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    return 0


if __name__ == "__main__":
    sys.exit(main())
