#!/usr/bin/env python3
"""Run the hash-pinned bubble placement matrix with a fresh overlay per run."""

from pathlib import Path
import argparse
import base64
import datetime
import hashlib
import json
import re
import shlex
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[4]
SSH_HOST = "xilinx@192.168.4.35"
REMOTE_DIR = "/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq"
CONTROL_PROGRAM_SHA256 = "2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30"
INTERACTIVE_HELPER_SHA256 = "744f2bd7f547fe757df462a45101129b7e4df8c36461f42f75e7b50b72355191"
BITSTREAM_SHA256 = "9d6c4eb5e90f85ddc225c08d6fd930b1e405cf45cd15ae59e17c1356e052c29b"
RUNTIME_MS = 30000


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


IMAGES = {
    "original-k10": (
        HERE.parent / "context4-sim-120-124/steps124/only4-steps124.nbf",
        "cfa9ededb6cc73c65acb0d7b5cc61100031e08908237db5af0c9c44f912cc7df",
    ),
    "branch-control-k10": (
        HERE / "exact-branch-encoding-control.nbf",
        "0eead35c3cc5476d021796701fd6f09fca8b3df5f5fbeebe367808d1dda4ce65",
    ),
    "post-switch-k10": (
        HERE / "exact-inplace-bubble-n1.nbf",
        "da075999c56bd29d82b8a0bd50dcb7dc55b8315a2676bc3cee94087cf4502e55",
    ),
    "pre-switch-k10": (
        HERE / "exact-preswitch-bubble-n1.nbf",
        "1903ba3a932910915ab66dc16872d525e9c1a35c84ac04346753c929c82b13d3",
    ),
    "body-k10": (
        HERE / "exact-body-bubble-n1.nbf",
        "0f08524e1da95aec53da57d8976d5ed101ed65a042d2a188a594dd24ed1e1afd",
    ),
    "original-k2": (
        HERE / "fast-k2-control/original-k2.nbf",
        "92b0bdbe635486053a23ca9fc86074678a8f28b11e07626d43a23a11af6a5b0c",
    ),
    "branch-control-k2": (
        HERE / "fast-k2-control/branch-encoding-control-k2.nbf",
        "b0d538e5e2c805b6eabd42ad2b9333d5c73bace1f8371aba9962f081071af02e",
    ),
    "post-switch-k2": (
        HERE / "fast-k2-control/post-switch-n1-k2.nbf",
        "94ca62c38298d13538c4109a4c2cd2039c8aa9acaa553328b8758dc8a3939f89",
    ),
}

# Alternation checks that a passing bubble does not merely leave favorable
# board state. The final three runs measure physical fast-path cost.
MATRIX = [
    "original-k10", "branch-control-k10", "post-switch-k10",
    "original-k10", "pre-switch-k10", "body-k10", "post-switch-k10",
    "original-k2", "branch-control-k2", "post-switch-k2",
]


