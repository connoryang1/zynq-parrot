"""Summarize every retained successful Nano FPGA transcript without selection."""

from pathlib import Path
import hashlib
import json
import re
import statistics


OUT = Path(__file__).resolve().parent
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


samples = []
for mode, name in enumerate(NAMES):
    logs = [OUT / f"mode{mode}-n8-board.log"]
    logs.extend(sorted(OUT.glob(f"mode{mode}-n8-board-r*.log")))
    for log in logs:
        text = log.read_text()
        match = ROW.search(text)
        if not match or "RUNNER_EXIT=0" not in text or "INFO:    CORE PASS" not in text:
            raise SystemExit(f"invalid retained transcript: {log.name}")
        observed = [int(value, 16) for value in match.groups()]
        if observed[:3] != [mode, 8, 11]:
            raise SystemExit(f"selector mismatch: {log.name}")
        samples.append({
            "mode": mode, "name": name, "cycles": observed[3],
            "checksum": observed[4], "log": log.name,
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        })

summary = []
for mode, name in enumerate(NAMES):
    values = [sample["cycles"] for sample in samples if sample["mode"] == mode]
    median = statistics.median(values)
    summary.append({
        "mode": mode, "name": name, "samples": values,
        "median_cycles": median, "min_cycles": min(values),
        "max_cycles": max(values), "median_cycles_per_node": median / 88,
    })

(OUT / "board-all-samples.json").write_text(json.dumps(samples, indent=2) + "\n")
(OUT / "board-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
