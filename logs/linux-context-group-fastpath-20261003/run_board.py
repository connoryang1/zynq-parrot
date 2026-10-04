#!/usr/bin/env python3
import base64
import hashlib
import json
import os
from pathlib import Path

import pexpect

repo = Path("/home/coyang/zynq-parrot")
evidence = Path(__file__).resolve().parent
binary = evidence / "context_group_fastpath"
expected = hashlib.sha256(binary.read_bytes()).hexdigest()
payload = base64.b64encode(binary.read_bytes()).decode()
env = os.environ.copy()
env["PYNQ_CONTROL_PROGRAM_SHA256"] = \
    "be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e"
env["PYNQ_CONTROL_PROGRAM_TIMEOUT_MS"] = "600000"
status = {"status": "running"}

with (evidence / "board.log").open("w") as log:
    child = pexpect.spawn(
        str(repo / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh"),
        ["xilinx@192.168.4.35", str(repo / "linux-tests/out/linux-shell.nbf")],
        env=env, encoding="utf-8", timeout=600)
    child.logfile_read = log
    child.setwinsize(50, 180)
    try:
        child.expect("Run /bin/sh as init process")
        child.expect(r"~ # ")
        child.sendline(": > /tmp/context_group_fastpath.b64")
        child.expect(r"~ # ")
        for offset in range(0, len(payload), 768):
            chunk = payload[offset:offset + 768]
            child.sendline("echo '%s' >> /tmp/context_group_fastpath.b64" % chunk)
            child.expect(r"~ # ", timeout=30)
        child.sendline("base64 -d /tmp/context_group_fastpath.b64 > "
                       "/tmp/context_group_fastpath; "
                       "chmod 755 /tmp/context_group_fastpath")
        child.expect(r"~ # ", timeout=30)
        child.sendline("sha256sum /tmp/context_group_fastpath")
        child.expect(expected + r"\s+/tmp/context_group_fastpath")
        child.expect(r"~ # ")
        print("Guest ELF verified; executing persistent context group.", flush=True)
        child.sendline("/tmp/context_group_fastpath")
        outcome = child.expect_exact(
            ["[LINUX-CONTEXT-GROUP] PASS", "[LINUX-CONTEXT-GROUP] FAIL"],
            timeout=180)
        child.expect(r"~ # ")
        child.sendline("echo PROBE_EXIT=$?")
        child.expect(r"PROBE_EXIT=([0-9]+)[\r\n]")
        probe_exit = int(child.match.group(1))
        child.expect(r"~ # ")
        child.sendline("poweroff -f")
        child.expect_exact("CORE[0] PASS")
        child.expect(pexpect.EOF, timeout=90)
        child.close()
        if child.exitstatus != 0 or child.signalstatus is not None:
            raise RuntimeError("board runner failed")
        if outcome != 0 or probe_exit != 0:
            raise RuntimeError(
                f"probe failed: outcome={outcome} exit={probe_exit}")
        status = {
            "status": "PASS",
            "binary_sha256": expected,
            "runner_exit": 0,
            "checks": [
                "guest ELF SHA", "resident and nonresident probe PASS",
                "exit 0", "poweroff CORE PASS",
            ],
        }
        print("Persistent Linux context group PASS; guest powered off.",
              flush=True)
    except Exception as exc:
        status = {
            "status": "FAIL",
            "error": repr(exc),
            "recovery": "Power-cycle and reload the accepted overlay before retry.",
        }
        raise
    finally:
        (evidence / "board-status.json").write_text(
            json.dumps(status, indent=2) + "\n")
        if child.isalive():
            child.close(force=True)
