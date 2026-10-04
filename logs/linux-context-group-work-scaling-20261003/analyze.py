#!/usr/bin/env python3
"""Analyze matched Linux scheduler and hardware context-group work scaling."""
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEXT = (HERE / "board.log").read_text(errors="replace").replace("\r", "")
EXPECTED_ELF = "95daa65a98151423cbcacac9655111a9e76034edaab9c9ea81c7ef2e323ad236"
EXPECTED_BITSTREAM = "9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf"
EXPECTED_SHELL = "af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3"

elf_hash = hashlib.sha256((HERE / "context_group_work_scaling").read_bytes()).hexdigest()
if elf_hash != EXPECTED_ELF or EXPECTED_ELF not in TEXT:
    raise SystemExit("accepted guest ELF identity mismatch")
ready_text = (HERE / "board-ready-retry.log").read_text()
overlay_text = (HERE / "overlay-load-retry.log").read_text()
if "PYNQ_READY_OK=1" not in ready_text:
    raise SystemExit("accepted readiness gate missing")
for marker in (
        f"LOADING_BIT_SHA256={EXPECTED_BITSTREAM}", "OVERLAY_LOAD_OK=1",
        "REMOTE_FPGA_STATE=operating", "REMOTE_FPGA_STATE_OK=1"):
    if marker not in overlay_text:
        raise SystemExit(f"accepted overlay evidence missing {marker}")

HEADER = re.search(
    r"CONTEXT_GROUP_WORK_SCALING samples=(\d+) warmups=(\d+) turns=(\d+) "
    r"sink=(\d+)", TEXT)
if not HEADER:
    raise SystemExit("missing work-scaling header")
samples, warmups, turns, sink = map(int, HEADER.groups())
if (samples, warmups, turns) != (64, 8, 64):
    raise SystemExit("unexpected benchmark dimensions")

pattern = re.compile(
    r"WORK_SCALING iterations=(\d+) "
    r"work_aggregate=(\d+) work_x100_per_call=(\d+) "
    r"linux_aggregate=(\d+) linux_x100_per_handoff=(\d+) "
    r"resident_aggregate=(\d+) resident_x100_per_handoff=(\d+) "
    r"nonresident_aggregate=(\d+) nonresident_x100_per_handoff=(\d+)")
matches = pattern.findall(TEXT)
if len(matches) != 6:
    raise SystemExit(f"expected 6 scaling rows, found {len(matches)}")

rows = []
for values in matches:
    (iterations, work_aggregate, work_x100, linux_aggregate, linux_x100,
     resident_aggregate, resident_x100, nonresident_aggregate,
     nonresident_x100) = map(int, values)
    # Check the guest's integer summaries against the raw aggregate medians.
    if work_x100 != work_aggregate * 100 // turns:
        raise SystemExit("work summary mismatch")
    for aggregate, x100 in (
            (linux_aggregate, linux_x100),
            (resident_aggregate, resident_x100),
            (nonresident_aggregate, nonresident_x100)):
        if x100 != aggregate * 100 // (2 * turns):
            raise SystemExit("handoff summary mismatch")
    rows.append({
        "iterations": iterations,
        "work_cycles_per_call": work_aggregate / turns,
        "linux_cycles_per_handoff": linux_aggregate / (2 * turns),
        "resident_cycles_per_handoff": resident_aggregate / (2 * turns),
        "nonresident_cycles_per_handoff": nonresident_aggregate / (2 * turns),
    })

if [row["iterations"] for row in rows] != [0, 16, 64, 256, 1024, 4096]:
    raise SystemExit("unexpected work levels")

retry_match = re.search(
    r"SC_FAILURES resident_source=(\d+) resident_peer=(\d+) "
    r"nonresident_source=(\d+) nonresident_peer=(\d+)", TEXT)
fault_match = re.search(r"FAULTS minor=(\d+) major=(\d+)", TEXT)
work_match = re.search(r"WORK_CHECK status=(\w+) expected_delta=(\d+)", TEXT)
if not retry_match or not fault_match or not work_match:
    raise SystemExit("missing correctness summaries")
