#!/usr/bin/env python3
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import statistics
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
assert not (out / "matrix-results.json").exists()
overlay = (out / "overlay.log").read_text()
assert "LOADING_BIT_SHA256=" + args.bit_sha256 in overlay
assert "REMOTE_FPGA_STATE=operating" in overlay

source = repo / "logs/prefetch-mlatency-20260926/board-collateral/source/candidate-k3"
manifest = json.loads((source / "manifest.json").read_text())
sector = root / "sector-diagnostic/mt_ddr_latency_benchmark_fpga.nbf"
sector_manifest = json.loads((root / "sector-diagnostic/manifest.json").read_text())
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
for name, expected in manifest["sha256"].items():
    assert digest(source / name) == expected, name
assert digest(sector) == sector_manifest["sha256"][sector.name]

runner = repo / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_serial.sh"
env = dict(os.environ, PYNQ_CONTROL_PROGRAM_FOREGROUND="1",
           PYNQ_CONTROL_PROGRAM_TIMEOUT_MS="15000",
           PYNQ_CONTROL_PROGRAM_SHA256=
           "2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30")


def invoke(nbf, log):
    started = time.time()
    with log.open("w") as stream:
        run = subprocess.run([str(runner), "xilinx@192.168.4.35", str(nbf)],
                             env=env, stdout=stream, stderr=subprocess.STDOUT)
    text = log.read_text(errors="replace")
    common = {
        "exit_code": run.returncode,
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
    assert "CONTROL_PROGRAM_SHA256=" + env["PYNQ_CONTROL_PROGRAM_SHA256"] in text
    assert "nbf finish command" in text and "freeing DRAM buffer" in text
    return common, text


sector_rows = []


def run_sector_phase(phase):
    for rep in range(3):
        log = out / f"sector-{phase}-r{rep}.log"
        common, text = invoke(sector, log)
        assert "[BSG-PASS] DDR dependent-load latency and prefetch lead sweep" in text
        match = re.search(
            r"DDR_SECTOR_SUMMARY samples=(0x[0-9a-fA-F]+) "
            r"first_min=(0x[0-9a-fA-F]+) first_max=(0x[0-9a-fA-F]+) "
            r"adjacent_min=(0x[0-9a-fA-F]+) adjacent_max=(0x[0-9a-fA-F]+)", text)
        assert match
        values = list(map(lambda value: int(value, 16), match.groups()))
        assert values[0] == 16
        # A side-buffer hit is normally 3 cycles; leave a small measurement
        # margin while failing far below the measured 42-cycle DDR fallback.
        assert values[2] <= 8 and values[4] <= 8, values
        row = dict(common, phase=phase, rep=rep, samples=values[0],
                   first_min=values[1], first_max=values[2],
                   adjacent_min=values[3], adjacent_max=values[4])
        sector_rows.append(row)
        (out / "sector-results.json").write_text(
            json.dumps(sector_rows, indent=2) + "\n")


run_sector_phase("before")

gate = (10, 3)
base = [(streams, mode) for streams in (2, 3, 4, 10) for mode in range(4)
        if (streams, mode) != gate]
orders = [base, list(reversed(base)), base[8:] + base[:8]]
plan = [(rep, streams, mode) for rep, order in enumerate(orders)
        for streams, mode in order]
# The prior five-slot image fails this cell before printing a benchmark result.
# Preserve three repetitions of every independent comparison before enforcing
# the corrected image's mandatory ten-stream hardware correctness gate.
plan.extend((rep, *gate) for rep in range(3))
rows = []
for index, (rep, streams, mode) in enumerate(plan):
    nbf = source / f"dep-candidate-k3-k{streams}-m{mode}.nbf"
    log = out / f"matrix-{index:02d}-r{rep}-k{streams}-m{mode}.log"
    common, text = invoke(nbf, log)
    assert "[BSG-PASS] dependent streams, checksums and completion" in text
    matches = re.findall(
        r"Benchmark: DEPENDENT mode=(0x[0-9a-fA-F]+) "
        r"streams=(0x[0-9a-fA-F]+) nodes=(0x[0-9a-fA-F]+) "
        r"cycles=(0x[0-9a-fA-F]+)", text)
    assert matches and len(set(matches)) == 1, matches
    got_mode, got_streams, nodes, cycles = map(
        lambda value: int(value, 16), matches[0])
    expected_nodes = 1278 if streams == 3 else 1280
    assert (got_mode, got_streams, nodes) == (mode, streams, expected_nodes)
    row = dict(common, index=index, rep=rep, mode=mode, streams=streams,
               nodes=nodes, cycles=cycles, cycles_per_node=cycles / nodes,
               transcript_copies=len(matches))
    rows.append(row)
    (out / "matrix-results.json").write_text(json.dumps(rows, indent=2) + "\n")

run_sector_phase("after")

medians = {}
for streams in (2, 3, 4, 10):
    medians[str(streams)] = {}
    for mode in range(4):
        samples = [row["cycles"] for row in rows
                   if row["streams"] == streams and row["mode"] == mode]
        assert len(samples) == 3
        medians[str(streams)][str(mode)] = {
            "samples": samples,
            "median": statistics.median(samples),
        }
    demand = medians[str(streams)]["0"]["median"]
    medians[str(streams)]["software_speedup"] = (
        demand / medians[str(streams)]["2"]["median"])
    medians[str(streams)]["hardware_speedup"] = (
        demand / medians[str(streams)]["3"]["median"])

# Compare against the accepted fast image and the three-repetition buggy
# five-slot medians. The focused physical probe measures a 39-cycle
# adjacent-word penalty, so this predicts the portion of each prefetch-mode
# total that the RTL fix alone should recover. These are interpretation fields,
# not pass thresholds.
fast = {
    2: {0: 60071, 1: 30821, 2: 14167, 3: 18621},
    3: {0: 59997, 1: 30790, 2: 9525, 3: 21825},
    4: {0: 60053, 1: 30891, 2: 8413, 3: 22298},
    10: {0: 60345, 1: 31005, 2: 8077, 3: 23820},
}
buggy = {
    2: {0: 60083, 1: 82608, 2: 62244, 3: 69893},
    3: {0: 60025, 1: 82488, 2: 60943, 3: 73137},
    4: {0: 60060, 1: 82510, 2: 60678, 3: 74377},
    10: {0: 60375, 1: 82411, 2: 62851, 3: None},
}
recovery = {}
for streams in (2, 3, 4, 10):
    nodes = 1278 if streams == 3 else 1280
    expected_recovery = 39 * nodes
    recovery[str(streams)] = {}
    for mode in range(4):
        observed = medians[str(streams)][str(mode)]["median"]
        broken = buggy[streams][mode]
        row = {
            "accepted_fast_cycles": fast[streams][mode],
            "buggy_five_slot_median_cycles": broken,
            "corrected_median_cycles": observed,
            "corrected_minus_accepted_fast": observed - fast[streams][mode],
        }
        if mode != 0 and broken is not None:
            recovered = broken - observed
            row.update({
                "measured_penalty_prediction": expected_recovery,
                "buggy_minus_measured_penalty": broken - expected_recovery,
                "actual_recovered_cycles": recovered,
                "actual_over_predicted_recovery": recovered / expected_recovery,
            })
        recovery[str(streams)][str(mode)] = row

analysis = {
    "bit_sha256": args.bit_sha256,
    "sector": sector_rows,
    "sector_hot_before_and_after": all(
        row["first_max"] <= 8 and row["adjacent_max"] <= 8
        for row in sector_rows),
    "matrix_runs": len(rows),
    "all_runs_valid": True,
    "medians": medians,
    "adjacent_penalty_recovery": recovery,
}
(out / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n")
print(json.dumps(analysis, indent=2))
