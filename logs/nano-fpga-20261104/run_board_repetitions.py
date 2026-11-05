"""Collect three reset-separated samples for every Nano N=8 FPGA mode."""

from pathlib import Path
import json
import os
import re
import statistics
import subprocess


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUNNER = ROOT / "codex-skills/bp-fpga-synthesis/scripts/run_pynq_serial.sh"
HOST = "xilinx@192.168.4.35"
RUNNER_SHA256 = "2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30"
NAMES = [
    "serial demand", "demand ring", "worker prefetch", "matched batch",
    "switch-only", "serial prefetch", "C++20 coroutines",
    "fixed unrolled SoA batch", "fixed unrolled recompute batch",
    "lean queue C++20 coroutines", "direct C++20 coroutines",
]
ROW = re.compile(
    r"Benchmark: NANO_LOOKUP mode=(?:0x)?([0-9a-fA-F]+) "
    r"queries=(?:0x)?([0-9a-fA-F]+) levels=(?:0x)?([0-9a-fA-F]+) "
    r"cycles=(?:0x)?([0-9a-fA-F]+) checksum=(?:0x)?([0-9a-fA-F]+)"
)
ENV = {
    **os.environ,
    "PYNQ_CONTROL_PROGRAM_SHA256": RUNNER_SHA256,
    "PYNQ_CONTROL_PROGRAM_FOREGROUND": "1",
}


samples = []
base_order = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
for repetition in range(3):
    order = base_order if repetition != 1 else list(reversed(base_order))
    for mode in order:
        image = OUT / f"nano-mode{mode}-n8.nbf"
        result = subprocess.run(
            [str(RUNNER), HOST, str(image)], cwd=ROOT, env=ENV,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        transcript = result.stdout
        log_name = f"mode{mode}-n8-board-r{repetition}.log"
        (OUT / log_name).write_text(transcript)
        match = ROW.search(transcript)
        if result.returncode or not match:
            raise SystemExit(
                f"mode {mode} repetition {repetition} failed rc={result.returncode}"
            )
        observed = [int(value, 16) for value in match.groups()]
        required = [
            f"Mode: {NAMES[mode]}; checks: pass",
            "[BSG-PASS] Nano-style binary index lookups",
            "INFO:    CORE PASS", "INFO:    BSG PASS", "RUNNER_EXIT=0",
        ]
        if observed[:3] != [mode, 8, 11] or any(
                marker not in transcript for marker in required):
            raise SystemExit(f"mode {mode} repetition {repetition} validation failed")
        samples.append({
            "mode": mode, "name": NAMES[mode], "repetition": repetition,
            "cycles": observed[3], "checksum": observed[4], "log": log_name,
        })
        print(f"r={repetition} mode={mode} cycles={observed[3]}", flush=True)

summaries = []
for mode, name in enumerate(NAMES):
    values = [row["cycles"] for row in samples if row["mode"] == mode]
    summaries.append({
        "mode": mode, "name": name, "samples": values,
        "median_cycles": statistics.median(values),
        "min_cycles": min(values), "max_cycles": max(values),
        "median_cycles_per_node": statistics.median(values) / 88,
    })

(OUT / "board-samples.json").write_text(json.dumps(samples, indent=2) + "\n")
(OUT / "board-results.json").write_text(json.dumps(summaries, indent=2) + "\n")
print("BOARD_REPETITIONS_PASS=1", flush=True)
