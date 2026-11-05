#!/usr/bin/env python3
"""Generate the peer-review Nano result tables from qualified transcripts."""

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
ROW = re.compile(
    r"Benchmark: NANO_LOOKUP mode=0x(?P<mode>[0-9a-f]+) "
    r"queries=0x(?P<workers>[0-9a-f]+) levels=0x(?P<levels>[0-9a-f]+) "
    r"cycles=0x(?P<cycles>[0-9a-f]+) checksum=0x(?P<checksum>[0-9a-f]+)",
    re.IGNORECASE,
)
NAME = re.compile(
    r"(?P<opt>o[23])-m(?P<mode>\d+)-n(?P<workers>\d+)"
    r"(?P<repeat>-r\d+)?\.log$"
)


def parse(path):
    name = NAME.fullmatch(path.name)
    if not name:
        return None
    text = path.read_text(errors="replace")
    rows = list(ROW.finditer(text))
    if len(rows) != 1:
        raise SystemExit(f"{path}: expected one Nano result, found {len(rows)}")
    if "[BSG-PASS] Nano-style binary index lookups" not in text:
        raise SystemExit(f"{path}: missing guest PASS")
    if "BSG-INFO:    CORE PASS" not in text or "BSG-INFO:    BSG PASS" not in text:
        raise SystemExit(f"{path}: missing host/core PASS")
    actual = {key: int(value, 16) for key, value in rows[0].groupdict().items()}
    expected_mode = int(name["mode"])
    expected_workers = int(name["workers"])
    if (actual["mode"], actual["workers"]) != (expected_mode, expected_workers):
        raise SystemExit(f"{path}: filename/result selector mismatch")
    return {
        "optimization": name["opt"].upper(),
        "mode": expected_mode,
        "workers": expected_workers,
        "repeat": name["repeat"].lstrip("-") if name["repeat"] else "r1",
        "cycles": actual["cycles"],
        "useful_nodes": expected_workers * actual["levels"],
        "cycles_per_node": actual["cycles"] / (expected_workers * actual["levels"]),
        "checksum": f"0x{actual['checksum']:x}",
        "status": "pass",
        "transcript": f"runs/{path.name}",
    }


rows = [row for path in sorted(RUNS.glob("o[23]-m*-n*.log")) if (row := parse(path))]
if len(rows) != 34:
    raise SystemExit(f"expected 34 qualified Nano transcripts, found {len(rows)}")

fields = list(rows[0])
with (ROOT / "results.csv").open("w", newline="") as output:
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

main = {(row["optimization"], row["mode"], row["workers"], row["repeat"]): row
        for row in rows}
with (ROOT / "sweep.csv").open("w", newline="") as output:
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("workers", "hardware_cycles", "batch_cycles", "batch_over_hardware"))
    for workers in range(2, 11):
        hardware = main[("O3", 2, workers, "r1")]["cycles"]
        batch = main[("O3", 7, workers, "r1")]["cycles"]
        writer.writerow((workers, hardware, batch, f"{batch / hardware:.6f}"))

for mode, expected in ((2, 2810), (7, 3817)):
    repeats = [main[("O3", mode, 8, repeat)]["cycles"] for repeat in ("r1", "r2", "r3")]
    if repeats != [expected] * 3:
        raise SystemExit(f"mode {mode}: repeatability check failed: {repeats}")

print(f"wrote {len(rows)} rows; N=8 batch/hardware={3817 / 2810:.6f}x")
