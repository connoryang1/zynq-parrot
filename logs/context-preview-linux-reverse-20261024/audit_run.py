#!/usr/bin/env python3
"""Audit phase timing and completion markers from the physical Linux oracle."""

import hashlib
import json
import re
import statistics
from pathlib import Path

here = Path(__file__).resolve().parent
log_bytes = (here / "board.log").read_bytes()
log = log_bytes.decode(errors="replace").replace("\r", "")
binary_sha = "23b0e1622a63faa7247b7e97d1cf51a238c5bfdcf3a0e97817ad8e595e128e8f"
pattern = (
    r"^CONTEXT_PREVIEW mode=(\d+) repeat=(\d+) total=(\d+) "
    r"preview=(\d+) work=(\d+) wake=(\d+) peer_entry=(\d+) "
    r"peer_load=(\d+) cpu=(\d+)$"
)
rows = [tuple(map(int, match)) for match in re.findall(pattern, log, re.M)]
loads = [tuple(map(int, match)) for match in re.findall(
    r"^PREVIEW_LOADS mode=(\d+) repeat=(\d+) "
    r"l0=(\d+) l1=(\d+) l2=(\d+) l3=(\d+)$", log, re.M)]
assert len(rows) == 112, len(rows)
assert len(loads) == 112, len(loads)
assert {(row[0], row[1]) for row in loads} == {(row[0], row[1]) for row in rows}
load_map = {(row[0], row[1]): row for row in loads}
assert all(sum(load_map[row[:2]][2:]) == row[7] for row in rows)
assert {(row[0], row[1]) for row in rows} == {
    (mode, repeat) for mode in range(7) for repeat in range(16)
}
assert {row[8] for row in rows} == {0}
assert all(0 <= row[3] <= row[4] <= row[2] and row[6] + row[7] <= row[2]
           for row in rows)
assert f"{binary_sha}  /tmp/context_preview_oracle_dynamic" in log
for marker in (
    "CONTEXT_PREVIEW PASS\n", "CONTEXT_PREVIEW_EXIT=0\n",
    "~ # poweroff -f\n", "reboot: Power down",
    "INFO:    CORE PASS\n", "INFO:    BSG PASS\n",
    "Returning from ps_main with RC: 0",
):
    assert marker in log, marker
status = json.loads((here / "board-status.json").read_text())
assert status["status"] == "PASS" and status["runner_exit"] == 0
assert status["binary_sha256"] == binary_sha
assert status["result_rows"] == 112 and not status["recovery_required"]

fields = {"total": 2, "preview": 3, "work": 4, "wake": 5,
          "peer_entry": 6, "peer_load": 7}
modes = {}
for mode in range(7):
    selected = sorted((row for row in rows if row[0] == mode), key=lambda row: row[1])
    values = {name: [row[index] for row in selected]
              for name, index in fields.items()}
    values["peer_done"] = [row[6] + row[7] for row in selected]
    line_values = [[load_map[row[:2]][line + 2] for row in selected]
                   for line in range(4)]
    modes[str(mode)] = {
        "line_cycles": line_values,
        "median_line_cycles": [statistics.median(values) for values in line_values],
        "fast_line_counts_at_15_cycles": [sum(value <= 15 for value in values)
                                          for values in line_values],
        "rows": values,
        "medians": {name: statistics.median(samples)
                    for name, samples in values.items()},
        "wake_after_peer_entry_count": sum(row[5] > row[6] for row in selected),
    }

result = {
    "status": "PASS", "row_count": len(rows), "cpu": 0,
    "binary_sha256": binary_sha,
    "board_log_sha256": hashlib.sha256(log_bytes).hexdigest(),
    "linux_nbf_sha256": status["linux_nbf_sha256"],
    "bit_sha256": status["bit_sha256"],
    "modes": modes,
}
(here / "validated-status.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"status": result["status"],
                  "medians": {mode: data["medians"] for mode, data in modes.items()}}, indent=2))