retries = list(map(int, retry_match.groups()))
minor_faults, major_faults = map(int, fault_match.groups())
if work_match.group(1) != "PASS" or int(work_match.group(2)) != 25141248:
    raise SystemExit("work checksum failed")
if major_faults != 0 or minor_faults > 24:
    raise SystemExit("fault bound failed")
for marker in (
        "[CONTEXT-GROUP-WORK-SCALING] PASS", "PROBE_EXIT=0",
        "CORE[0] PASS"):
    if marker not in TEXT:
        raise SystemExit(f"missing {marker}")
status = json.loads((HERE / "board-status.json").read_text())
if status.get("status") != "PASS" or status.get("runner_exit") != 0:
    raise SystemExit("runner status failed")
if status.get("binary_sha256") != EXPECTED_ELF:
    raise SystemExit("runner ELF identity mismatch")

baseline = rows[0]
for row in rows:
    incremental_work = row["work_cycles_per_call"] - baseline["work_cycles_per_call"]
    predicted_linux = baseline["linux_cycles_per_handoff"] + incremental_work
    predicted_resident = baseline["resident_cycles_per_handoff"] + incremental_work
    predicted_nonresident = baseline["nonresident_cycles_per_handoff"] + incremental_work
    row.update({
        "incremental_work_cycles": incremental_work,
        "observed_linux_over_resident_speedup":
            row["linux_cycles_per_handoff"] / row["resident_cycles_per_handoff"],
        "observed_linux_over_nonresident_speedup":
            row["linux_cycles_per_handoff"] / row["nonresident_cycles_per_handoff"],
        "additive_predicted_linux_over_resident_speedup":
            predicted_linux / predicted_resident,
        "additive_predicted_linux_over_nonresident_speedup":
            predicted_linux / predicted_nonresident,
        "linux_path_residual_percent":
            100 * (row["linux_cycles_per_handoff"] - predicted_linux) / predicted_linux,
        "resident_path_residual_percent":
            100 * (row["resident_cycles_per_handoff"] - predicted_resident) / predicted_resident,
        "nonresident_path_residual_percent":
            100 * (row["nonresident_cycles_per_handoff"] - predicted_nonresident) / predicted_nonresident,
    })

result = {
    "artifact_identity": {
        "elf_sha256": elf_hash,
        "bitstream_sha256": EXPECTED_BITSTREAM,
        "linux_shell_nbf_sha256": EXPECTED_SHELL,
    },
    "dimensions": {
        "samples_per_mode": samples,
        "warmups_per_mode": warmups,
        "round_trips_per_sample": turns,
        "timed_handoffs_per_path": samples * turns * 2 * len(rows),
        "sink": sink,
    },
    "rows": rows,
    "aggregate_sc_failures": {
        "resident_source": retries[0],
        "resident_peer": retries[1],
        "nonresident_source": retries[2],
        "nonresident_peer": retries[3],
    },
    "faults": {"minor": minor_faults, "major": major_faults},
    "additive_thresholds_incremental_work_cycles": {
        "resident_at_least_2x":
            baseline["linux_cycles_per_handoff"]
            - 2 * baseline["resident_cycles_per_handoff"],
        "nonresident_at_least_2x":
            baseline["linux_cycles_per_handoff"]
            - 2 * baseline["nonresident_cycles_per_handoff"],
        "resident_at_least_1_5x":
            2 * baseline["linux_cycles_per_handoff"]
            - 3 * baseline["resident_cycles_per_handoff"],
        "nonresident_at_least_1_5x":
            2 * baseline["linux_cycles_per_handoff"]
            - 3 * baseline["nonresident_cycles_per_handoff"],
    },
    "limits": [
        "Rows contain medians of 64 aggregate windows; the guest did not print individual window samples.",
        "Useful work is a checked dependent integer loop and does not include cache misses, faults, I/O, or blocking.",
        "The zero-work hardware rows include the shared work-call and benchmark-loop overhead, so they do not replace the isolated 17.074/22.090-cycle selector measurement.",
        "Both mechanisms run sequentially in one physical Linux boot and one ELF, but normal asynchronous Linux activity remains enabled.",
    ],
}

print(json.dumps(result, indent=2) + "")
