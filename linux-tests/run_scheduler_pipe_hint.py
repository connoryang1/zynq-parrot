#!/usr/bin/env python3
"""Run one sustained pipe-hint comparison on the serialized PYNQ console."""

import argparse
import base64
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import zlib

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
GUEST_ZLIB = "/tmp/libz.so.1"
MAX_GUEST_COMMAND_LENGTH = 768


def library_transfer(path):
    """Generate bounded, fixed-destination commands for an optional RV64 library."""
    # Reduce shell command count before timing. BusyBox gunzip is enabled in
    # the bound rootfs; the runner verifies the original decompressed bytes.
    payload = base64.b64encode(gzip.compress(path.read_bytes(), mtime=0)).decode("ascii")
    return [f": > {GUEST_ZLIB}.b64", *(
        f"echo '{payload[index:index + 512]}' >> {GUEST_ZLIB}.b64"
        for index in range(0, len(payload), 512)),
        f"base64 -d {GUEST_ZLIB}.b64 > {GUEST_ZLIB}.gz",
        f"/bin/busybox gunzip -c {GUEST_ZLIB}.gz > {GUEST_ZLIB}"]


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
    plain_tail = [f"base64 -d {b64_path} > {GUEST_ELF}", f"chmod +x {GUEST_ELF}"]
    gzip_tail = [f"base64 -d {b64_path} > {GUEST_ELF}.gz",
                 f"/bin/busybox gunzip -c {GUEST_ELF}.gz > {GUEST_ELF}",
                 f"chmod +x {GUEST_ELF}"]
    compressed = commands[-3:] == gzip_tail
    tail = gzip_tail if compressed else plain_tail
    if (len(commands) < len(tail) + 2 or commands[0] != f": > {b64_path}"
            or commands[-len(tail):] != tail):
        raise ValueError("transfer contains unexpected shell commands")
    payload = []
    pattern = re.compile(r"echo '([A-Za-z0-9+/=]+)' >> " + re.escape(b64_path))
    for command in commands[1:-len(tail)]:
        match = pattern.fullmatch(command)
        if match is None:
            raise ValueError("transfer contains unexpected shell commands")
        payload.append(match.group(1))
    decoded = base64.b64decode("".join(payload), validate=True)
    if compressed:
        try:
            decoded = gzip.decompress(decoded)
        except (OSError, EOFError, zlib.error) as error:
            raise ValueError("invalid gzip ELF payload") from error
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
    parser.add_argument("--policy", choices=("continuous", "continuous-unmatched",
                                              "futex-early", "futex-early-both",
                                              "seed", "preseed", "retention-rr", "retention-first"),
                        default="continuous")
    parser.add_argument("--warmup", type=int, default=32)
    parser.add_argument("--sync", choices=("pipe", "futex"), default="pipe")
    parser.add_argument("--profile", choices=("plain", "legs"), default="plain")
    parser.add_argument("--working-set-kib", type=int, default=0)
    parser.add_argument("--workload", choices=("scan", "lookup", "parse", "chase", "deflate"),
                        default="scan")
    parser.add_argument("--zlib-library", type=Path,
                        help="exact RV64 libz.so.1 staged with this ELF and bound by SHA-256")
    parser.add_argument("--retention-probe", choices=("absent", "present"),
                        help="run the separately bound ABI diagnostic instead of a benchmark")
    parser.add_argument("--legacy-no-terminal-handshake", action="store_true",
                        help="bind an older seven-argument guest without the final verification barrier")
    parser.add_argument(
        "--legacy-four-arg-cli", action="store_true",
        help=("invoke the preserved pre-sync/profile benchmark ABI; valid only "
              "for pipe/plain runs"),
    )
    parser.add_argument("--runtime-ms", type=int, default=3_600_000)
    return parser.parse_args(argv)


