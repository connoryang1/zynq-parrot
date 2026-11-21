#!/usr/bin/env python3
"""Verify this offline audit's exact snapshots and closed evidence, without target execution."""
import gzip
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    here = Path(__file__).resolve().parent
    bindings = json.loads((here / "bindings.json").read_text())
    for record in bindings["records"]:
        if "snapshot" in record:
            archive = (here / record["snapshot"]).read_bytes()
            assert sha(archive) == record["snapshot_sha256"], record["snapshot"]
            data = gzip.decompress(archive)
        else:
            data = Path(record["original_path"]).read_bytes()
        assert len(data) == record["bytes"], record["original_path"]
        assert sha(data) == record["sha256"], record["original_path"]
    report = json.loads((here / "review.json").read_text())
    closed = next(r for r in bindings["records"]
                  if r["original_path"].endswith("closed-comparison/results.json"))
    assert closed["sha256"] == "acbdd8a0d32617e69b9601cc5b594cc4780b288c53cec18f86dfd59b317c3f1f"
    data = json.loads(Path(closed["original_path"]).read_text())
    assert report["closed_control"]["ring_cycles"] == data["complete_ring_cycles"]
    assert report["closed_control"]["accepted_D_misses_per_program"] == 6508
    assert report["closed_control"]["accepted_D_fill_beats_per_program"] == 6508*8
    old = next(r for r in bindings["records"]
               if r["original_path"].endswith("control-v2/board-summary.json"))
    old = json.loads(Path(old["original_path"]).read_text())
    assert old["probe_boots"] == 3
    assert old["pairs"]["cold"]["n"] == 48
    assert old["pairs"]["cold"]["median"] == 41
    assert old["pairs"]["cold"]["max"] == 44
    assert old["pairs"]["hot"]["median"] == 3
    for scenario in report["prospective_cpu_scenarios"]:
        import math
        assert scenario["cycles_ceil"] == [math.ceil(ns*scenario["assumed_cpu_ghz"])
                                           for ns in scenario["CPU_visible_local_memory_ns"]]
    assert report["maximum_proposed_additive_delay"]["actual_20MHz_target_us"] == 384/20
    assert report["maximum_proposed_additive_delay"]["assumed_3p2GHz_additional_ns"] == 384/3.2
    result = {"passed": True, "verified_bindings": len(bindings["records"]),
              "scope": "Offline source/evidence/hash and arithmetic verification only; no target run or FPGA calibration",
              "audit_files_sha256": {p.name: sha(p.read_bytes()) for p in
                                     (here / "README.md", here / "bindings.json", here / "review.json",
                                      here / "primary-sources.json", Path(__file__).resolve())}}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
