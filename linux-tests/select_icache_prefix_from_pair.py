#!/usr/bin/env python3
"""Select replay lines whose matched trace shows fewer demand events."""

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(prefix_path, analysis_path):
    prefix = json.loads(prefix_path.read_text())
    analysis = json.loads(analysis_path.read_text())
    table = prefix["fixed_shared_prefix"]
    source_lines = table["lines"]
    if table["line_count"] != len(source_lines) or not source_lines:
        raise ValueError("source prefix is empty or inconsistent")
    source_by_address = {int(line["paddr"]): line for line in source_lines}
    if len(source_by_address) != len(source_lines):
        raise ValueError("source prefix contains duplicate addresses")

    configured = analysis["configured_lines"]
    off_lines = configured["off"]["lines"]
    on_lines = configured["on"]["lines"]
    off = {int(line["paddr"]): len(line["relatives"]) for line in off_lines}
    on = {int(line["paddr"]): len(line["relatives"]) for line in on_lines}
    if set(off) != set(source_by_address) or set(on) != set(source_by_address):
        raise ValueError("analysis configured lines do not match source prefix")

    ranked = []
    for original_rank, line in enumerate(source_lines):
        address = int(line["paddr"])
        if int(line["rank"]) != original_rank:
            raise ValueError("source prefix ranks are not consecutive")
        reduction = off[address] - on[address]
        if reduction > 0:
            ranked.append((reduction, original_rank, line))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    if not ranked:
        raise ValueError("matched trace has no positive event-reduction lines")

    selected = []
    for rank, (reduction, original_rank, source) in enumerate(ranked):
        line = dict(source)
        line.update({
            "rank": rank,
            "source_rank": original_rank,
            "off_events": off[int(source["paddr"])],
            "on_events": on[int(source["paddr"])],
            "event_reduction": reduction,
        })
        selected.append(line)
    return {
        "purpose": (
            "Select only instruction-prefix lines with a positive demand-event "
            "reduction in the matched replay-off/on entry trace pair."
        ),
        "input_identity": {
            "source_prefix": str(prefix_path),
            "source_prefix_sha256": sha256(prefix_path),
            "matched_analysis": str(analysis_path),
            "matched_analysis_sha256": sha256(analysis_path),
            "kernel_sha256": prefix.get("input_identity", {}).get("kernel_sha256"),
        },
        "fixed_shared_prefix": {
            "policy": (
                "positive off-minus-on demand-event reduction, descending by "
                "reduction then ascending original prefix rank"
            ),
            "line_count": len(selected),
            "lines": selected,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = select(args.prefix, args.analysis)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"wrote {args.output} with "
        f"{result['fixed_shared_prefix']['line_count']} selected lines"
    )


if __name__ == "__main__":
    main()
