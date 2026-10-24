#!/usr/bin/env python3
"""Run the Linux oracle preview with a hash-checked interactive board session."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pexpect

experiment = Path("/tmp/zp-context-resume-prefetch-lane")
canonical = Path("/home/coyang/zynq-parrot")
evidence = Path(__file__).resolve().parent
binary = experiment / "linux-tests/out/context_preview_oracle_dynamic"
transfer = experiment / "linux-tests/out/context_preview_oracle_dynamic.transfer"
linux_nbf = canonical / "linux-tests/out/linux-shell-timer8-memory46-nodebug.nbf"
expected_nbf = "892b19f7a9d697bfc84adc2853e2fe9165a92ced7305a4971d2bb7577c8b1438"
expected_runner = "2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30"
expected_bit = "f234819855ee79028ccf6387a356fe297962b9e30e36420f4da224150384a7b8"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if sha(linux_nbf) != expected_nbf:
    raise RuntimeError("Linux NBF identity mismatch")
remote_bit = subprocess.check_output([
    "ssh", "-o", "BatchMode=yes", "xilinx@192.168.4.35",
    "sha256sum ~/zynq-parrot/cosim/black-parrot-example/zynq/blackparrot_bd_1.bit",
], text=True).split()[0]
if remote_bit != expected_bit:
    raise RuntimeError("board bitstream identity mismatch")
expected_binary = sha(binary)
commands = transfer.read_text().splitlines()
status = {
    "status": "running", "stage": "boot", "binary_sha256": expected_binary,
    "linux_nbf_sha256": expected_nbf, "bit_sha256": expected_bit,
    "runner_sha256": expected_runner, "recovery_required": True,
}
env = os.environ.copy()
env["PYNQ_CONTROL_PROGRAM_SHA256"] = expected_runner
env["PYNQ_CONTROL_PROGRAM_TIMEOUT_MS"] = "900000"
child = None
try:
    with (evidence / "board.log").open("w") as log:
        child = pexpect.spawn(
            str(canonical / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh"),
            ["xilinx@192.168.4.35", str(linux_nbf)], env=env,
            encoding="utf-8", timeout=600,
        )
        child.logfile_read = log
        child.setwinsize(50, 180)
        child.delaybeforesend = 0.005
        child.expect_exact("Run /bin/sh as init process")
        child.expect(r"~ # ")
        status["stage"] = "transfer"
        for index, command in enumerate(commands):
            child.sendline(command)
            child.expect(r"~ # ", timeout=60)
            if index % 100 == 0:
                print(f"Transfer {index + 1}/{len(commands)} commands", flush=True)
        child.sendline("sha256sum /tmp/context_preview_oracle_dynamic")
        child.expect(expected_binary + r"\s+/tmp/context_preview_oracle_dynamic[\r\n]")
        child.expect(r"~ # ")
        status["stage"] = "measurement"
        child.sendline("/tmp/context_preview_oracle_dynamic")
        child.expect(r"CONTEXT_PREVIEW PASS[\r\n]", timeout=600)
        output = child.before + child.after
        clean = output.replace("\r", "")
        (evidence / "benchmark.stdout.txt").write_text(clean)
        rows = re.findall(
            r"^CONTEXT_PREVIEW mode=(\d+) repeat=(\d+) total=(\d+) "
            r"preview=(\d+) work=(\d+) wake=(\d+) peer_entry=(\d+) "
            r"peer_load=(\d+) cpu=(\d+)$", clean, re.M,
        )
        if len(rows) != 32:
            raise RuntimeError(f"expected 32 result rows, got {len(rows)}")
        seen = {(int(mode), int(repeat)) for mode, repeat, *_ in rows}
        if seen != {(mode, repeat) for mode in range(4) for repeat in range(8)}:
            raise RuntimeError("mode/repetition coverage mismatch")
        if len({cpu for *_, cpu in rows}) != 1:
            raise RuntimeError("CPU affinity changed")
        child.expect(r"~ # ")
        child.sendline("echo CONTEXT_PREVIEW_EXIT=$?")
        child.expect(r"CONTEXT_PREVIEW_EXIT=0[\r\n]")
        child.expect(r"~ # ")
        status.update(stage="poweroff", result_rows=32, application_exit=0)
        child.sendline("poweroff -f")
        child.expect(r"CORE(?:\[0\])? PASS")
        child.expect(pexpect.EOF, timeout=120)
        child.close()
        if child.exitstatus != 0 or child.signalstatus is not None:
            raise RuntimeError(f"runner exit={child.exitstatus} signal={child.signalstatus}")
        status.update(status="PASS", stage="complete", runner_exit=0,
                      core_pass=True, recovery_required=False)
        print("Linux context preview oracle PASS", flush=True)
except Exception as exc:
    status.update(status="FAIL", error=repr(exc))
    raise
finally:
    if child is not None and child.isalive():
        child.close(force=True)
    (evidence / "board-status.json").write_text(json.dumps(status, indent=2) + "\n")
