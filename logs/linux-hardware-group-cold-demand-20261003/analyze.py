#!/usr/bin/env python3
"""Analyze the accepted cache-displaced hardware-group demand comparison."""
import hashlib
import json
import random
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
STDOUT = (HERE / "benchmark.stdout.txt").read_text()
BOARD = (HERE / "board.log").read_text(errors="replace").replace("\r", "")
EXPECTED_ELF = "de53ce7c669c469630367b4b93e512a2f85ea5a8b6337c787ad7eb4b5971d2ee"
EXPECTED_BIT = "9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf"
EXPECTED_NBF = "af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3"
MODES = (
    "linux-threads-demand", "batched-prefetch-load",
    "resident-demand-handoff",
)

elf_hash = hashlib.sha256((HERE / "request_benchmark_dynamic").read_bytes()).hexdigest()
if elf_hash != EXPECTED_ELF or EXPECTED_ELF not in BOARD:
    raise SystemExit("guest ELF identity mismatch")
if "PYNQ_READY_OK=1" not in (HERE / "board-ready.log").read_text():
    raise SystemExit("readiness gate missing")
overlay = (HERE / "overlay-load.log").read_text()
for marker in (
        f"LOADING_BIT_SHA256={EXPECTED_BIT}", "OVERLAY_LOAD_OK=1",
        "REMOTE_FPGA_STATE=operating", "REMOTE_FPGA_STATE_OK=1"):
    if marker not in overlay:
        raise SystemExit(f"overlay evidence missing {marker}")

header = re.search(
    r"REQUEST_BENCH .* workers=(\d+) hardware=(\d+) "
    r"requests_per_worker=(\d+) data_bytes=(\d+) samples=(\d+) "
    r"mode_mask=(\d+) hardware_prime_lines=(\d+).* checksum=(\d+)", STDOUT)
if not header or tuple(map(int, header.groups())) != (
        2, 1, 4096, 2097152, 32, 7, 0, 133130652):
    raise SystemExit("benchmark configuration mismatch")
for mode in MODES:
    if STDOUT.count(f"WARMUP_PASS mode={mode}") != 1:
        raise SystemExit(f"warmup coverage mismatch for {mode}")

pattern = re.compile(
    r"^RESULT sample=(\d+) order=(\d+) mode=([^ ]+) ns=(\d+) "
    r"requests=(\d+) checksum=(\d+) cycles=(\d+)$", re.M)
matches = pattern.findall(STDOUT)
if len(matches) != 96:
    raise SystemExit(f"expected 96 result rows, found {len(matches)}")
rows = []
by_mode = {mode: [] for mode in MODES}
coverage = set()
order_counts = {mode: [0, 0, 0] for mode in MODES}
for values in matches:
    sample, order, mode, ns, requests, checksum, cycles = values
    sample, order, ns, requests, checksum, cycles = map(
        int, (sample, order, ns, requests, checksum, cycles))
    if mode not in by_mode or not 1 <= sample <= 32 or not 0 <= order < 3:
        raise SystemExit("invalid result identity")
    if requests != 8192 or checksum != 133130652:
        raise SystemExit("request/checksum mismatch")
    if (sample, mode) in coverage:
        raise SystemExit("duplicate sample/mode")
    coverage.add((sample, mode))
    order_counts[mode][order] += 1
    row = {
        "sample": sample, "order": order, "mode": mode,
        "nanoseconds_reported": ns, "requests": requests,
        "checksum": checksum, "cycles": cycles,
    }
    rows.append(row)
    by_mode[mode].append(row)
if coverage != {(sample, mode) for sample in range(1, 33) for mode in MODES}:
    raise SystemExit("sample/mode coverage mismatch")
if any(sorted(counts) != [10, 11, 11] for counts in order_counts.values()):
    raise SystemExit("mode order is not balanced")

def percentile(sorted_values, fraction):
    return sorted_values[int(fraction * len(sorted_values))]

summary = {}
for mode in MODES:
    values = [row["cycles"] for row in by_mode[mode]]
    ordered = sorted(values)
    median = statistics.median(values)
    summary[mode] = {
        "samples": len(values),
        "min_cycles": ordered[0],
        "median_cycles": median,
        "p95_cycles": percentile(ordered, 0.95),
        "max_cycles": ordered[-1],
        "median_cycles_per_request": median / 8192,
        "population_coefficient_of_variation":
            statistics.pstdev(values) / statistics.mean(values),
        "order_counts": order_counts[mode],
        "cycles": values,
    }

