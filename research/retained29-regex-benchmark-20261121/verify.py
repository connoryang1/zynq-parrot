#!/usr/bin/env python3
"""Verify closed regex derivative host/link evidence without target execution."""
import difflib
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import derive
import prepare

HERE = Path(__file__).resolve().parent


def verify():
    out = HERE / "preparation-002"
    manifest_path = out / "manifest.json"
    m = json.loads(manifest_path.read_text())
    assert m["state"] == "PASS-real-regex-host-protocol-and-RV64-link-only"
    archive_path = HERE / "closed-inputs.json"
    archive = json.loads(archive_path.read_text())
    assert archive["gate_manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    archived = {r["original"]["path"]:r for r in archive["inputs"]}
    assert set(archived) == set(m["inputs"])
    drift = []
    for name, binding in m["inputs"].items():
        row = archived[name]
        assert row["original"] == binding
        assert prepare.binding(row["snapshot"]["path"]) == row["snapshot"]
        assert row["snapshot"]["sha256"] == binding["sha256"]
        if prepare.binding(name) != binding: drift.append(name)
    # Later authorized host-runner changes are not inputs to this closed gate.
    # The derivative and read-only workload module must still match its bytes.
    for name in ("scheduler_retained29_regex_benchmark.c", "retained29_regex_workload.h",
                 "test_retained29_regex_benchmark.py"):
        p = str(derive.ROOT / "linux-tests" / name)
        assert prepare.binding(p) == m["inputs"][p]
    assert m["frozen_runtime_sources"] == 17
    assert derive.verify() == json.loads((out / "provenance.json").read_text())
    expected_patch = "".join(difflib.unified_diff(derive.BASE.read_text().splitlines(True),
        derive.NEW.read_text().splitlines(True),fromfile=str(derive.BASE),tofile=str(derive.NEW)))
    assert (out / "plain-to-regex.patch").read_text() == expected_patch
    checked = []

    def walk(value):
        if isinstance(value,dict):
            if set(("path","bytes","sha256")) <= value.keys():
                assert prepare.binding(value["path"]) == value,value["path"]
                checked.append(value["path"])
            for item in value.values():walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)

    walk({key:value for key,value in m.items() if key != "inputs"})
    for command in m["commands"]:assert command["returncode"] == 0
    for label in ("host-protocol", "host-protocol-sanitizers"):
        log = (out / (label+".log")).read_text()
        assert "Ran 6 tests" in log and log.rstrip().endswith("OK")
        assert "ERROR" not in log and "AddressSanitizer" not in log and "runtime error:" not in log
    assert Path(m["elf"]["path"]).read_bytes() == Path(m["rebuilt_elf"]["path"]).read_bytes()
    assert m["needed"] == ["libc.so.6","ld-linux-riscv64-lp64d.so.1"]
    rejected_path = HERE / "rejected-by-value-adapter/manifest.json"
    rejected = json.loads(rejected_path.read_text())
    assert rejected["state"] == "EXPECTED-REJECTION-host-mock-object-identity-only"
    walk(rejected)
    assert rejected["returncode"] != 0
    failed_cross = json.loads((HERE / "preparation-001/manifest.json").read_text())
    assert failed_cross["state"] == "FAILED-PREPARATION-NOT-TARGET-EVIDENCE"
    assert "extension `zifencei' required" in (HERE / "preparation-001/cross-build.log").read_text()
    return dict(state="PASS-closed-regex-derivative-preparation",manifest=prepare.binding(manifest_path),
        input_archive=prepare.binding(archive_path),archived_inputs=len(archived),
        other_artifact_bindings_checked=len(checked),post_gate_current_input_drift=drift,
        rejected_adapter_manifest=prepare.binding(rejected_path),
        elf=m["elf"],scope="Host functional/sanitizer and RV64 link only; no target execution or performance claim",
        verifier=prepare.binding(__file__))


if __name__ == "__main__":print(json.dumps(verify(),indent=2))
