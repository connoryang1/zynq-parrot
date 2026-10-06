#!/usr/bin/env python3
"""Summarize the retained physical cache-miss recorder runs."""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
SIM_LOG = ROOT.parent / "cache-miss-trace-sim-20261006" / "run.log"
TRACE_RE = re.compile(
    r"MISS-TRACE i-count=0x([0-9a-f]+) d-count=0x([0-9a-f]+) "
    r"i-cycle=0x([0-9a-f]+) d-cycle=0x([0-9a-f]+)"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_trace(path: Path, *, physical: bool) -> dict[str, int | str | bool]:
    text = path.read_text(errors="replace")
    matches = TRACE_RE.findall(text)
    if len(matches) != 1:
        raise ValueError(f"{path}: expected one MISS-TRACE row, found {len(matches)}")
    i_count, d_count, i_cycle, d_cycle = (int(value, 16) for value in matches[0])
    try:
        display_path = path.relative_to(ROOT)
    except ValueError:
        display_path = path.relative_to(ROOT.parent)
    result = {
        "path": str(display_path),
        "sha256": sha256(path),
        "i_count": i_count,
        "d_count": d_count,
        "i_cycle": i_cycle,
        "d_cycle": d_cycle,
        "i_to_d_cycles": d_cycle - i_cycle,
        "trace_pass": text.count("[BSG-PASS] accepted cache-miss trace") == 1,
        "core_pass": text.count("CORE PASS") == 1,
        "runner_rc_zero": (
            text.count("Returning from ps_main with RC: 0") == 1
            if physical
            else "BSG PASS" in text
        ),
    }
    if physical:
        result["allocation_bytes"] = 16 * 1024 * 1024
        result["first_8_mib_only"] = (
            "00000000000000000000000000000001" in text
        )
    if not all(
        result[key]
        for key in ("trace_pass", "core_pass", "runner_rc_zero")
    ):
        raise ValueError(f"{path}: missing a required success marker")
    if physical and not result["first_8_mib_only"]:
        raise ValueError(f"{path}: unexpected DRAM usage mask")
    return result


board_logs = [RAW / "mt_cache_miss_trace_test-physical-16m-20261006.log"]
board_logs += sorted((RAW / "cache-miss-trace-series-20261006").glob("sample-*.log"))
board = [parse_trace(path, physical=True) for path in board_logs]
sim = parse_trace(SIM_LOG, physical=False)

deltas = [int(row["i_to_d_cycles"]) for row in board]
if not all(row["i_count"] == 2 and row["d_count"] == 1 for row in board):
    raise ValueError("physical trace counts are not uniformly 2 I / 1 D")
if len(set(deltas)) != 1:
    raise ValueError(f"physical I-to-D interval is not deterministic: {deltas}")

failure_log = RAW / "mt_cache_miss_trace_test-physical-20261006.log"
failure_text = failure_log.read_text(errors="replace")
if "allocating owned DRAM buffer with size 67108864" not in failure_text:
    raise ValueError("missing the rejected 64 MiB allocation attempt")
if "virtual_ptr != NULL" not in failure_text:
    raise ValueError("missing the rejected allocation assertion")

manifest = {
    str(path.relative_to(ROOT)): sha256(path)
    for path in sorted(RAW.rglob("*"))
    if path.is_file()
}
manifest["board-evidence.tar.gz"] = sha256(ROOT / "board-evidence.tar.gz")
with tarfile.open(ROOT / "board-evidence.tar.gz", "r:gz") as archive:
    archive_manifest = {
        member.name: hashlib.sha256(archive.extractfile(member).read()).hexdigest()
        for member in archive.getmembers()
        if member.isfile()
    }

result = {
    "artifact_identity": {
        "top_commit": "e860ceea",
        "black_parrot_commit": "52c5dde701263b4a476fc87ae0c37afb9721cfcb",
        "bitstream_sha256": "f4a183d8f900170ce5a6eb59366d56609cbe0f492063ea5a41b791d807306c5a",
        "nbf_sha256": "e30d602e3b857ec99f6248f16390e53ae4ce5cc4ac5c27b7f17249dbe2bb8353",
        "original_runner_sha256": "912362b0639b2fafdce3b6ba256cf004c2702a50f1db72207146ece7cd06386d",
        "measurement_runner_sha256": "3b76dbb4a3ce23dda0666e73131446e3a2de77662a369749f3315f428f0d6def",
    },
    "physical": {
        "successful_samples": len(board),
        "all_trace_and_core_pass": True,
        "all_i_count": 2,
        "all_d_count": 1,
        "i_to_d_cycles": {
            "min": min(deltas),
            "median": sorted(deltas)[len(deltas) // 2],
            "max": max(deltas),
            "all": deltas,
        },
        "runs": board,
    },
    "simulation": sim,
    "comparison": {
        "physical_i_to_d_cycles": deltas[0],
        "simulation_i_to_d_cycles": sim["i_to_d_cycles"],
        "physical_minus_simulation_cycles": deltas[0] - int(sim["i_to_d_cycles"]),
    },
    "rejected_preflight": {
        "reason": "64 MiB CMA allocation failed before NBF load or guest start",
        "requested_bytes": 64 * 1024 * 1024,
        "kernel_cma_total_kib": 131072,
        "kernel_cma_free_kib": 118492,
        "kernel_error": "cma_alloc: alloc failed, req-size: 16384 pages, ret: -16",
        "log_sha256": sha256(failure_log),
        "runner_exit": 137,
        "excluded_from_measurements": True,
    },
    "manifest_sha256": manifest,
    "board_archive_member_sha256": archive_manifest,
}

(ROOT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result["physical"], indent=2))
print(json.dumps(result["comparison"], indent=2))
