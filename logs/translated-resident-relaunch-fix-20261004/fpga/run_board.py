#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pexpect

root = Path("/home/coyang/zynq-parrot")
evidence = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--requests", type=int, default=4096)
parser.add_argument("--samples", type=int, default=512)
parser.add_argument("--controller-timeout-ms", type=int, default=600000)
parser.add_argument("--output-tag", default="")
parser.add_argument("--binary", type=Path,
                    default=evidence / "failing-placement.elf")
parser.add_argument(
    "--expected-binary-sha256",
    default="90411570eaf29908cd5d94d1d6eac449f9fde0d36261234860f445cc2ffe22d8")
args = parser.parse_args()
if not 1 <= args.requests <= 1048576:
    parser.error("--requests must be in 1..1048576")
if not 1 <= args.samples <= 1000:
    parser.error("--samples must be in 1..1000")
if args.controller_timeout_ms < 1000:
    parser.error("--controller-timeout-ms must be at least 1000")
if args.output_tag and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.output_tag):
    parser.error("--output-tag must contain lowercase letters, digits, and hyphens")
suffix = f"-{args.output_tag}" if args.output_tag else ""
log_path = evidence / f"board{suffix}.log"
status_path = evidence / f"board-status{suffix}.json"
binary = args.binary.resolve()
expected = args.expected_binary_sha256.lower()
if not re.fullmatch(r"[0-9a-f]{64}", expected):
    parser.error("--expected-binary-sha256 must be a SHA-256 digest")
if hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
    raise RuntimeError("guest ELF identity mismatch")
linux_nbf = root / "linux-tests/out/linux-shell.nbf"
expected_nbf = "af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3"
if hashlib.sha256(linux_nbf.read_bytes()).hexdigest() != expected_nbf:
    raise RuntimeError("Linux NBF identity mismatch")
expected_bit_path = evidence / "expected-bit.sha256"
expected_bit = expected_bit_path.read_text().strip()
if not re.fullmatch(r"[0-9a-f]{64}", expected_bit):
    raise RuntimeError("invalid or missing expected bitstream SHA-256")
encoded = base64.b64encode(binary.read_bytes()).decode()
commands = ["rm -f /tmp/request_benchmark_dynamic.b64"]
commands.extend(
    f"echo '{encoded[i:i + 512]}' >> /tmp/request_benchmark_dynamic.b64"
    for i in range(0, len(encoded), 512))
commands.extend([
    "base64 -d /tmp/request_benchmark_dynamic.b64 > /tmp/request_benchmark_dynamic",
    "chmod +x /tmp/request_benchmark_dynamic",
])
status = {
    "status": "running", "stage": "boot", "binary_sha256": expected,
    "linux_nbf_sha256": expected_nbf, "bitstream_sha256": expected_bit,
    "requests_per_worker": args.requests, "samples": args.samples,
    "controller_timeout_ms": args.controller_timeout_ms,
    "recovery_required": True,
}
env = os.environ.copy()
env["PYNQ_CONTROL_PROGRAM_SHA256"] = \
    "be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e"
