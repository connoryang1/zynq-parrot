#!/usr/bin/env python3
"""Recheck closed host/link preparation; never execute a target ELF."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import prepare

HERE = Path(__file__).resolve().parent


def verify(out):
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["state"] == "PASS-host-oracle-ASAN-UBSAN-and-RV64-link-only"
    bindings = []

    def walk(value):
        if isinstance(value, dict):
            if set(("path", "bytes", "sha256")) <= value.keys():
                assert prepare.binding(value["path"]) == value, value["path"]
                bindings.append(value["sha256"])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(manifest)
    for command in manifest["commands"]:
        assert command["returncode"] == command["expected_returncode"]
    assert (out / "host-checks.stdout").read_text().strip() == "RETAINED29_REGEX_HOST_PASS"
    assert not (out / "host-checks.stderr").read_bytes()
    for key in manifest["inputs"]:
        source = out / "source" / Path(key).name
        if Path(key).parent in (HERE, HERE.parents[1] / "linux-tests") and source.exists():
            assert source.read_bytes() == Path(key).read_bytes()
    assert (out / "source/old_regex_abi_helpers.py").read_bytes() == Path(
        manifest["accepted_runtime_ABI"]["reused_helpers"]["path"]).read_bytes()
    for case in manifest["oracle_cases"]:
        label = "oracle-%d-%d" % (case["kib"], case["seed"])
        assert not (out / (label + ".stderr")).read_bytes()
        assert prepare.oracle((out / (label + ".stdout")).read_text(), case["kib"],
                              case["seed"], case["requests"]) == case
    assert len(manifest["oracle_cases"]) == 8
    return dict(state="PASS-closed-bindings-and-independent-oracles", manifest=prepare.binding(manifest_path),
                file_bindings_checked=len(bindings), independent_oracle_cases=8,
                limits=manifest["limits"], verifier=prepare.binding(__file__))


if __name__ == "__main__":
    print(json.dumps(verify(HERE / "preparation-001"), indent=2))
