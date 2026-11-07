#!/usr/bin/env python3
"""Select stable post-hint return-path instruction lines across board traces."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path

from analyze_tagged_icache_trace_pair import IDENTITY_KEYS, load_trace


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_excluded_prefix(path):
    document = json.loads(path.read_text())
    lines = document.get("fixed_shared_prefix", {}).get("lines", [])
    excluded = {
        int(line.get("paddr_hex", line.get("paddr")), 0)
        if isinstance(line.get("paddr_hex", line.get("paddr")), str)
        else line.get("paddr_hex", line.get("paddr"))
        for line in lines
    }
    if not excluded or None in excluded or any(line & 63 for line in excluded):
        raise ValueError("excluded prefix is empty, malformed, or unaligned")
    return excluded


def select(paths, excluded_prefix_path, limit, allow_truncated=False,
           anchor_paddr=None):
    if len(paths) < 3:
        raise ValueError("return selection requires at least three traces")
    if not 1 <= limit <= 256:
        raise ValueError("invalid selection limit")
    if anchor_paddr is not None and anchor_paddr & 63:
        raise ValueError("return anchor is not cache-line aligned")
    traces = [
        load_trace(
            path, "instruction-explicit-roundtrip", 0, 0, "return"
        )
        for path in paths
    ]
    reference = traces[0]["status"]
    for trace in traces:
        if trace["truncated"] and not allow_truncated:
            raise ValueError(f"return trace is truncated: {trace['path']}")
        if trace["return_hint"] is None:
            raise ValueError(f"return hint boundary is absent: {trace['path']}")
        for key in IDENTITY_KEYS:
            if trace["status"].get(key) != reference.get(key):
                raise ValueError(f"return trace identity mismatch: {key}")

    excluded = load_excluded_prefix(excluded_prefix_path)
    first_by_trace = []
    anchor_relatives = []
    for trace in traces:
        hint_end = trace["return_hint"]["end_relative"]
        anchor_relative = None
        if anchor_paddr is not None:
            anchor_relative = next(
                (record["relative"] for record in trace["records"]
                 if (record["paddr"] & ~63) == anchor_paddr),
                None,
            )
            if anchor_relative is None:
                raise ValueError(
                    f"return anchor 0x{anchor_paddr:016x} is absent: "
                    f"{trace['path']}"
                )
        anchor_relatives.append(anchor_relative)
        boundary = max(hint_end, anchor_relative or hint_end)
        first = {}
        for record in trace["records"]:
            address = record["paddr"] & ~63
            if record["relative"] >= boundary and address not in excluded:
                first.setdefault(address, record["relative"])
        first_by_trace.append(first)
    common = set(first_by_trace[0])
    for first in first_by_trace[1:]:
        common &= set(first)

    boundaries = [
        max(trace["return_hint"]["end_relative"], anchor or 0)
        for trace, anchor in zip(traces, anchor_relatives)
    ]
    ranked = []
    for address in common:
        relatives = [first[address] for first in first_by_trace]
        after_hint = [
            relative - boundary
            for relative, boundary in zip(relatives, boundaries)
        ]
        ranked.append((max(after_hint), statistics.median(after_hint),
                       address, relatives, after_hint))
    ranked.sort()
    if len(ranked) < limit:
        raise ValueError(
            f"only {len(ranked)} stable post-hint reverse-only lines are available"
        )

    selected = ranked[:limit]
    return {
        "purpose": (
            "Select reverse-path instruction lines observed after the matched "
            "return hint completes in every complete disabled board trace."
        ),
        "input_identity": {
            "traces": [
                {
                    "transcript": str(path),
                    "transcript_sha256": trace["sha256"],
                    "status_sha256": trace["status_sha256"],
                    "record_count": trace["record_count"],
                    "unique_lines": trace["unique_lines"],
                    "truncated": trace["truncated"],
                    "data_truncated": trace["data_truncated"],
                    "hint_end_relative": trace["return_hint"]["end_relative"],
                }
                for path, trace in zip(paths, traces)
            ],
            **{key: reference.get(key) for key in IDENTITY_KEYS},
            "excluded_prefix": str(excluded_prefix_path),
            "excluded_prefix_sha256": sha256(excluded_prefix_path),
        },
        "selection": {
            "trace_count": len(traces),
            "excluded_line_count": len(excluded),
            "stable_reverse_only_lines_available": len(ranked),
            "selected_lines": limit,
            "truncated_prefixes_allowed": allow_truncated,
            "anchor_paddr": anchor_paddr,
            "anchor_paddr_hex": (
                f"0x{anchor_paddr:016x}" if anchor_paddr is not None else None
            ),
            "trace_anchor_relatives": anchor_relatives,
            "trace_selection_floor_relatives": boundaries,
            "policy": (
                "intersect first occurrences at or after each trace's "
                + ("aligned return anchor" if anchor_paddr is not None else
                   "return-hint completion")
                + ", exclude the installed forward prefix, then "
                "rank by the latest per-trace distance after that selection floor"
            ),
        },
        "fixed_shared_prefix": {
            "line_count": limit,
            "lines": [
                {
                    "rank": rank,
                    "paddr": address,
                    "paddr_hex": f"0x{address:016x}",
                    "trace_first_relatives": relatives,
                    "trace_relative_to_selection_floor": after_hint,
                    "worst_relative_to_selection_floor": worst,
                    "median_relative_to_selection_floor": median,
                    "cache_set": (address // 64) % 64,
                }
                for rank, (worst, median, address, relatives, after_hint)
                in enumerate(selected)
            ],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", nargs="+", type=Path)
    parser.add_argument("--exclude-prefix", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument(
        "--allow-truncated-prefixes", action="store_true",
        help=(
            "allow retained first-256 I-miss prefixes for positive "
            "intersection only"
        ),
    )
    parser.add_argument(
        "--anchor-paddr", type=lambda value: int(value, 0),
        help="align selection on this cache-line physical switch boundary",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = select(
        args.trace, args.exclude_prefix, args.limit,
        args.allow_truncated_prefixes, args.anchor_paddr,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"wrote {args.output} with "
        f"{result['fixed_shared_prefix']['line_count']} stable lines"
    )


if __name__ == "__main__":
    main()
