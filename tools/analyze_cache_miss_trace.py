#!/usr/bin/env python3
"""Summarize cache-miss recorder output from cache_miss_trace_capture."""

import argparse
import collections
import json
import re
from pathlib import Path


HEADER_RE = re.compile(r"^TRACE_HEADER\s+(.*)$")
RECORD_RE = re.compile(r"^TRACE_RECORD\s+(.*)$")


def fields(text):
    result = {}
    for item in text.split():
        key, value = item.split("=", 1)
        result[key] = int(value, 0) if key not in {"side"} else value
    return result


def percentile(values, numerator, denominator):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) * numerator + denominator - 1) // denominator - 1
    return ordered[max(0, index)]


def analyze(path):
    header = None
    records = []
    outcome = None
    for raw in Path(path).read_text(errors="replace").splitlines():
        line = raw.replace("\r", "")
        match = HEADER_RE.match(line)
        if match:
            header = fields(match.group(1))
            continue
        match = RECORD_RE.match(line)
        if match:
            records.append(fields(match.group(1)))
            continue
        if line.startswith("TRACE_PASS") or line.startswith("TRACE_TRUNCATED"):
            outcome = line.split()[0]
    if header is None:
        raise ValueError(f"{path}: no TRACE_HEADER")

    window = header.get("window", 0)
    source_to_peer = header["peer_begin"] - header["start"]
    peer_to_source = header["resume"] - header["peer_begin"]
    boundaries = {
        "source_to_peer": source_to_peer,
        "peer_to_source": peer_to_source,
    }
    if window == 1:
        phase_ends = [("source_to_peer", header["elapsed"])]
    elif window == 2:
        phase_ends = [("peer_to_source", header["elapsed"])]
    else:
        # peer_block is observed after FUTEX_WAKE returns. Linux may dispatch
        # the source inside that syscall, making peer_block later than resume.
        phase_ends = [
            ("source_to_peer", source_to_peer),
            ("peer_to_source", header["elapsed"]),
        ]
    phase_counts = {name: {"I": 0, "D": 0} for name, _ in phase_ends}
    unassigned_counts = {"I": 0, "D": 0}
    by_side = {}
    for side in ("I", "D"):
        selected = [record for record in records if record["side"] == side]
        addresses = [record["paddr"] for record in selected]
        gaps = [
            selected[index]["relative"] - selected[index - 1]["relative"]
            for index in range(1, len(selected))
        ]
        counts = collections.Counter(addresses)
        by_side[side] = {
            "records": len(selected),
            "unique_lines": len(counts),
            "repeated_records": len(selected) - len(counts),
            "first_cycle": selected[0]["relative"] if selected else None,
            "last_cycle": selected[-1]["relative"] if selected else None,
            "median_interarrival": percentile(gaps, 1, 2),
            "p95_interarrival": percentile(gaps, 95, 100),
            "max_interarrival": max(gaps) if gaps else None,
            "most_repeated": [
                {"paddr": f"0x{address:09x}", "count": count}
                for address, count in counts.most_common(8)
                if count > 1
            ],
        }

    for record in records:
        previous = 0
        assigned = False
        for name, end in phase_ends:
            if previous <= record["relative"] <= end:
                phase_counts[name][record["side"]] += 1
                assigned = True
                break
            previous = end + 1
        if not assigned:
            unassigned_counts[record["side"]] += 1

    expected = header["i_count"] + header["d_count"]
    return {
        "path": str(path),
        "outcome": outcome,
        "window": window,
        "elapsed_cycles": header["elapsed"],
        "phase_cycles": boundaries,
        "status": {
            key: header[key]
            for key in ("i_count", "d_count", "i_overflow", "d_overflow", "armed")
        },
        "records_parsed": len(records),
        "records_expected": expected,
        "record_count_matches": len(records) == expected,
        "phase_record_counts": phase_counts,
        "unassigned_record_counts": unassigned_counts,
        "by_side": by_side,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+")
    args = parser.parse_args()
    print(json.dumps([analyze(path) for path in args.logs], indent=2))


if __name__ == "__main__":
    main()
