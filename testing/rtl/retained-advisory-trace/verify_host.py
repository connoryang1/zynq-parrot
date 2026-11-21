#!/usr/bin/env python3
"""Archive host fixtures and a name-only closed-FST header coverage check.

No RISC-V program/model is executed. A header check is not advisory trace PASS.
"""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("advisory_validate", HERE / "validate.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--header-fst", type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    source_before = [v.binding(f) for f in sorted(HERE.iterdir()) if f.suffix in (".py", ".c")]
    cmd = ["python3", "-m", "unittest", "discover", "-s", str(HERE), "-p", "test_*.py", "-v"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    (a.out / "tests.log").write_text(result.stdout)
    v.require(result.returncode == 0, "host fixture tests failed")
    with tempfile.TemporaryDirectory(prefix="advisory-reader-header-", dir="/dev/shm") as temp:
        reader = Path(temp) / "fst_events"
        build = ["python3", str(HERE / "build_reader.py"), "--output", str(reader)]
        result = subprocess.run(build, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=150)
        (a.out / "reader-build-command.log").write_text(result.stdout)
        if reader.with_suffix(".build.log").exists():
            shutil.copyfile(reader.with_suffix(".build.log"), a.out / "reader.build.log")
        v.require(result.returncode == 0, "reader build failed")
        shutil.copyfile(reader.with_suffix(".build.json"), a.out / "reader.build.json")
        header_cmd = [str(reader), str(a.header_fst.resolve()), "--list"]
        result = subprocess.run(header_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        (a.out / "header.stderr").write_text(result.stderr)
        v.require(result.returncode == 0, "name-only FST header failed")
        with gzip.open(a.out / "header.tsv.gz", "wt") as saved:
            saved.write(result.stdout)
        names = []
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            if fields[0] == "#VAR":
                names.append((fields[3], int(fields[1]), int(fields[2])))
        mapping = {}
        for key, (suffix, width) in v.selections().items():
            matches = [item for item in names if item[0] == suffix or item[0].endswith("." + suffix)]
            v.require(len(matches) == 1 and matches[0][1] == width, "missing/ambiguous/wrong-width actual header " + key)
            mapping[key] = {"path": matches[0][0], "width": width, "handle": matches[0][2]}
        (a.out / "selected-header-map.json").write_text(json.dumps(mapping, indent=2) + "\n")
    v.require(source_before == [v.binding(f) for f in sorted(HERE.iterdir()) if f.suffix in (".py", ".c")],
              "validator source changed during host gate")
    report = {"accepted": True, "scope": "host fixture tests + existing closed-FST names/widths only; no advisory execution acceptance",
              "tests_command": cmd, "reader_build_command": build, "header_command": header_cmd,
              "header_fst": v.binding(a.header_fst), "sources": source_before,
              "artifacts": [v.binding(f) for f in sorted(a.out.iterdir())]}
    (a.out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: host-only fixture tests and real closed-FST name/width coverage; no target execution")


if __name__ == "__main__":
    main()
