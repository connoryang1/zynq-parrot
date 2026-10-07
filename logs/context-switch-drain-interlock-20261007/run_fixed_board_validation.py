#!/usr/bin/env python3
"""Run the focused physical validation for the context-switch drain fix."""

from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import time


repo = Path(__file__).resolve().parents[2]
root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("bit_sha256")
args = parser.parse_args()
out = args.output.resolve()
assert out.is_dir() and re.fullmatch(r"[0-9a-f]{64}", args.bit_sha256)
assert not (out / "results.json").exists()
overlay = (out / "overlay.log").read_text()
assert "LOADING_BIT_SHA256=" + args.bit_sha256 in overlay
assert "REMOTE_FPGA_STATE=operating" in overlay

store_nbf = root / "board-collateral/mt_ctxtsw_store_handoff_benchmark_fpga.nbf"
k10_nbf = (repo / "logs/prefetch-mlatency-20260926/board-collateral/source/"
            "candidate-k3/dep-candidate-k3-k10-m3.nbf")
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert digest(store_nbf) == "98ac179bf4dfabf11533ed639dbad010b3d8703682b1ee088067f96b3f4a5ee9"
assert digest(k10_nbf) == "9c6e2df1ee6b33c19c4c03561a78684a8683d2d0692d160699945187e9e10e64"

runner = repo / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_serial.sh"
runner_sha = "2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30"
env = dict(os.environ, PYNQ_CONTROL_PROGRAM_FOREGROUND="1",
           PYNQ_CONTROL_PROGRAM_TIMEOUT_MS="15000",
           PYNQ_CONTROL_PROGRAM_SHA256=runner_sha)


def invoke(nbf, log):
    attempts = []
    command = [str(runner), "xilinx@192.168.4.35", str(nbf)]
    started = time.time()
    for attempt in range(5):
        run = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        attempts.append({"attempt": attempt, "exit_code": run.returncode,
                         "output": run.stdout})
        # Retry only a local socket refusal before the board runner starts.
        transient = (
            run.returncode != 0 and "RUNNER_STARTED_PID=" not in run.stdout and
            re.search(r"socket: Operation not permitted|connect to host .* failure",
                      run.stdout))
        if not transient:
            break
    log.write_text("".join(
        "ATTEMPT={} EXIT={}\n{}".format(
            item["attempt"], item["exit_code"], item["output"])
        for item in attempts))
    text = log.read_text(errors="replace")
    common = {
        "exit_code": run.returncode,
        "ssh_attempts": len(attempts),
        "nbf": str(nbf.relative_to(repo)),
        "nbf_sha256": digest(nbf),
        "log": log.name,
        "log_sha256": digest(log),
        "started": started,
        "completed": time.time(),
    }
    assert run.returncode == 0
    assert len(re.findall(r"^RUNNER_STARTED_PID=", text, re.M)) == 1
    assert re.search(r"^RUNNER_EXIT=0\s*$", text, re.M)
    assert re.search(r"\bCORE(?:\[0\])? PASS\b", text)
    assert re.search(r"\bBSG PASS\b", text)
    assert not re.search(
        r"BSG-FAIL|CORE(?:\[0\])? FAIL|Assertion .*failed|runtime limit|"
        r"unexpected trap|ERROR:", text, re.I)
    assert "CONTROL_PROGRAM_SHA256=" + runner_sha in text
    assert "nbf finish command" in text and "freeing DRAM buffer" in text
    return common, text


labels = {
    "resident_pure": "Resident pure cycles/switch x100",
    "resident_single": "Resident store cycles/switch x100",
    "resident_single_overhead": "Resident store overhead/switch x100",
    "resident_four": "Resident four-store cycles/switch x100",
    "resident_four_overhead": "Resident four-store overhead x100",
    "nonresident_pure": "Nonresident pure cycles/switch x100",
    "nonresident_single": "Nonresident store cycles/switch x100",
    "nonresident_single_overhead": "Nonresident store overhead/switch x100",
    "nonresident_four": "Nonresident four-store cycles/switch x100",
    "nonresident_four_overhead": "Nonresident four-store overhead x100",
}
store_rows = []
for rep in range(3):
    common, text = invoke(store_nbf, out / f"store-handoff-r{rep}.log")
    assert "[BSG-PASS] matched store-before-switch handoff benchmark" in text
    values = {}
    for key, label in labels.items():
        matches = re.findall(re.escape(label) + r":\s*(0x[0-9a-fA-F]+)", text)
        assert len(matches) == 1, (label, matches)
        values[key] = int(matches[0], 16) / 100
    store_rows.append(dict(common, rep=rep, **values))
    (out / "results.json").write_text(json.dumps({
        "bit_sha256": args.bit_sha256,
        "control_program_sha256": runner_sha,
        "store_handoff_runs": store_rows,
        "k10_zero_nop_runs": [],
    }, indent=2) + "\n")

k10_rows = []
for rep in range(3):
    common, text = invoke(k10_nbf, out / f"k10-zero-nop-r{rep}.log")
    assert "[BSG-PASS] dependent streams, checksums and completion" in text
    matches = re.findall(
        r"Benchmark: DEPENDENT mode=(0x[0-9a-fA-F]+) "
        r"streams=(0x[0-9a-fA-F]+) nodes=(0x[0-9a-fA-F]+) "
        r"cycles=(0x[0-9a-fA-F]+)", text)
    assert matches and len(set(matches)) == 1, matches
    mode, streams, nodes, cycles = map(lambda value: int(value, 16), matches[0])
    assert (mode, streams, nodes) == (3, 10, 1280)
    k10_rows.append(dict(common, rep=rep, mode=mode, streams=streams,
                         nodes=nodes, cycles=cycles,
                         cycles_per_node=cycles / nodes))
    (out / "results.json").write_text(json.dumps({
        "bit_sha256": args.bit_sha256,
        "control_program_sha256": runner_sha,
        "store_handoff_runs": store_rows,
        "k10_zero_nop_runs": k10_rows,
    }, indent=2) + "\n")

assert all(row["resident_pure"] == store_rows[0]["resident_pure"] and
           row["resident_single"] == store_rows[0]["resident_single"] and
           row["resident_four"] == store_rows[0]["resident_four"] and
           row["nonresident_pure"] == store_rows[0]["nonresident_pure"] and
           row["nonresident_single"] == store_rows[0]["nonresident_single"] and
           row["nonresident_four"] == store_rows[0]["nonresident_four"]
           for row in store_rows)
print(json.dumps({
    "bit_sha256": args.bit_sha256,
    "store_handoff_cycle_row": {
        key: store_rows[0][key] for key in labels
    },
    "k10_zero_nop_cycles": [row["cycles"] for row in k10_rows],
    "all_six_runs_valid": True,
}, indent=2))
