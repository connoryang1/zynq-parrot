#!/usr/bin/env python3
"""Run one fresh-boot persistent-thread Linux handoff batch on the PYNQ board."""

import os
import pathlib
import pexpect
import sys


if len(sys.argv) not in (6, 7):
    raise SystemExit(
        "usage: run_persistent_handoff.py NBF TRANSFER ELF_SHA LOG SAMPLES [summary|full]"
    )

repo = pathlib.Path(__file__).resolve().parents[2]
nbf, transfer_name, expected_elf_sha, log_name, sample_text = sys.argv[1:6]
samples = int(sample_text)
mode = sys.argv[6] if len(sys.argv) == 7 else "summary"
if samples < 2 or samples > 10000:
    raise SystemExit("SAMPLES must include one warmup and be in 2..10000")
if mode not in ("summary", "full"):
    raise SystemExit("mode must be summary or full")

runner = repo / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh"
env = os.environ.copy()
env["PYNQ_CONTROL_PROGRAM_SHA256"] = (
    "2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30"
)
child = pexpect.spawn(
    str(runner),
    ["xilinx@192.168.4.35", nbf],
    env=env,
    encoding="utf-8",
    timeout=240,
)
log_path = pathlib.Path(log_name)
transfer_path = pathlib.Path(transfer_name)
with log_path.open("w") as log:
    child.logfile = log
    child.expect_exact("~ # ")
    for line in transfer_path.read_text().splitlines():
        child.sendline(line)
        child.expect_exact("~ # ")
    child.sendline("sha256sum /tmp/cache_miss_trace_capture_dynamic")
    child.expect_exact(expected_elf_sha)
    child.expect_exact("~ # ")
    child.sendline("echo PERSISTENT_BEGIN")
    child.expect_exact("PERSISTENT_BEGIN")
    child.expect_exact("~ # ")
    summary_option = "--summary-only " if mode == "summary" else ""
    child.sendline(
        "/tmp/cache_miss_trace_capture_dynamic --window to-peer "
        f"{summary_option}--samples {samples} || true"
    )
    child.expect_exact("~ # ", timeout=600)
    child.sendline("echo PERSISTENT_END")
    child.expect_exact("PERSISTENT_END")
    child.expect_exact("~ # ")
    child.sendline("poweroff -f")
    child.expect(pexpect.EOF, timeout=120)
status = child.wait()
print(f"PERSISTENT_RUN_EXIT={status}")
sys.exit(status)