linux = {row["sample"]: row["cycles"] for row in by_mode[MODES[0]]}
batch = {row["sample"]: row["cycles"] for row in by_mode[MODES[1]]}
hardware = {row["sample"]: row["cycles"] for row in by_mode[MODES[2]]}
rng = random.Random(20261003)
bootstrap = []
for _ in range(20000):
    selected = [rng.randrange(1, 33) for _ in range(32)]
    linux_median = statistics.median(linux[index] for index in selected)
    batch_median = statistics.median(batch[index] for index in selected)
    hardware_median = statistics.median(hardware[index] for index in selected)
    bootstrap.append((
        linux_median / hardware_median,
        batch_median / hardware_median,
        linux_median - hardware_median,
    ))

def interval(column):
    values = sorted(row[column] for row in bootstrap)
    return {
        "low_95": values[500],
        "bootstrap_median": statistics.median(values),
        "high_95": values[19500],
    }

linux_median = summary[MODES[0]]["median_cycles"]
batch_median = summary[MODES[1]]["median_cycles"]
hardware_median = summary[MODES[2]]["median_cycles"]
status = json.loads((HERE / "board-status.json").read_text())
if (status.get("status"), status.get("result_rows"), status.get("runner_exit"),
        status.get("request_exit"), status.get("core_pass")) != (
        "PASS", 96, 0, 0, True):
    raise SystemExit("runner status mismatch")
if status.get("binary_sha256") != EXPECTED_ELF or status.get("linux_nbf_sha256") != EXPECTED_NBF:
    raise SystemExit("runner identity mismatch")
for marker in ("[REQUEST-BENCH] PASS", "REQUEST_EXIT=0", "CORE[0] PASS"):
    if marker not in BOARD:
        raise SystemExit(f"missing board marker {marker}")

result = {
    "accepted": True,
    "artifact_identity": {
        "elf_sha256": elf_hash,
        "bitstream_sha256": EXPECTED_BIT,
        "linux_shell_nbf_sha256": EXPECTED_NBF,
    },
    "configuration": {
        "samples_per_mode": 32,
        "workers": 2,
        "requests_per_worker": 4096,
        "total_requests_per_sample": 8192,
        "data_bytes": 2097152,
        "cache_displacement_bytes": 4194304,
        "mode_mask": 7,
        "hardware_prime_lines": 0,
        "checksum": 133130652,
    },
    "mode_summary": summary,
    "comparisons": {
        "linux_over_resident_hardware_median_speedup": linux_median / hardware_median,
        "batch_over_resident_hardware_median_ratio": batch_median / hardware_median,
        "linux_over_batch_median_ratio": linux_median / batch_median,
        "resident_hardware_cycles_saved_vs_linux_median": linux_median - hardware_median,
        "resident_hardware_cycles_saved_vs_batch_median": batch_median - hardware_median,
        "resident_hardware_p95_speedup_vs_linux_p95":
            summary[MODES[0]]["p95_cycles"] / summary[MODES[2]]["p95_cycles"],
        "paired_bootstrap_linux_over_hardware_speedup": interval(0),
        "paired_bootstrap_batch_over_hardware_ratio": interval(1),
        "paired_bootstrap_linux_minus_hardware_cycles": interval(2),
        "previous_incomplete_four_sample_linux_over_hardware_ratio": 1.1203403469449735,
    },
    "limits": [
        "Cache displacement is best effort and random request streams can revisit lines; this does not prove that every request misses.",
        "The pthread baseline includes thread release and drain, while the hardware path uses leaf assembly and switches on every request; the result is an end-to-end implementation comparison, not an isolated switch-cost attribution.",
        "The excluded resident-prefetch-yield-load mode still has a separately recorded sustained lifecycle stall, so this result does not establish an integrated hardware-prefetch speedup.",
        "CLOCK_MONOTONIC values are retained as reported, but conclusions use the core cycle counter.",
    ],
}
print(json.dumps(result, indent=2))
