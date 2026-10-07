#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import re
import statistics
import subprocess
import time

repo = Path(__file__).resolve().parents[2]
root = Path(__file__).resolve().parent
out = root / "buggy-five-slot-matrix"
out.mkdir(exist_ok=False)
source = repo / "logs/prefetch-mlatency-20260926/board-collateral/source/candidate-k3"
manifest = json.loads((source / "manifest.json").read_text())
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
for name, expected in manifest["sha256"].items():
    assert digest(source / name) == expected, name

host = "xilinx@192.168.4.35"
remote = "/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq"
bit_sha256 = "933777e636853c0a6e9c6cb6d068778b4a49209510d16e49226c63bcbb6793ea"
runner_sha256 = "2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30"

preflight = subprocess.check_output([
    "ssh", "-o", "BatchMode=yes", host,
    "cd {} && cat /sys/class/fpga_manager/fpga0/state && "
    "sha256sum blackparrot_bd_1.bit control-program".format(remote)], text=True)
assert preflight.splitlines()[0] == "operating", preflight
assert bit_sha256 in preflight and runner_sha256 in preflight, preflight
(out / "preflight.log").write_text(preflight)


def invoke(nbf, log):
    command = ["ssh", "-o", "BatchMode=yes", host,
               "cd {} && sudo -n ./control-program {} 15000".format(
                   remote, nbf.name)]
    attempts = []
    for attempt in range(5):
        started = time.time()
        run = subprocess.run(command, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        attempts.append({"attempt": attempt, "exit_code": run.returncode,
                         "started": started, "completed": time.time(),
                         "output": run.stdout})
        transient = (run.returncode == 255 and
                     re.search(r"socket: Operation not permitted|connect to host .* failure",
                               run.stdout))
        if not transient:
            break
    log.write_text("".join(
        "ATTEMPT={} EXIT={}\n{}".format(a["attempt"], a["exit_code"], a["output"])
        for a in attempts))
    return attempts[-1], digest(log), len(attempts)


base = [(streams, mode) for streams in (2, 3, 4) for mode in range(4)]
base += [(10, mode) for mode in range(3)]
orders = [base, list(reversed(base)), base[7:] + base[:7]]
plan = [(rep, streams, mode) for rep, order in enumerate(orders)
        for streams, mode in order]
rows = []
for index, (rep, streams, mode) in enumerate(plan):
    nbf = source / f"dep-candidate-k3-k{streams}-m{mode}.nbf"
    log = out / f"matrix-{index:02d}-r{rep}-k{streams}-m{mode}.log"
    result, log_sha, attempts = invoke(nbf, log)
    text = result["output"]
    matches = re.findall(
        r"Benchmark: DEPENDENT mode=(0x[0-9a-fA-F]+) "
        r"streams=(0x[0-9a-fA-F]+) nodes=(0x[0-9a-fA-F]+) "
        r"cycles=(0x[0-9a-fA-F]+)", text)
    expected_nodes = 1278 if streams == 3 else 1280
    valid = (result["exit_code"] == 0 and
             "[BSG-PASS] dependent streams, checksums and completion" in text and
             re.search(r"\bCORE(?:\[0\])? PASS\b", text) is not None and
             re.search(r"\bBSG PASS\b", text) is not None and
             not re.search(r"BSG-FAIL|CORE(?:\[0\])? FAIL|runtime limit|unexpected trap",
                           text, re.I) and matches and len(set(matches)) == 1)
    if valid:
        got_mode, got_streams, nodes, cycles = map(
            lambda value: int(value, 16), matches[0])
        valid = (got_mode, got_streams, nodes) == (mode, streams, expected_nodes)
    row = {"index": index, "rep": rep, "streams": streams, "mode": mode,
           "nodes": expected_nodes, "valid": bool(valid),
           "exit_code": result["exit_code"], "ssh_attempts": attempts,
           "nbf": str(nbf.relative_to(repo)), "nbf_sha256": digest(nbf),
           "log": log.name, "log_sha256": log_sha,
           "bit_sha256": bit_sha256, "control_program_sha256": runner_sha256}
    if valid:
        row.update(cycles=cycles, cycles_per_node=cycles / nodes)
    rows.append(row)
    (out / "matrix-results.json").write_text(json.dumps(rows, indent=2) + "\n")
    assert valid, row

# The earlier exact-overlay runs failed here. Keep this separate from the
# accepted matrix so either a pass or a reproduced target failure is evidence.
nbf = source / "dep-candidate-k3-k10-m3.nbf"
gate_log = out / "k10-m3-gate.log"
gate, gate_sha, gate_attempts = invoke(nbf, gate_log)
gate_text = gate["output"]
gate_record = {
    "streams": 10, "mode": 3, "exit_code": gate["exit_code"],
    "ssh_attempts": gate_attempts, "log": gate_log.name,
    "log_sha256": gate_sha, "nbf_sha256": digest(nbf),
    "core_pass": re.search(r"\bCORE(?:\[0\])? PASS\b", gate_text) is not None,
    "core_fail": re.search(r"\bCORE(?:\[0\])? FAIL\b", gate_text) is not None,
    "host_pass": re.search(r"\bBSG PASS\b", gate_text) is not None,
}
(out / "k10-m3-gate.json").write_text(json.dumps(gate_record, indent=2) + "\n")

medians = {}
for streams in (2, 3, 4, 10):
    medians[str(streams)] = {}
    modes = range(3) if streams == 10 else range(4)
    for mode in modes:
        samples = [row["cycles"] for row in rows
                   if row["streams"] == streams and row["mode"] == mode]
        assert len(samples) == 3
        medians[str(streams)][str(mode)] = {
            "samples": samples, "median": statistics.median(samples),
            "min": min(samples), "max": max(samples),
        }
(out / "analysis.json").write_text(json.dumps({
    "bit_sha256": bit_sha256,
    "accepted_runs": len(rows),
    "all_accepted_runs_valid": all(row["valid"] for row in rows),
    "medians": medians,
    "k10_hardware_gate": gate_record,
}, indent=2) + "\n")
