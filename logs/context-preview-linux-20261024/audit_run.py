#!/usr/bin/env python3
"""Audit the complete physical Linux run after the runner's marker mismatch."""

import hashlib
import json
import re
import statistics
from pathlib import Path

here = Path(__file__).resolve().parent
raw = (here / "board.log").read_text(errors="replace").replace("\r", "")
binary_sha = "eb48c980c0a4926a4b15df180e08d2c9d015d79fa8cd16f82d04a576091cb6df"
rows = [tuple(map(int, match)) for match in re.findall(
    r"^CONTEXT_PREVIEW mode=(\d+) repeat=(\d+) total=(\d+) "
    r"peer_load=(\d+) cpu=(\d+)$", raw, re.M)]
assert len(rows) == 32, len(rows)
assert {(mode, repeat) for mode, repeat, *_ in rows} == {
    (mode, repeat) for mode in range(4) for repeat in range(8)
}
assert len({cpu for *_, cpu in rows}) == 1
assert f"{binary_sha}  /tmp/context_preview_oracle_dynamic" in raw
assert "CONTEXT_PREVIEW PASS\n" in raw
assert "CONTEXT_PREVIEW_EXIT=0\n" in raw
assert "~ # poweroff -f\n" in raw
assert "reboot: Power down" in raw
assert "INFO:    CORE PASS\n" in raw
assert "INFO:    BSG PASS\n" in raw
assert (here / "runner.status").read_text().strip() == "RUNNER_EXIT=0"

summary = {}
for mode in range(4):
    selected = sorted((row for row in rows if row[0] == mode), key=lambda row: row[1])
    summary[str(mode)] = {
        "total_cycles": [row[2] for row in selected],
        "peer_load_cycles": [row[3] for row in selected],
        "median_total_cycles": statistics.median(row[2] for row in selected),
        "median_peer_load_cycles": statistics.median(row[3] for row in selected),
    }

result = {
    "status": "PASS_POSTHOC",
    "reason_for_original_runner_failure": "host prints CORE PASS, not CORE[0] PASS",
    "binary_sha256": binary_sha,
    "board_log_sha256": hashlib.sha256((here / "board.log").read_bytes()).hexdigest(),
    "row_count": len(rows),
    "cpu": rows[0][4],
    "guest_pass": True,
    "application_exit": 0,
    "core_pass": True,
    "host_pass": True,
    "runner_exit": 0,
    "clean_poweroff": True,
    "modes": summary,
}
(here / "validated-status.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"status": result["status"], "row_count": len(rows), "modes": summary}, indent=2))
