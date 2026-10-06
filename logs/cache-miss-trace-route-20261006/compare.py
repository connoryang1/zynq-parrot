#!/usr/bin/env python3
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
JOBS = {
    "lut_ram": "20261006T173322Z-6da84fc6",
    "block_ram": "20261006T182248Z-e860ceea",
}


def parse(job):
    job_dir = ROOT / "logs" / "fpga" / job
    summary = (job_dir / "summary.txt").read_text()
    revisions = dict(
        line.split("=", 1)
        for line in (job_dir / "revisions.txt").read_text().splitlines()
        if "=" in line
    )

    def one(pattern, cast=float):
        match = re.search(pattern, summary, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {pattern!r} in {job}/summary.txt")
        return cast(match.group(1))

    timing = re.search(
        r"^\s+([0-9.-]+)\s+([0-9.-]+)\s+\d+\s+\d+\s+"
        r"([0-9.-]+)\s+([0-9.-]+)\s+\d+\s+\d+\s+",
        summary,
        re.MULTILINE,
    )
    if not timing:
        raise RuntimeError(f"missing timing row in {job}/summary.txt")

    return {
        "job": job,
        "top_commit": revisions["top_commit"],
        "black_parrot_commit": revisions["black_parrot_commit"],
        "slice_luts": one(r"^\| Slice LUTs\s+\|\s+(\d+)", int),
        "slice_lut_percent": one(r"^\| Slice LUTs\s+\|.*\|\s+([0-9.]+)\s+\|$"),
        "slice_registers": one(r"^\| Slice Registers\s+\|\s+(\d+)", int),
        "bram_tiles": one(r"^\| Block RAM Tile\s+\|\s+([0-9.]+)"),
        "wns_ns": float(timing.group(1)),
        "tns_ns": float(timing.group(2)),
        "whs_ns": float(timing.group(3)),
        "ths_ns": float(timing.group(4)),
    }


before = parse(JOBS["lut_ram"])
after = parse(JOBS["block_ram"])
result = {
    "before": before,
    "after": after,
    "delta_after_minus_before": {
        "slice_luts": after["slice_luts"] - before["slice_luts"],
        "slice_lut_percentage_points": round(
            after["slice_lut_percent"] - before["slice_lut_percent"], 2
        ),
        "slice_registers": after["slice_registers"] - before["slice_registers"],
        "bram_tiles": after["bram_tiles"] - before["bram_tiles"],
        "wns_ns": round(after["wns_ns"] - before["wns_ns"], 3),
        "whs_ns": round(after["whs_ns"] - before["whs_ns"], 3),
    },
}
print(json.dumps(result, indent=2, sort_keys=True))
