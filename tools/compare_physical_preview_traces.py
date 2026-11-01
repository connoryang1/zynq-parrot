#!/usr/bin/env python3
"""Compare selected instruction lines in disabled and enabled pipe traces."""

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path


HEADER_RE = re.compile(r"^TRACE_HEADER\s+(.*)$")
RECORD_RE = re.compile(r"^TRACE_RECORD\s+(.*)$")


def sha256(path):
    """Return the SHA-256 of a retained input artifact."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path):
    """Read a plain or gzip-compressed transcript."""
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", errors="replace") as stream:
            return stream.read()
    return path.read_text(errors="replace")


def fields(body):
    """Parse the recorder's bounded key=value format."""
    parsed = {}
    for item in body.split():
        key, value = item.split("=", 1)
        try:
            parsed[key] = int(value, 0)
        except ValueError:
            parsed[key] = value
    return parsed


def parse_trace(path):
    """Parse one complete, non-overflowing physical-preview trace."""
    header = None
    records = []
    outcome = None
    for raw in read_text(path).splitlines():
        line = raw.replace("\r", "")
        match = HEADER_RE.match(line)
        if match:
            header = fields(match.group(1))
            continue
        match = RECORD_RE.match(line)
        if match:
            records.append(fields(match.group(1)))
            continue
        if line.startswith("TRACE_PASS") or line.startswith("TRACE_FAIL"):
            outcome = line.split()[0]
    if header is None:
        raise ValueError(f"{path}: no TRACE_HEADER")
    expected = header["i_count"] + header["d_count"]
    if outcome != "TRACE_PASS":
        raise ValueError(f"{path}: trace did not pass")
    if header["i_overflow"] or header["d_overflow"] or header["armed"]:
        raise ValueError(f"{path}: invalid final recorder status")
    if len(records) != expected:
        raise ValueError(
            f"{path}: parsed {len(records)} records, expected {expected}"
        )
    return {"header": header, "records": records}


def occurrences(trace, paddr):
    """Return I-side occurrences of one physical line."""
    return [
        {"sequence": record["seq"], "relative_cycle": record["relative"]}
        for record in trace["records"]
        if record["side"] == "I" and record["paddr"] == paddr
    ]


def summarize(path, trace):
    """Summarize exact identity, timing, and record counts for one trace."""
    header = trace["header"]
    iaddresses = [
        record["paddr"] for record in trace["records"]
        if record["side"] == "I"
    ]
    return {
        "path": str(path),
        "sha256": sha256(path),
        "wake_to_entry": header["wake_to_entry"],
        "load_cycles": header["load_cycles"],
        "wake_to_load": header["wake_to_load"],
        "i_count": header["i_count"],
        "d_count": header["d_count"],
        "unique_i_lines": len(set(iaddresses)),
    }


def compare(disabled_path, enabled_path, selection_path):
    """Compare every selected prefix line across two accepted traces."""
    disabled = parse_trace(disabled_path)
    enabled = parse_trace(enabled_path)
    selection = json.loads(Path(selection_path).read_text())
    selected = selection["fixed_shared_prefix"]["lines"]
    results = []
    for line in selected:
        paddr = line["paddr"]
        results.append({
            "rank": line["rank"],
            "paddr": f"0x{paddr:09x}",
            "disabled_occurrences": occurrences(disabled, paddr),
            "enabled_occurrences": occurrences(enabled, paddr),
        })
    disabled_present = sum(bool(row["disabled_occurrences"]) for row in results)
    enabled_present = sum(bool(row["enabled_occurrences"]) for row in results)
    return {
        "purpose": (
            "Determine whether the exact configured instruction-prefix lines "
            "remain architectural demand misses when replay is enabled."
        ),
        "selection": {
            "path": str(selection_path),
            "sha256": sha256(selection_path),
            "line_count": len(results),
        },
        "disabled": summarize(disabled_path, disabled),
        "enabled": summarize(enabled_path, enabled),
        "selected_summary": {
            "present_as_demand_miss_disabled": disabled_present,
            "present_as_demand_miss_enabled": enabled_present,
            "removed_from_demand_stream": sum(
                bool(row["disabled_occurrences"])
                and not row["enabled_occurrences"]
                for row in results
            ),
            "all_selected_present_disabled": disabled_present == len(results),
            "all_selected_absent_enabled": enabled_present == 0,
        },
        "selected_lines": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disabled", type=Path)
    parser.add_argument("enabled", type=Path)
    parser.add_argument("selection", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(compare(args.disabled, args.enabled, args.selection), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
