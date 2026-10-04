#!/usr/bin/env python3
"""Cross-check repeated demand lifecycle outcomes and exploratory hazard math."""
import hashlib
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE.parent
BIT = "9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf"
NBF = "af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3"
CONTROL = "be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e"
ROW_RE = re.compile(
    r"^RESULT sample=(\d+) order=(\d+) mode=([^ ]+) ns=(\d+) "
    r"requests=(\d+) checksum=(\d+) cycles=(\d+)$", re.M)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_body(path, name, useful_count):
    text = path.read_text()
    label = re.search(rf"^([0-9a-f]+) <{name}>:$", text, re.M)
    if not label:
        raise SystemExit(f"missing {name} in {path}")
    tail = text[label.end():]
    next_label = re.search(r"^[0-9a-f]+ <[^>]+>:$", tail, re.M)
    section = tail[:next_label.start()] if next_label else tail
    opcodes = re.findall(r"^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s+", section, re.M)
    if len(opcodes) < useful_count:
        raise SystemExit(f"short {name} body in {path}")
    return int(label.group(1), 16), opcodes[:useful_count]


def validate_platform(path, elf):
    board = (path / "board.log").read_text(errors="replace").replace("\r", "")
    if sha(path / "request_benchmark_dynamic") != elf:
        raise SystemExit(f"ELF identity mismatch in {path.name}")
    for marker in (
            f"{elf}  /tmp/request_benchmark_dynamic",
            f"CONTROL_PROGRAM_SHA256={CONTROL}", f"NBF_SHA256={NBF}"):
        if marker not in board:
            raise SystemExit(f"missing board marker {marker} in {path.name}")
    if "PYNQ_READY_OK=1" not in (path / "board-ready.log").read_text():
        raise SystemExit(f"readiness missing in {path.name}")
    overlay = (path / "overlay-load.log").read_text()
    for marker in (
            f"LOADING_BIT_SHA256={BIT}", "OVERLAY_LOAD_OK=1",
            "REMOTE_FPGA_STATE=operating", "REMOTE_FPGA_STATE_OK=1"):
        if marker not in overlay:
            raise SystemExit(f"missing overlay marker {marker} in {path.name}")
    return board


cases = [
    {
        "name": "exact-new-demand-run-a",
        "directory": "linux-hardware-demand-lifecycle-isolation-20261003",
        "elf": "8d95f0cfbf91686836ab72b2fe3029bdee1f338a2658774ca1034debf5b1d643",
        "expected_complete": 26, "expected_started": 27,
        "outcome": "post-run verification failure",
    },
    {
        "name": "exact-new-demand-run-b",
        "directory": "linux-hardware-demand-exact-repeat-20261003",
        "elf": "8d95f0cfbf91686836ab72b2fe3029bdee1f338a2658774ca1034debf5b1d643",
        "expected_complete": 2, "expected_started": 3,
        "outcome": "in-loop nonreturn",
    },
    {
        "name": "diagnostic-plus-32-bytes",
        "directory": "linux-hardware-demand-failure-values-20261003",
        "elf": "e2f48758d80f1dab791f112ba1cf3778594a2ad573dd2add664888ee069272cf",
        "expected_complete": 64, "expected_started": 64,
        "outcome": "pass",
    },
    {
        "name": "hardware-loops-aligned-64",
        "directory": "linux-hardware-demand-aligned64-20261003",
        "elf": "90411570eaf29908cd5d94d1d6eac449f9fde0d36261234860f445cc2ffe22d8",
        "expected_complete": 50, "expected_started": 51,
        "outcome": "in-loop nonreturn",
    },
]

base_disassembly = LOGS / cases[0]["directory"] / "disassembly.txt"
base_bodies = {
    name: function_body(base_disassembly, name, count)[1]
    for name, count in (("source_demand", 16), ("peer_demand", 22))
}
results = []
for case in cases:
    path = LOGS / case["directory"]
    board = validate_platform(path, case["elf"])
    rows = []
    for values in ROW_RE.findall(board):
        sample, order, mode, _, requests, checksum, cycles = values
        if (int(order), mode, int(requests), int(checksum)) != (
                0, "resident-demand-handoff", 8192, 133130652):
            raise SystemExit(f"result mismatch in {case['name']}")
        rows.append((int(sample), int(cycles)))
    begins = [int(x) for x in re.findall(r"^SAMPLE_BEGIN sample=(\d+) ", board, re.M)]
    if [sample for sample, _ in rows] != list(
            range(1, case["expected_complete"] + 1)):
        raise SystemExit(f"complete-prefix mismatch in {case['name']}")
    if not begins or begins[-1] != case["expected_started"]:
        raise SystemExit(f"last-started mismatch in {case['name']}")
    status = json.loads((path / "board-status.json").read_text())
    if case["outcome"] == "pass":
        if (status.get("status"), status.get("result_rows"),
                status.get("request_exit"), status.get("core_pass")) != (
                    "PASS", 64, 0, True):
            raise SystemExit("diagnostic pass status mismatch")
        if "[REQUEST-BENCH] PASS" not in board:
            raise SystemExit("diagnostic PASS marker missing")
    elif case["outcome"] == "post-run verification failure":
        if "hardware context/completion verification failed" not in board:
            raise SystemExit("verification failure marker missing")
    else:
        if (status.get("status"), status.get("observed_outcome"),
                status.get("result_rows"), status.get("last_started_sample")) != (
                    "MEASURED_STALL", "IN_LOOP_NONRETURN",
                    case["expected_complete"], case["expected_started"]):
            raise SystemExit(f"nonreturn status mismatch in {case['name']}")
    functions = {}
    for name, count in (("source_demand", 16), ("peer_demand", 22)):
        address, opcodes = function_body(path / "disassembly.txt", name, count)
        if opcodes != base_bodies[name]:
            raise SystemExit(f"opcode mismatch for {name} in {case['name']}")
        functions[name] = {
            "address_hex": hex(address), "offset_in_64_byte_line": address % 64,
            "functional_opcodes_identical": True,
        }
    results.append({
        "name": case["name"], "elf_sha256": case["elf"],
        "complete_samples": len(rows), "last_started_sample": begins[-1],
        "outcome": case["outcome"], "demand_functions": functions,
    })