env["PYNQ_CONTROL_PROGRAM_TIMEOUT_MS"] = str(args.controller_timeout_ms)
child = None
exit_code = 0
try:
    status["stage"] = "overlay_load"
    load = subprocess.run(
        [str(root / "codex-skills/bp-fpga-synthesis/scripts/load_pynq_overlay.sh"),
         "xilinx@192.168.4.35"],
        check=True, text=True, capture_output=True)
    if f"LOADING_BIT_SHA256={expected_bit}\n" not in load.stdout:
        raise RuntimeError("loaded overlay SHA-256 does not match acceptance image")
    if "REMOTE_OVERLAY_LOAD_OK=1\n" not in load.stdout:
        raise RuntimeError("overlay loader did not report acceptance")
    status["stage"] = "boot"
    with log_path.open("w") as log:
        child = pexpect.spawn(
            str(root / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh"),
            ["xilinx@192.168.4.35", str(linux_nbf)], env=env,
            encoding="utf-8", timeout=600)
        child.logfile_read = log
        child.setwinsize(50, 210)
        child.delaybeforesend = 0.005
        child.expect_exact("Run /bin/sh as init process")
        child.expect(r"~ # ")
        status["stage"] = "transfer"
        for index, command in enumerate(commands):
            child.sendline(command)
            child.expect(r"~ # ", timeout=60)
            if index % 100 == 0:
                print(f"Transfer {index + 1}/{len(commands)} commands", flush=True)
        child.sendline("sha256sum /tmp/request_benchmark_dynamic")
        child.expect(expected + r"\s+/tmp/request_benchmark_dynamic[\r\n]")
        child.expect(r"~ # ")
        print(f"Guest ELF {binary.name} verified; executing "
              f"{args.samples} samples of {args.requests} requests/worker.",
              flush=True)
        status["stage"] = "measurement"
        child.sendline(
            "/tmp/request_benchmark_dynamic --workers 2 --hardware "
            f"--requests {args.requests} --samples {args.samples} "
            "--data-kib 2048 --mode-mask 4")
        outcome = child.expect([
            r"\[REQUEST-BENCH\] PASS[\r\n]",
            r"hardware context/completion verification failed[\r\n]",
            r"HARDWARE_VERIFY_FAIL[^\r\n]*[\r\n]",
            r"Segmentation fault[\r\n]",
            r"~ # ",
            pexpect.EOF,
        ], timeout=args.controller_timeout_ms / 1000 + 60)
        log.flush()
        text = log_path.read_text(errors="replace").replace("\r", "")
        rows = re.findall(
            r"^RESULT sample=(\d+) order=(\d+) mode=([^ ]+) ns=(\d+) "
            r"requests=(\d+) checksum=(\d+) cycles=(\d+)$", text, re.M)
        begins = re.findall(r"^SAMPLE_BEGIN sample=(\d+) ", text, re.M)
        warmup_begins = re.findall(r"^WARMUP_BEGIN mode=([^\n]+)$", text, re.M)
        warmup_passes = re.findall(r"^WARMUP_PASS mode=([^\n]+)$", text, re.M)
        status.update(
            result_rows=len(rows),
            last_complete_sample=int(rows[-1][0]) if rows else 0,
            last_started_sample=int(begins[-1]) if begins else 0,
            warmup_started=bool(warmup_begins),
            warmup_passed=bool(warmup_passes))
        if outcome != 0:
            observed = {
                1: "HARDWARE_VERIFY_FAIL",
                2: "HARDWARE_VERIFY_FAIL",
                3: "SEGMENTATION_FAULT",
                4: "UNEXPECTED_SHELL_RETURN",
                5: "UNEXPECTED_EOF",
            }[outcome]
            if "ps.cpp: target runtime limit reached" in text:
                observed = "CONTROLLER_TIMEOUT"
            status.update(
                status="MEASURED_FAILURE", stage="hardware_verification",
                observed_outcome=observed,
                controller_stopped_after_marker=True)
            exit_code = 1
            print(json.dumps(status, indent=2), flush=True)
        else:
            status["observed_outcome"] = "PASS"
            child.expect(r"~ # ", timeout=30)
            child.sendline("echo REQUEST_EXIT=$?")
            child.expect(r"REQUEST_EXIT=(\d+)[\r\n]")
            status["request_exit"] = int(child.match.group(1))
            child.expect(r"~ # ")
            status["stage"] = "poweroff"
            child.sendline("poweroff -f")
            child.expect_exact("CORE[0] PASS")
            child.expect(pexpect.EOF, timeout=120)
            child.close()
            if child.exitstatus != 0 or child.signalstatus is not None:
                raise RuntimeError(
                    f"runner exit={child.exitstatus} signal={child.signalstatus}")
            status.update(status="PASS", stage="complete", runner_exit=0,
                          core_pass=True, recovery_required=False)
            print(json.dumps(status, indent=2), flush=True)
except Exception as exc:
    status.update(status="FAIL", error=repr(exc))
    raise
finally:
    if child is not None and child.isalive():
        child.close(force=True)
    status_path.write_text(
        json.dumps(status, indent=2) + "\n")

if exit_code:
    raise SystemExit(exit_code)
