#!/usr/bin/env python3
from pathlib import Path
import argparse
import hashlib
import json
import re
import statistics

parser = argparse.ArgumentParser()
parser.add_argument("logs", nargs="+", type=Path)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()


def fields(line):
    return {name: int(value, 16) for name, value in
            re.findall(r"(\w+)=(0x[0-9a-fA-F]+)", line)}


records = []
for path in args.logs:
    text = path.read_text(errors="replace")
    summaries = [fields(line) for line in text.splitlines()
                 if line.startswith("DDR_SECTOR_SUMMARY ")]
    samples = [fields(line) for line in text.splitlines()
               if line.startswith("DDR_SECTOR sample=")]
    samples = [sample for sample in samples
               if {"sample", "first", "adjacent"} <= sample.keys()]
    core_passes = len(re.findall(r"\bCORE(?:\[\d+\])?\s+PASS\b", text))
    host_passes = len(re.findall(r"\bBSG PASS\b", text))
    guest_passes = text.count(
        "[BSG-PASS] DDR dependent-load latency and prefetch lead sweep")
    assert summaries and core_passes and host_passes and guest_passes, path
    assert not re.search(
        r"BSG-FAIL|CORE(?:\[\d+\])?\s+FAIL|runtime limit|unexpected trap",
        text, re.I), path
    row = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "guest_passes": guest_passes,
        "core_passes": core_passes,
        "host_passes": host_passes,
        "summaries": summaries,
        "complete_sample_rows": len(samples),
    }
    if samples:
        first = [sample["first"] for sample in samples]
        adjacent = [sample["adjacent"] for sample in samples]
        row["complete_rows_first"] = {
            "median": statistics.median(first), "min": min(first),
            "max": max(first),
        }
        row["complete_rows_adjacent"] = {
            "median": statistics.median(adjacent), "min": min(adjacent),
            "max": max(adjacent),
        }
    records.append(row)

args.output.write_text(json.dumps(records, indent=2) + "\n")
