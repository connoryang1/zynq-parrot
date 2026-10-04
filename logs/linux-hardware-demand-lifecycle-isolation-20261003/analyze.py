#!/usr/bin/env python3
"""Validate the demand-only lifecycle stall and compare executable bodies."""
import hashlib
import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / "logs/linux-hardware-group-cold-demand-20261003"
ATTRIBUTION = ROOT / "logs/linux-hardware-group-demand-attribution-20261003"

EXPECTED_NEW_ELF = "8d95f0cfbf91686836ab72b2fe3029bdee1f338a2658774ca1034debf5b1d643"
EXPECTED_OLD_ELF = "de53ce7c669c469630367b4b93e512a2f85ea5a8b6337c787ad7eb4b5971d2ee"
EXPECTED_BIT = "9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf"
EXPECTED_NBF = "af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3"
EXPECTED_CONTROL = "be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e"
ROW_RE = re.compile(
    r"^RESULT sample=(\d+) order=(\d+) mode=([^ ]+) ns=(\d+) "
    r"requests=(\d+) checksum=(\d+) cycles=(\d+)$", re.M)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


board = (HERE / "board.log").read_text(errors="replace").replace("\r", "")
status = json.loads((HERE / "board-status.json").read_text())
ready = (HERE / "board-ready.log").read_text()
overlay = (HERE / "overlay-load.log").read_text()
if sha(HERE / "request_benchmark_dynamic") != EXPECTED_NEW_ELF:
    raise SystemExit("new guest ELF identity mismatch")
if sha(OLD / "request_benchmark_dynamic") != EXPECTED_OLD_ELF:
    raise SystemExit("old guest ELF identity mismatch")
for marker in (
        f"{EXPECTED_NEW_ELF}  /tmp/request_benchmark_dynamic",
        f"CONTROL_PROGRAM_SHA256={EXPECTED_CONTROL}",
        f"NBF_SHA256={EXPECTED_NBF}"):
    if marker not in board:
        raise SystemExit(f"board identity marker missing: {marker}")
if "PYNQ_READY_OK=1" not in ready:
    raise SystemExit("readiness gate missing")
for marker in (
        f"LOADING_BIT_SHA256={EXPECTED_BIT}", "OVERLAY_LOAD_OK=1",
        "REMOTE_FPGA_STATE=operating", "REMOTE_FPGA_STATE_OK=1"):
    if marker not in overlay:
        raise SystemExit(f"overlay identity marker missing: {marker}")

header = re.search(
    r"REQUEST_BENCH .* workers=(\d+) hardware=(\d+) "
    r"requests_per_worker=(\d+) data_bytes=(\d+) samples=(\d+) "
    r"mode_mask=(\d+) hardware_prime_lines=(\d+).* checksum=(\d+)", board)
expected_header = (2, 1, 4096, 2097152, 64, 4, 0, 133130652)
if not header or tuple(map(int, header.groups())) != expected_header:
    raise SystemExit("benchmark configuration mismatch")
if board.count("WARMUP_PASS mode=resident-demand-handoff") != 1:
    raise SystemExit("hardware-demand warmup evidence mismatch")

rows = []
for match in ROW_RE.findall(board):
    sample, order, mode, ns, requests, checksum, cycles = match
    row = {
        "sample": int(sample), "order": int(order), "mode": mode,
        "nanoseconds_reported": int(ns), "requests": int(requests),
        "checksum": int(checksum), "cycles": int(cycles),
    }
    if (row["order"], row["mode"], row["requests"], row["checksum"]) != (
            0, "resident-demand-handoff", 8192, 133130652):
        raise SystemExit("result identity/checksum mismatch")
    rows.append(row)
if [row["sample"] for row in rows] != list(range(1, 27)):
    raise SystemExit("expected exactly the complete sample 1--26 prefix")
failure_marker = "SAMPLE_BEGIN sample=27 order=0 mode=resident-demand-handoff"
if failure_marker not in board:
    raise SystemExit("sample-27 begin marker missing")
if re.search(r"^RESULT sample=27 ", board, re.M):
    raise SystemExit("sample 27 unexpectedly has a result")
if board.count("hardware context/completion verification failed") != 1:
    raise SystemExit("sample-27 verification failure marker missing")
for forbidden in ("[REQUEST-BENCH] PASS", "REQUEST_EXIT=0", "CORE[0] PASS"):
    if forbidden in board:
        raise SystemExit(f"stalled run unexpectedly contains {forbidden}")
if (status.get("status"), status.get("stage"), status.get("recovery_required")) != (
        "FAIL", "measurement", True):
    raise SystemExit("runner failure status mismatch")