def validate_args(args):
    for label, value in (("ELF", args.elf_sha256),
                         ("control program", args.control_sha256),
                         ("bitstream", args.bitstream_sha256)):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{label} SHA-256 must be 64 lowercase hex digits")
    if (not 1 <= args.loops <= 1_000_000
            or not 1 <= args.repeats <= 1_000_000
            or not 1 <= args.warmup <= 1_000_000):
        raise ValueError("loops, repeats, and warmup must be in 1..1000000")
    if not 0 <= args.working_set_kib <= 65536:
        raise ValueError("working-set-kib must be in 0..65536")
    if args.profile == "legs" and args.sync != "futex":
        raise ValueError("legs profile requires futex synchronization")
    if args.policy in ("futex-early", "futex-early-both") and args.sync != "futex":
        raise ValueError("futex-early policy requires futex synchronization")
    if args.legacy_four_arg_cli and (args.sync != "pipe" or args.profile != "plain"
                                     or args.working_set_kib or args.workload != "scan"):
        raise ValueError("legacy four-argument CLI requires pipe/plain")
    if args.retention_probe and (args.legacy_four_arg_cli or args.zlib_library is not None):
        raise ValueError("retention ABI probe requires its own ELF and no optional library")
    if not args.nbf.is_file() or not args.transfer.is_file():
        raise ValueError("NBF and transfer files must exist")
    if args.zlib_library is not None and not args.zlib_library.is_file():
        raise ValueError("zlib library must exist")
    if not args.log.parent.is_dir():
        raise ValueError("log parent directory must exist")
    validate_transfer(args.transfer, args.elf_sha256)


def build_guest_command(args):
    if args.retention_probe:
        return f"{GUEST_ELF} {args.retention_probe}"
    command = (f"{GUEST_ELF} {args.loops} {args.repeats} {args.policy} "
               f"{args.warmup}")
    if not args.legacy_four_arg_cli:
        command += f" {args.sync} {args.profile} {args.working_set_kib}"
        if args.workload != "scan":
            command += f" {args.workload}"
    if args.zlib_library is not None:
        command = "LD_LIBRARY_PATH=/tmp " + command
    return command


def run(args):
    repo = Path(__file__).resolve().parents[1]
    runner = repo / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh"
    status_path = args.log.with_suffix(args.log.suffix + ".status.json")
    command = build_guest_command(args)
    pass_marker = (f"ICACHE_RETENTION_PROBE_PASS capability={args.retention_probe}"
                   if args.retention_probe else "PIPE_HINT_PASS")
    status = {
        "status": "running",
        "nbf_sha256": sha256(args.nbf),
        "transfer_sha256": sha256(args.transfer),
        "elf_sha256": args.elf_sha256,
        "control_program_sha256": args.control_sha256,
        "bitstream_sha256": args.bitstream_sha256,
        "loops": args.loops,
        "repeats": args.repeats,
        "policy": args.policy,
        "warmup": args.warmup,
        "sync": args.sync,
        "profile": args.profile,
        "working_set_kib": args.working_set_kib,
        "workload": args.workload,
        "terminal_handshake": int(not (args.legacy_four_arg_cli
                                       or args.legacy_no_terminal_handshake)),
        "legacy_four_arg_cli": args.legacy_four_arg_cli,
        "command": command,
    }
    if args.zlib_library is not None:
        status["zlib_library_sha256"] = sha256(args.zlib_library)
        status["zlib_transfer_encoding"] = "gzip-base64-v1"
    if args.retention_probe:
        status["retention_probe_capability"] = args.retention_probe
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
            if args.zlib_library is not None:
                for transfer_command in library_transfer(args.zlib_library):
                    child.sendline(transfer_command)
                    expect_shell_prompt(child, 180, "guest zlib transfer")
                child.sendline(f"/bin/busybox sha256sum {GUEST_ZLIB}")
                child.expect_exact(f"{status['zlib_library_sha256']}  {GUEST_ZLIB}")
                expect_shell_prompt(child, 180, "guest zlib verification")
            for transfer_command in args.transfer.read_text().splitlines():
                child.sendline(transfer_command)
                expect_shell_prompt(child, 180, "guest ELF transfer")
            child.sendline(f"/bin/busybox sha256sum {GUEST_ELF}")
            child.expect_exact(f"{args.elf_sha256}  {GUEST_ELF}")
            expect_shell_prompt(child, 300, "guest ELF verification")
            child.sendline(command)
            outcome = child.expect([
                re.compile(re.escape(pass_marker) + r"\r*\n"),
                re.compile(TIMER_GUARD_MARKER + r"[^\r\n]*"),
                KERNEL_FAILURE_MARKER,
                SHELL_PROMPT,
            ], timeout=1800)
            if outcome == 1:
                raise RuntimeError("timer callback integrity guard fired")
            if outcome == 2:
                raise RuntimeError("kernel failure marker: " + child.match.group(0))
            if outcome == 3:
                raise RuntimeError("guest returned to shell before " + pass_marker)
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
        for marker in (pass_marker, "BSG PASS"):
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