# Validate the same exact ELF's mixed-mode failure, without treating its other
# modes as demand launches in the exploratory demand-only hazard calculation.
attribution = json.loads((
    LOGS / "linux-hardware-group-demand-attribution-20261003/analysis.json").read_text())
mixed = attribution["excluded_32_sample_run"]
if (attribution["artifact_identity"]["elf_sha256"] != cases[0]["elf"]
        or mixed["complete_samples_per_mode"] != 16
        or mixed["last_marker"] !=
        "SAMPLE_BEGIN sample=17 order=0 mode=resident-demand-handoff"):
    raise SystemExit("mixed-run evidence mismatch")

# Validate the older ELF's accepted 32-sample pass and its identical useful
# demand opcodes. This is context, not part of the new-family hazard estimate.
old_path = LOGS / "linux-hardware-group-cold-demand-20261003"
old_analysis = json.loads((old_path / "analysis.json").read_text())
old_elf = "de53ce7c669c469630367b4b93e512a2f85ea5a8b6337c787ad7eb4b5971d2ee"
if (old_analysis["artifact_identity"]["elf_sha256"] != old_elf
        or old_analysis["mode_summary"]["resident-demand-handoff"]["samples"] != 32):
    raise SystemExit("older pass evidence mismatch")
old_functions = {}
for name, count in (("source_demand", 16), ("peer_demand", 22)):
    address, opcodes = function_body(old_path / "disassembly.txt", name, count)
    if opcodes != base_bodies[name]:
        raise SystemExit(f"older {name} opcode mismatch")
    old_functions[name] = {
        "address_hex": hex(address), "offset_in_64_byte_line": address % 64,
        "functional_opcodes_identical": True,
    }

# Exploratory constant independent per-launch hazard model over the four
# demand-only new-family runs. A pass is right-censored after its 64 successes.
successes = sum(case["expected_complete"] for case in cases)
failures = sum(case["outcome"] != "pass" for case in cases)
trials = successes + failures
hazard = failures / trials
z = 1.959963984540054
denom = 1 + z * z / trials
center = (hazard + z * z / (2 * trials)) / denom
half = z * math.sqrt(
    hazard * (1 - hazard) / trials + z * z / (4 * trials * trials)) / denom

result = {
    "artifact_identity": {
        "bitstream_sha256": BIT, "linux_shell_nbf_sha256": NBF,
        "control_program_sha256": CONTROL,
    },
    "demand_only_runs": results,
    "same_exact_new_elf_mixed_run": {
        "complete_hardware_samples": 16,
        "failure_sample": 17,
        "outcome": "post-run verification failure",
    },
    "older_elf_control": {
        "complete_hardware_samples": 32, "outcome": "pass",
        "elf_sha256": old_elf, "demand_functions": old_functions,
    },
    "observed_conclusions": [
        "The exact newer ELF fails in all three physical attempts, but at variable samples 17, 27, and 3.",
        "Moving the functional demand bodies and aligning them to 64-byte boundaries does not eliminate the failure: the aligned control stalls in sample 51.",
        "The diagnostic ELF's 64-sample pass therefore does not establish a placement fix.",
        "Both post-run verification failures and in-loop nonreturns occur, indicating at least two visible terminal states of the same unresolved lifecycle class.",
    ],
    "exploratory_constant_hazard_model": {
        "scope": "four demand-only new-family runs",
        "completed_samples": successes,
        "observed_failed_launches": failures,
        "total_launches_including_failures": trials,
        "maximum_likelihood_failure_probability_per_launch": hazard,
        "wilson_95_interval": {"low": center - half, "high": center + half},
        "model_probability_of_64_consecutive_successes": (1 - hazard) ** 64,
        "warning": "This model assumes independent launches with one constant hazard despite ELF/layout differences; use it only to show that one 64-sample pass is statistically compatible with the observed intermittent failures.",
    },
    "next_step":
        "Add bounded progress records inside both demand loops so a failing run identifies the context and iteration where handoff progress stops; code alignment alone is not a fix.",
}
print(json.dumps(result, indent=2))