if status.get("binary_sha256") != EXPECTED_NEW_ELF or status.get(
        "linux_nbf_sha256") != EXPECTED_NBF:
    raise SystemExit("runner artifact identity mismatch")
if "exitstatus: 124" not in status.get("error", ""):
    raise SystemExit("runner timeout identity missing")


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
    if not opcodes:
        raise SystemExit(f"missing opcodes for {name} in {path}")
    return address, opcodes


old_disassembly = OLD / "disassembly.txt"
new_disassembly = HERE / "disassembly.txt"
functions = {}
for name, expected_count in (("source_demand", 16), ("peer_demand", 22)):
    old_address, old_opcodes = function_body(old_disassembly, name)
    new_address, new_opcodes = function_body(new_disassembly, name)
    if len(old_opcodes) != expected_count or len(new_opcodes) != expected_count:
        raise SystemExit(f"unexpected {name} instruction count")
    if old_opcodes != new_opcodes:
        raise SystemExit(f"{name} opcode body changed")
    functions[name] = {
        "old_address_hex": hex(old_address),
        "new_address_hex": hex(new_address),
        "address_shift_bytes": new_address - old_address,
        "instruction_count": len(new_opcodes),
        "opcode_body_identical": True,
        "old_64_byte_line": old_address // 64,
        "new_64_byte_line": new_address // 64,
        "old_offset_within_64_byte_line": old_address % 64,
        "new_offset_within_64_byte_line": new_address % 64,
    }

old_analysis = json.loads((OLD / "analysis.json").read_text())
old_hardware = old_analysis["mode_summary"]["resident-demand-handoff"]
if (old_analysis["artifact_identity"]["elf_sha256"] != EXPECTED_OLD_ELF
        or old_analysis["artifact_identity"]["bitstream_sha256"] != EXPECTED_BIT
        or old_hardware["samples"] != 32):
    raise SystemExit("old accepted comparison identity/coverage mismatch")

attribution = json.loads((ATTRIBUTION / "analysis.json").read_text())
excluded = attribution["excluded_32_sample_run"]
if (attribution["artifact_identity"]["elf_sha256"] != EXPECTED_NEW_ELF
        or excluded["complete_samples_per_mode"] != 16
        or excluded["last_marker"] !=
        "SAMPLE_BEGIN sample=17 order=0 mode=resident-demand-handoff"):
    raise SystemExit("mixed-run comparison identity mismatch")

cycles = [row["cycles"] for row in rows]
ordered = sorted(cycles)
result = {
    "accepted_performance_result": False,
    "classification": "measured lifecycle failure",
    "artifact_identity": {
        "new_elf_sha256": EXPECTED_NEW_ELF,
        "old_elf_sha256": EXPECTED_OLD_ELF,
        "bitstream_sha256": EXPECTED_BIT,
        "linux_shell_nbf_sha256": EXPECTED_NBF,
        "control_program_sha256": EXPECTED_CONTROL,
    },
    "demand_only_run": {
        "requested_samples": 64,
        "complete_samples": len(rows),
        "complete_requests": len(rows) * 8192,
        "last_complete_sample": 26,
        "failure_sample": 27,
        "failure_marker": failure_marker,
        "observed_failure": "hardware context/completion verification failed",
        "runner_exit_status": 124,
        "median_cycles_of_diagnostic_prefix": statistics.median(cycles),
        "min_cycles_of_diagnostic_prefix": ordered[0],
        "max_cycles_of_diagnostic_prefix": ordered[-1],
        "prefix_population_coefficient_of_variation":
            statistics.pstdev(cycles) / statistics.mean(cycles),
        "cycles": cycles,
    },
    "comparisons": {
        "same_new_elf_mixed_run_complete_samples_per_mode": 16,
        "same_new_elf_mixed_run_failure_sample": 17,
        "old_elf_demand_run_complete_samples": 32,
        "old_elf_demand_run_median_cycles": old_hardware["median_cycles"],
        "demand_function_bodies": functions,
    },
    "deductions": [
        "Mixed benchmark modes are not required to trigger the failure.",
        "The failure is not a deterministic limit at 16 hardware-demand samples.",
        "The hardware-demand instruction bodies are identical between the old 32-sample-passing ELF and the newer failing ELF, but both bodies moved by 264 bytes.",
        "Code placement or accumulated architectural/microarchitectural state remains plausible; this evidence does not establish either cause.",
    ],
    "limits": [
        "The 26-row prefix is diagnostic only because the declared 64-sample run did not complete.",
        "The generic verification message does not identify whether current_context, peer completion count, or peer terminal context was wrong.",
        "A controlled multi-placement experiment is required before attributing the failure to an instruction-cache set or address.",
    ],
}
print(json.dumps(result, indent=2))
