#!/usr/bin/env python3
"""Compare matched replay-off/on entry-bounded instruction-miss traces."""

import argparse
import hashlib
import json
import re
from pathlib import Path


HEADER = re.compile(
    r"^TAGGED_REPLAY_ITRACE_HEADER trial=(\d+) enabled=(\d+) "
    r"i_count=(\d+) d_count=(\d+) i_overflow=(\d+) d_overflow=(\d+) "
    r"armed=(\d+) status=0x([0-9a-fA-F]{16})$", re.MULTILINE
)
RECORD = re.compile(
    r"^TAGGED_REPLAY_ITRACE_RECORD index=(\d+) relative=(\d+) "
    r"paddr=0x([0-9a-fA-F]+) raw=0x([0-9a-fA-F]{16})$", re.MULTILINE
)
PREFIX_PASS = re.compile(
    r"^TAGGED_REPLAY_ITRACE_PREFIX_PASS truncated=(\d+) records=(\d+)$",
    re.MULTILINE,
)
RETURN_HINT = re.compile(
    r"^TAGGED_REPLAY_RETURN_HINT trial=(\d+) enabled=(\d+) "
    r"begin_relative=(\d+) end_relative=(\d+)$", re.MULTILINE
)
ROW = re.compile(
    r"^TAGGED_REPLAY trial=(\d+) enabled=(\d+).* "
    r"wake_to_entry=(\d+) load_cycles=(\d+) wake_to_load=(\d+) "
    r"roundtrip=(\d+)", re.MULTILINE
)
IDENTITY_KEYS = (
    "nbf_sha256", "transfer_sha256", "elf_sha256",
    "control_program_sha256", "bitstream_sha256",
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_trace(path, expected_mode, expected_enabled, expected_trial=1,
               expected_window="entry"):
    status_path = path.with_suffix(path.suffix + ".status.json")
    if not status_path.is_file():
        raise ValueError(f"missing status for {path}")
    status = json.loads(status_path.read_text())
    if status.get("status") != "PASS" or status.get("mode") != expected_mode:
        raise ValueError(f"unexpected runner status or mode for {path}")
    entry_capture = (status.get("trace_icache_entry_prefix")
                     or status.get("trace_icache_entry_prefix_off"))
    return_capture = (status.get("trace_icache_return_prefix")
                      or status.get("trace_icache_return_prefix_off"))
    if ((expected_window == "entry" and not entry_capture)
            or (expected_window == "return" and not return_capture)
            or (expected_window not in ("entry", "return"))):
        raise ValueError(
            f"trace is not an {expected_window}-prefix capture: {path}"
        )

    text = path.read_text(errors="replace").replace("\r", "")
    headers = HEADER.findall(text)
    passes = PREFIX_PASS.findall(text)
    if len(headers) != 1 or len(passes) != 1:
        raise ValueError(f"expected one trace header and prefix PASS in {path}")
    trial, enabled, icount, dcount, ioverflow, doverflow, armed, raw = headers[0]
    del raw
    trial, enabled = int(trial), int(enabled)
    icount, dcount = int(icount), int(dcount)
    ioverflow, doverflow, armed = int(ioverflow), int(doverflow), int(armed)
    truncated, pass_count = map(int, passes[0])
    if trial != expected_trial or enabled != expected_enabled:
        raise ValueError(f"trace trial/arm mismatch in {path}")
    if armed or not icount or icount > 256 or dcount > 256:
        raise ValueError(f"invalid recorder status in {path}")
    if ioverflow and icount != 256:
        raise ValueError(f"overflowed trace did not retain 256 records in {path}")
    if truncated != ioverflow or pass_count != icount:
        raise ValueError(f"prefix PASS does not match recorder status in {path}")

    matches = RECORD.findall(text)
    if (len(matches) != icount
            or [int(match[0]) for match in matches] != list(range(icount))):
        raise ValueError(f"trace records are incomplete or unordered in {path}")
    records = [
        {"index": int(index), "relative": int(relative),
         "paddr": int(paddr, 16), "raw": int(raw_record, 16)}
        for index, relative, paddr, raw_record in matches
    ]
    hint_matches = RETURN_HINT.findall(text)
    if len(hint_matches) > 1:
        raise ValueError(f"multiple return hint boundaries in {path}")
    return_hint = None
    if hint_matches:
        hint_trial, hint_enabled, hint_begin, hint_end = map(
            int, hint_matches[0]
        )
        if (hint_trial != expected_trial or hint_enabled != expected_enabled
                or hint_begin > hint_end):
            raise ValueError(f"invalid return hint boundary in {path}")
        return_hint = {
            "begin_relative": hint_begin,
            "end_relative": hint_end,
        }
    rows = [tuple(map(int, match)) for match in ROW.findall(text)]
    row = next((match for match in rows if match[0] == expected_trial), None)
    if row is None or row[1] != expected_enabled:
        raise ValueError(f"missing measured trace row in {path}")
    return {
        "path": str(path),
        "sha256": sha256(path),
        "status_path": str(status_path),
        "status_sha256": sha256(status_path),
        "status": status,
        "record_count": icount,
        "unique_lines": len({record["paddr"] for record in records}),
        "repeated_events": icount - len({record["paddr"] for record in records}),
        "truncated": bool(ioverflow),
        "data_truncated": bool(doverflow),
        "last_relative": records[-1]["relative"],
        "return_hint": return_hint,
        "records": records,
        "timing": {
            "wake_to_entry": row[2],
            "load_cycles": row[3],
            "wake_to_load": row[4],
            "roundtrip": row[5],
        },
        "window": expected_window,
    }


def configured_summary(trace, prefix_lines):
    by_line = {}
    for record in trace["records"]:
        by_line.setdefault(record["paddr"], []).append(record["relative"])
    present = [line for line in prefix_lines if line in by_line]
    return {
        "distinct_lines": len(present),
        "events": sum(len(by_line[line]) for line in present),
        "lines": [
            {"paddr": line, "paddr_hex": f"0x{line:016x}",
             "relatives": by_line.get(line, [])}
            for line in prefix_lines
        ],
    }


def configured_absence_coverage(off, on, off_configured):
    """Report whether the retained replay-on prefix reaches the control horizon."""
    off_relatives = [
        relative
        for line in off_configured["lines"]
        for relative in line["relatives"]
    ]
    latest_off = max(off_relatives) if off_relatives else None
    return {
        "latest_replay_off_configured_relative": latest_off,
        "replay_on_last_relative": on["last_relative"],
        "replay_on_is_complete": not on["truncated"],
        "retained_on_prefix_reaches_off_configured_horizon": (
            latest_off is None or on["last_relative"] >= latest_off
        ),
    }


def analyze(off_path, on_path, prefix_path):
    off_status_path = off_path.with_suffix(off_path.suffix + ".status.json")
    if not off_status_path.is_file():
        raise ValueError(f"missing status for {off_path}")
    off_mode = json.loads(off_status_path.read_text()).get("mode")
    if off_mode == "instruction-explicit-roundtrip":
        off = load_trace(
            off_path, "instruction-explicit-roundtrip", 0, 0, "return"
        )
        on = load_trace(
            on_path, "instruction-explicit-roundtrip", 1, 1, "return"
        )
        window = "return"
    elif off_mode == "instruction-explicit":
        off = load_trace(off_path, "instruction-explicit", 0, 0)
        on = load_trace(on_path, "instruction-explicit", 1, 1)
        window = "entry"
    else:
        off = load_trace(off_path, "off", 0)
        on = load_trace(on_path, "instruction-wake", 1)
        window = "entry"
    for key in IDENTITY_KEYS:
        if off["status"].get(key) != on["status"].get(key):
            raise ValueError(f"off/on identity mismatch: {key}")
    prefix = json.loads(prefix_path.read_text())
    prefix_lines = [int(line["paddr_hex"], 16)
                    for line in prefix["fixed_shared_prefix"]["lines"]]
    if len(prefix_lines) != len(set(prefix_lines)) or not prefix_lines:
        raise ValueError("prefix lines are empty or duplicated")

    off_set = {record["paddr"] for record in off["records"]}
    on_set = {record["paddr"] for record in on["records"]}
    off_configured = configured_summary(off, prefix_lines)
    on_configured = configured_summary(on, prefix_lines)
    removed = [line for line in prefix_lines if line in off_set and line not in on_set]
    added = [line for line in prefix_lines if line not in off_set and line in on_set]
    return {
        "purpose": (
            f"Compare same-image, same-ELF, adjacent-arm {window}-bounded I-miss "
            "prefixes without treating a truncated arm as complete."
        ),
        "window": window,
        "prefix": {
            "path": str(prefix_path),
            "sha256": sha256(prefix_path),
            "line_count": len(prefix_lines),
        },
        "identity": {key: off["status"].get(key) for key in IDENTITY_KEYS},
        "off": {key: value for key, value in off.items()
                if key not in ("status", "records")},
        "on": {key: value for key, value in on.items()
               if key not in ("status", "records")},
        "set_comparison": {
            "common_unique_lines": len(off_set & on_set),
            "off_only_unique_lines": len(off_set - on_set),
            "on_only_unique_lines": len(on_set - off_set),
        },
        "configured_lines": {
            "off": off_configured,
            "on": on_configured,
            "removed_by_replay": [f"0x{line:016x}" for line in removed],
            "added_with_replay": [f"0x{line:016x}" for line in added],
            "net_distinct_reduction": (
                off_configured["distinct_lines"]
                - on_configured["distinct_lines"]
            ),
            "net_event_reduction": (
                off_configured["events"] - on_configured["events"]
            ),
            "absence_coverage": configured_absence_coverage(
                off, on, off_configured
            ),
        },
        "single_trace_timing_delta_on_minus_off": {
            key: on["timing"][key] - off["timing"][key]
            for key in off["timing"]
        },
        "interpretation_limits": ([
            f"The {name} trace is a retained first-256 prefix, not a complete entry window."
            for name, trace in (("replay-off", off), ("replay-on", on))
            if trace["truncated"]
        ] + [
            "One trace pair is mechanism evidence, not a statistical performance estimate."
        ]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("off", type=Path)
    parser.add_argument("on", type=Path)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.off, args.on, args.prefix)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote matched trace comparison to {args.output}")


if __name__ == "__main__":
    main()
