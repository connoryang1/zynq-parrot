#!/usr/bin/env python3
"""Compare disabled and enabled pipe miss traces at four target demand lines."""

import argparse
import hashlib
import json
import re
from pathlib import Path


CONFIG = re.compile(
    r"TRACE_CONFIG path=pipe group=(\d+) first_offset=(\d+) lines=4 "
    r"warmups=(\d+) replay=([a-z-]+) mode=(\d+)"
)
HEADER = re.compile(
    r"TRACE_HEADER path=pipe group=(\d+) warmups=(\d+) start=(\d+) "
    r"launch=(\d+) entry=(\d+) after_load=(\d+) returned=(\d+) "
    r"wake_to_entry=(\d+) load_cycles=(\d+) wake_to_load=(\d+) "
    r"i_count=(\d+) d_count=(\d+) i_overflow=(\d+) d_overflow=(\d+) "
    r"armed=(\d+) status=0x([0-9a-f]+)"
)
RECORD = re.compile(
    r"TRACE_RECORD seq=(\d+) side=([ID]) index=(\d+) cycle=(\d+) "
    r"relative=(\d+) message=(0x[0-9a-f]+) paddr=(0x[0-9a-f]+) "
    r"raw=(0x[0-9a-f]+)"
)


def sha256(path):
    """Return one retained artifact's lowercase SHA-256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_trace(path, expected_preview):
    """Validate one bounded trace and locate its four target demand misses."""
    text = path.read_text(errors="replace").replace("\r", "")
    status_path = path.with_suffix(path.suffix + ".status.json")
    if not status_path.is_file():
        raise ValueError(f"{path}: missing status")
    status = json.loads(status_path.read_text())
    expected_status = {
        "status": "PASS",
        "program": "physical-preview-pipe",
        "group": 7,
        "preview_mode": expected_preview,
        "runner_exit": 0,
    }
    for key, expected in expected_status.items():
        if status.get(key) != expected:
            raise ValueError(
                f"{path}: status {key}={status.get(key)!r}, expected {expected!r}"
            )
    configs = CONFIG.findall(text)
    expected_mode = "0" if expected_preview == "disabled" else "1"
    if configs != [("7", "1792", "16", expected_preview, expected_mode)]:
        raise ValueError(f"{path}: invalid trace configuration")
    headers = HEADER.findall(text)
    if len(headers) != 1:
        raise ValueError(f"{path}: expected one trace header")
    values = [int(value, 16) if index == 15 else int(value)
              for index, value in enumerate(headers[0])]
    names = (
        "group", "warmups", "start", "launch", "entry", "after_load",
        "returned", "wake_to_entry", "load_cycles", "wake_to_load",
        "i_count", "d_count", "i_overflow", "d_overflow", "armed",
        "status",
    )
    header = dict(zip(names, values))
    if header["i_overflow"] or header["d_overflow"] or header["armed"]:
        raise ValueError(f"{path}: trace overflowed or remained armed")
    if "TRACE_PASS" not in text or "CORE PASS" not in text or "BSG PASS" not in text:
        raise ValueError(f"{path}: missing terminal PASS marker")

    records = []
    for match in RECORD.finditer(text):
        seq, side, index, cycle, relative, message, paddr, raw = match.groups()
        records.append({
            "seq": int(seq), "side": side, "index": int(index),
            "cycle": int(cycle), "relative": int(relative),
            "message": int(message, 16), "paddr": int(paddr, 16),
            "raw": int(raw, 16),
        })
    if len(records) != header["i_count"] + header["d_count"]:
        raise ValueError(f"{path}: record count does not match header")
    target_offsets = (0x700, 0x740, 0x780, 0x7c0)
    demand = [
        record for record in records
        if record["side"] == "D"
        and header["entry"] <= record["cycle"] <= header["after_load"]
        and (record["paddr"] & 0xfff) in target_offsets
    ]
    if len(demand) != 4 or tuple(
            record["paddr"] & 0xfff for record in demand) != target_offsets:
        raise ValueError(f"{path}: missing ordered target demand misses")
    target_addresses = {record["paddr"] for record in demand}
    earlier = [
        record for record in records
        if record["paddr"] in target_addresses
        and record["cycle"] < header["entry"]
    ]
    return {
        "path": str(path),
        "sha256": sha256(path),
        "status_path": str(status_path),
        "status_sha256": sha256(status_path),
        "identity": {
            key: status.get(key) for key in (
                "nbf_sha256", "transfer_sha256", "elf_sha256",
                "control_program_sha256", "bitstream_sha256",
            )
        },
        "header": header,
        "target_demand": [
            {
                "paddr": f"0x{record['paddr']:09x}",
                "cycles_after_entry": record["cycle"] - header["entry"],
                "message": record["message"],
            }
            for record in demand
        ],
        "target_records_before_entry": len(earlier),
    }


def compare(disabled_path, enabled_path):
    """Validate an exact pair and summarize demand timing."""
    disabled = load_trace(disabled_path, "disabled")
    enabled = load_trace(enabled_path, "wake-early-data")
    if disabled["identity"] != enabled["identity"]:
        raise ValueError("trace identities differ")
    return {
        "purpose": (
            "Determine whether four mode-one physical previews complete before "
            "the target's first dependent loads on the 16 KiB routed FPGA."
        ),
        "identity": disabled["identity"],
        "disabled": disabled,
        "enabled": enabled,
        "load_cycles_enabled_minus_disabled": (
            enabled["header"]["load_cycles"]
            - disabled["header"]["load_cycles"]
        ),
        "interpretation_limit": (
            "The recorder reports architectural cache-miss events, not detached "
            "hint issue or completion directly. A target demand record can join "
            "an already outstanding hint."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disabled", required=True, type=Path)
    parser.add_argument("--enabled", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.disabled, args.enabled)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
