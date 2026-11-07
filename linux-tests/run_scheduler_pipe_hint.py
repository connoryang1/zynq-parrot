#!/usr/bin/env python3
"""Run one sustained pipe-hint comparison on the serialized PYNQ console."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re

import pexpect

from run_scheduler_tagged_replay import (
    DEFAULT_CONTROL_SHA,
    DEFAULT_HOST,
    KERNEL_FAILURE_MARKER,
    SHELL_PROMPT,
    TIMER_GUARD_MARKER,
    expect_shell_prompt,
)


GUEST_ELF = "/tmp/scheduler_pipe_hint_benchmark_dynamic"
MAX_GUEST_COMMAND_LENGTH = 768


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_transfer(path, elf_sha256):
    """Accept only the generated shell transfer for the bound guest ELF."""
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
    pattern = re.compile(r"echo '([A-Za-z0-9+/=]+)' >> " + re.escape(b64_path))
    for command in commands[1:-2]:
        match = pattern.fullmatch(command)
        if match is None:
            raise ValueError("transfer contains unexpected shell commands")
        payload.append(match.group(1))
    decoded = base64.b64decode("".join(payload), validate=True)
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
    parser.add_argument("--bitstream-sha256", required=True)
    parser.add_argument("--loops", type=int, default=512)
    parser.add_argument("--repeats", type=int, default=8)
    parser.add_argument("--runtime-ms", type=int, default=3_600_000)
    return parser.parse_args(argv)


def validate_args(args):
    for label, value in (("ELF", args.elf_sha256),
                         ("control program", args.control_sha256),
                         ("bitstream", args.bitstream_sha256)):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{label} SHA-256 must be 64 lowercase hex digits")
    if not 1 <= args.loops <= 1_000_000 or not 1 <= args.repeats <= 1_000_000:
        raise ValueError("loops and repeats must be in 1..1000000")
    if not args.nbf.is_file() or not args.transfer.is_file():
        raise ValueError("NBF and transfer files must exist")
    if not args.log.parent.is_dir():
        raise ValueError("log parent directory must exist")
    validate_transfer(args.transfer, args.elf_sha256)


def run(args):
    repo = Path(__file__).resolve().parents[1]
    runner = repo / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh"
    status_path = args.log.with_suffix(args.log.suffix + ".status.json")
    command = f"{GUEST_ELF} {args.loops} {args.repeats}"
    status = {
        "status": "running",
        "nbf_sha256": sha256(args.nbf),
        "transfer_sha256": sha256(args.transfer),
        "elf_sha256": args.elf_sha256,
        "control_program_sha256": args.control_sha256,
        "bitstream_sha256": args.bitstream_sha256,
        "loops": args.loops,
        "repeats": args.repeats,
        "command": command,
    }
    env = os.environ.copy()
    env["PYNQ_CONTROL_PROGRAM_SHA256"] = args.control_sha256
    env["PYNQ_CONTROL_PROGRAM_TIMEOUT_MS"] = str(args.runtime_ms)
    env["PYNQ_BITSTREAM_SHA256"] = args.bitstream_sha256
    child = None
    try:
        child = pexpect.spawn(
            str(runner), [args.host, str(args.nbf)], env=env,
            encoding="utf-8", timeout=300,
        )
        child.setwinsize(50, 180)
        with args.log.open("w") as log:
            child.logfile_read = log
            expect_shell_prompt(child, 300, "Linux boot")
            for transfer_command in args.transfer.read_text().splitlines():
                child.sendline(transfer_command)
                expect_shell_prompt(child, 180, "guest ELF transfer")
            child.sendline(f"/bin/busybox sha256sum {GUEST_ELF}")
            child.expect_exact(f"{args.elf_sha256}  {GUEST_ELF}")
            expect_shell_prompt(child, 300, "guest ELF verification")
            child.sendline(command)
            outcome = child.expect([
                re.compile(r"PIPE_HINT_PASS\r*\n"),
                re.compile(TIMER_GUARD_MARKER + r"[^\r\n]*"),
                KERNEL_FAILURE_MARKER,
                SHELL_PROMPT,
            ], timeout=1800)
            if outcome == 1:
                raise RuntimeError("timer callback integrity guard fired")
            if outcome == 2:
                raise RuntimeError("kernel failure marker: " + child.match.group(0))
            if outcome == 3:
                raise RuntimeError("benchmark returned to shell before PIPE_HINT_PASS")
            expect_shell_prompt(child, 300, "benchmark completion")
            child.sendline("poweroff -f")
            child.expect(re.compile(r"CORE(?:\[0\])? PASS"), timeout=180)
            child.expect(pexpect.EOF, timeout=180)
        child.close()
        if child.exitstatus != 0 or child.signalstatus is not None:
            raise RuntimeError(
                f"interactive runner exit={child.exitstatus} signal={child.signalstatus}"
            )
        transcript = args.log.read_text(errors="replace")
        for marker in ("PIPE_HINT_PASS", "BSG PASS"):
            if marker not in transcript:
                raise RuntimeError(f"required marker missing: {marker}")
        status.update(status="PASS", runner_exit=0)
    except (Exception, KeyboardInterrupt) as error:
        status.update(
            status="FAIL", error=repr(error),
            recovery=("Power-cycle the board, wait for PYNQ readiness, and reload "
                      "the verified overlay before another run."),
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
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