def run(command, *, input_text=None):
    return subprocess.run(command, input=input_text, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def ssh(remote_command, *, input_text=None, tty=False):
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
    if tty:
        command.append("-tt")
    command += [SSH_HOST, remote_command]
    return run(command, input_text=input_text)


def upload(path, expected):
    name = path.name
    assert re.fullmatch(r"[A-Za-z0-9._-]+\.nbf", name)
    incoming = "." + name + ".incoming"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    command = (
        f"cd {shlex.quote(REMOTE_DIR)} && "
        f"base64 -d > {shlex.quote(incoming)} && "
        f"test \"$(sha256sum {shlex.quote(incoming)} | awk '{{print $1}}')\" = {shlex.quote(expected)} && "
        f"mv -f {shlex.quote(incoming)} {shlex.quote(name)} && "
        f"sha256sum {shlex.quote(name)}"
    )
    result = ssh(command, input_text=encoded)
    if result.returncode or expected not in result.stdout:
        raise RuntimeError(f"upload failed for {name}:\n{result.stdout}")


def classify(text, returncode):
    if re.search(r"BSG-FAIL|\bBSG FAIL\b|CORE(?:\[0\])? FAIL", text, re.I):
        return "fail"
    if returncode == 124 or re.search(r"runtime limit|timed out|timeout", text, re.I):
        return "timeout"
    # The control program prints BSG PASS when it exits cleanly even if the
    # guest reported CORE FAIL. Require both guest and host success, and only
    # evaluate this after all guest failure markers above.
    if (re.search(r"CORE(?:\[\d+\])?\s+PASS", text)
            and re.search(r"\bBSG PASS\b", text)):
        return "pass"
    return "unknown"


def self_test_classify():
    cases = (
        ("INFO: CORE FAIL\nINFO: BSG PASS\n", 0, "fail"),
        ("[BSG-PASS] workload\nINFO: CORE PASS\nINFO: BSG PASS\n", 0, "pass"),
        ("INFO: BSG PASS\n", 0, "unknown"),
        ("INFO: target runtime limit reached\n", 124, "timeout"),
    )
    for text, returncode, expected in cases:
        actual = classify(text, returncode)
        if actual != expected:
            raise AssertionError(f"classify returned {actual}, expected {expected}: {text!r}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test_classify()
        print("classification self-test passed")
        return

    local = {}
    for label, (path, expected) in IMAGES.items():
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(f"SHA mismatch for {label}: {actual} != {expected}")
        local[label] = {"path": str(path.relative_to(REPO)), "sha256": actual,
                        "remote_name": path.name}

    plan = {
        "ssh_host": SSH_HOST,
        "remote_directory": REMOTE_DIR,
        "bitstream_sha256": BITSTREAM_SHA256,
        "control_program_sha256": CONTROL_PROGRAM_SHA256,
        "interactive_helper_sha256": INTERACTIVE_HELPER_SHA256,
        "runtime_ms": RUNTIME_MS,
        "fresh_overlay_before_every_run": True,
        "images": local,
        "matrix": MATRIX,
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return
    if args.output is None:
        parser.error("output is required unless --dry-run is used")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")

    helper = ssh(f"sha256sum {shlex.quote(REMOTE_DIR + '/run-blackparrot-interactive')}")
    if helper.returncode or not helper.stdout.startswith(INTERACTIVE_HELPER_SHA256 + " "):
        raise RuntimeError("interactive helper SHA mismatch:\n" + helper.stdout)
    unique_images = {str(path): (path, expected)
                     for path, expected in IMAGES.values()}
    for path, expected in unique_images.values():
        upload(path, expected)

    load_overlay = REPO / "codex-skills/bp-fpga-synthesis/scripts/load_pynq_overlay.sh"
    results = []
    for index, label in enumerate(MATRIX):
        path, expected = IMAGES[label]
        stem = f"{index:02d}-{label}"
        overlay = run([str(load_overlay), SSH_HOST])
        (out / f"{stem}-overlay.log").write_text(overlay.stdout)
        if (overlay.returncode or "REMOTE_FPGA_STATE=operating" not in overlay.stdout
                or "LOADING_BIT_SHA256=" + BITSTREAM_SHA256 not in overlay.stdout):
            raise RuntimeError(f"overlay load failed for {stem}:\n{overlay.stdout}")

        command = (
            f"{shlex.quote(REMOTE_DIR + '/run-blackparrot-interactive')} "
            f"{shlex.quote(path.name)} {expected} {CONTROL_PROGRAM_SHA256} {RUNTIME_MS}"
        )
        started = time.time()
        target = ssh(command, tty=True)
        completed = time.time()
        log = out / f"{stem}.log"
        log.write_text(target.stdout)
        row = {
            "index": index, "label": label, "nbf": local[label],
            "returncode": target.returncode,
            "classification": classify(target.stdout, target.returncode),
            "started_unix": started, "completed_unix": completed,
            "elapsed_seconds": completed - started,
            "overlay_log": f"{stem}-overlay.log", "target_log": log.name,
            "target_log_sha256": sha256(log),
        }
        results.append(row)
        (out / "results.json").write_text(json.dumps({"plan": plan, "runs": results}, indent=2) + "\n")
        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
