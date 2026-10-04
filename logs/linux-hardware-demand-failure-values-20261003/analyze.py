#!/usr/bin/env python3
"""Validate the 64-sample failure-value diagnostic pass."""
import hashlib
import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "linux-hardware-demand-lifecycle-isolation-20261003"
EXPECTED_ELF = "e2f48758d80f1dab791f112ba1cf3778594a2ad573dd2add664888ee069272cf"
EXPECTED_BASE_ELF = "8d95f0cfbf91686836ab72b2fe3029bdee1f338a2658774ca1034debf5b1d643"
EXPECTED_BIT = "9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf"
EXPECTED_NBF = "af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3"
EXPECTED_CONTROL = "be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e"
ROW_RE = re.compile(
    r"^RESULT sample=(\d+) order=(\d+) mode=([^ ]+) ns=(\d+) "
    r"requests=(\d+) checksum=(\d+) cycles=(\d+)$", re.M)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_body(path, name):
    text = path.read_text()
    label = re.search(rf"^([0-9a-f]+) <{name}>:$", text, re.M)
    if not label:
        raise SystemExit(f"missing {name} in {path}")
    address = int(label.group(1), 16)
    tail = text[label.end():]
    next_label = re.search(r"^[0-9a-f]+ <[^>]+>:$", tail, re.M)
    section = tail[:next_label.start()] if next_label else tail
    opcodes = re.findall(r"^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s+", section, re.M)
    return address, opcodes


if sha(HERE / "request_benchmark_dynamic") != EXPECTED_ELF:
    raise SystemExit("diagnostic ELF identity mismatch")
if sha(BASE / "request_benchmark_dynamic") != EXPECTED_BASE_ELF:
    raise SystemExit("base ELF identity mismatch")
board = (HERE / "board.log").read_text(errors="replace").replace("\r", "")
status = json.loads((HERE / "board-status.json").read_text())
ready = (HERE / "board-ready.log").read_text()
overlay = (HERE / "overlay-load.log").read_text()
for marker in (
        f"{EXPECTED_ELF}  /tmp/request_benchmark_dynamic",
        f"CONTROL_PROGRAM_SHA256={EXPECTED_CONTROL}",
        f"NBF_SHA256={EXPECTED_NBF}", "[REQUEST-BENCH] PASS",
        "REQUEST_EXIT=0", "CORE[0] PASS"):
    if marker not in board:
        raise SystemExit(f"board marker missing: {marker}")
if "HARDWARE_VERIFY_FAIL" in board:
    raise SystemExit("failure reporter unexpectedly triggered")
if "PYNQ_READY_OK=1" not in ready:
    raise SystemExit("readiness gate missing")
for marker in (
        f"LOADING_BIT_SHA256={EXPECTED_BIT}", "OVERLAY_LOAD_OK=1",
        "REMOTE_FPGA_STATE=operating", "REMOTE_FPGA_STATE_OK=1"):
    if marker not in overlay:
        raise SystemExit(f"overlay marker missing: {marker}")
header = re.search(
    r"REQUEST_BENCH .* workers=(\d+) hardware=(\d+) "
    r"requests_per_worker=(\d+) data_bytes=(\d+) samples=(\d+) "
    r"mode_mask=(\d+) hardware_prime_lines=(\d+).* checksum=(\d+)", board)
if not header or tuple(map(int, header.groups())) != (
        2, 1, 4096, 2097152, 64, 4, 0, 133130652):
    raise SystemExit("benchmark configuration mismatch")
if board.count("WARMUP_PASS mode=resident-demand-handoff") != 1:
    raise SystemExit("warmup coverage mismatch")

rows = []
for values in ROW_RE.findall(board):
    sample, order, mode, ns, requests, checksum, cycles = values
    row = {
        "sample": int(sample), "order": int(order), "mode": mode,
        "nanoseconds_reported": int(ns), "requests": int(requests),
        "checksum": int(checksum), "cycles": int(cycles),
    }
    if (row["order"], row["mode"], row["requests"], row["checksum"]) != (
            0, "resident-demand-handoff", 8192, 133130652):
        raise SystemExit("result identity/checksum mismatch")
    rows.append(row)
if [row["sample"] for row in rows] != list(range(1, 65)):
    raise SystemExit("64-sample coverage mismatch")
if (status.get("status"), status.get("stage"), status.get("observed_outcome"),
        status.get("request_exit"), status.get("result_rows"),
        status.get("runner_exit"), status.get("core_pass"),
        status.get("recovery_required")) != (
            "PASS", "complete", "PASS", 0, 64, 0, True, False):
    raise SystemExit("runner status mismatch")
if status.get("binary_sha256") != EXPECTED_ELF or status.get(
        "linux_nbf_sha256") != EXPECTED_NBF:
    raise SystemExit("runner identity mismatch")

functions = {}
for name, count in (("source_demand", 16), ("peer_demand", 22)):
    base_address, base_opcodes = function_body(BASE / "disassembly.txt", name)
    address, opcodes = function_body(HERE / "disassembly.txt", name)
    if len(opcodes) != count or opcodes != base_opcodes:
        raise SystemExit(f"{name} opcode body mismatch")
    functions[name] = {
        "base_address_hex": hex(base_address),
        "diagnostic_address_hex": hex(address),
        "address_shift_bytes": address - base_address,
        "instruction_count": len(opcodes),
        "opcode_body_identical": True,
    }

cycles = [row["cycles"] for row in rows]
result = {
    "accepted_functional_result": True,
    "primary_classification": "64-sample lifecycle pass",
    "artifact_identity": {
        "diagnostic_elf_sha256": EXPECTED_ELF,
        "previously_failing_elf_sha256": EXPECTED_BASE_ELF,
        "bitstream_sha256": EXPECTED_BIT,
        "linux_shell_nbf_sha256": EXPECTED_NBF,
        "control_program_sha256": EXPECTED_CONTROL,
    },
    "configuration": {
        "samples": 64, "requests_per_sample": 8192,
        "total_checked_requests": 64 * 8192,
        "mode": "resident-demand-handoff", "data_bytes": 2097152,
        "hardware_prime_lines": 0,
    },
    "result": {
        "warmup_pass": True, "complete_samples": len(rows),
        "checksum_verified_rows": len(rows), "request_exit": 0,
        "core_pass": True, "failure_reporter_triggered": False,
        "median_cycles": statistics.median(cycles),
        "median_cycles_per_request": statistics.median(cycles) / 8192,
        "min_cycles": min(cycles), "max_cycles": max(cycles),
        "population_coefficient_of_variation":
            statistics.pstdev(cycles) / statistics.mean(cycles),
        "cycles": cycles,
    },
    "demand_function_comparison": functions,
    "deductions": [
        "The lifecycle failure is not an inevitable accumulated-state limit below 64 demand samples.",
        "The identical demand-loop instructions can complete 524288 checked requests in this shifted diagnostic ELF.",
        "The pass is consistent with placement sensitivity but does not prove it because instrumentation and fresh-boot/run variation are confounded.",
    ],
    "next_discriminating_test":
        "Repeat the exact previously failing ELF after a fresh boot, then compare multiple controlled placements if its failure reproduces.",
}
print(json.dumps(result, indent=2))
