#!/usr/bin/env python3
import hashlib
import json
import os
import re
from pathlib import Path

import pexpect

root = Path("/home/coyang/zynq-parrot")
evidence = Path(__file__).resolve().parent
binary = evidence / "request_benchmark_dynamic"
expected = "8d95f0cfbf91686836ab72b2fe3029bdee1f338a2658774ca1034debf5b1d643"
if hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
    raise RuntimeError("guest ELF identity mismatch")
linux_nbf = root / "linux-tests/out/linux-shell.nbf"
expected_nbf = "af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3"
if hashlib.sha256(linux_nbf.read_bytes()).hexdigest() != expected_nbf:
    raise RuntimeError("Linux NBF identity mismatch")
commands = (evidence / "transfer.txt").read_text().splitlines()
status = {
    "status": "running", "stage": "boot", "binary_sha256": expected,
    "linux_nbf_sha256": expected_nbf, "recovery_required": True,
}
env = os.environ.copy()
env["PYNQ_CONTROL_PROGRAM_SHA256"] = \
    "be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e"
env["PYNQ_CONTROL_PROGRAM_TIMEOUT_MS"] = "600000"
child = None
try:
    with (evidence / "board.log").open("w") as log:
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
        print("Exact guest ELF verified; executing repeat.", flush=True)
        status["stage"] = "measurement"
        child.sendline(
            "/tmp/request_benchmark_dynamic --workers 2 --hardware "
            "--requests 4096 --samples 64 --data-kib 2048 --mode-mask 4")
        outcome = child.expect([
            r"\[REQUEST-BENCH\] PASS[\r\n]",
            r"hardware context/completion verification failed[\r\n]",
        ], timeout=600)
        log.flush()
        text = (evidence / "board.log").read_text(errors="replace").replace("\r", "")
        rows = re.findall(
            r"^RESULT sample=(\d+) order=(\d+) mode=([^ ]+) ns=(\d+) "
            r"requests=(\d+) checksum=(\d+) cycles=(\d+)$", text, re.M)
        begins = re.findall(r"^SAMPLE_BEGIN sample=(\d+) ", text, re.M)
        status.update(
            result_rows=len(rows),
            last_complete_sample=int(rows[-1][0]) if rows else 0,
            last_started_sample=int(begins[-1]) if begins else 0)
        if outcome == 1:
            status.update(
                status="MEASURED_FAILURE", stage="hardware_verification",
                observed_outcome="HARDWARE_VERIFY_FAIL",
                controller_stopped_after_marker=True)
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
    (evidence / "board-status.json").write_text(
        json.dumps(status, indent=2) + "\n")
