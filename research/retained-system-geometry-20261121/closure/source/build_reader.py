#!/usr/bin/env python3
"""Build only the selected FST reader in caller-chosen private RAM."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def binding(path):
    path = Path(path).resolve()
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True,
                   help="executable path in private RAM, e.g. /dev/shm/advisory/fst_events")
    p.add_argument("--api-dir", type=Path, default=Path(
        "/home/coyang/zynq-parrot/install/share/verilator/include/gtkwave"))
    a = p.parse_args()
    output = a.output.resolve()
    if not str(output).startswith("/dev/shm/"):
        p.error("reader must be built in private /dev/shm; archive only small closed evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_name("fst_events.c").resolve()
    sources = [source, a.api_dir / "fstapi.c", a.api_dir / "fastlz.c", a.api_dir / "lz4.c"]
    cmd = ["cc", "-O2", "-Wall", "-Wextra", '-DFST_CONFIG_INCLUDE="fst_config.h"',
           "-I" + str(a.api_dir)] + [str(s) for s in sources] + ["-lz", "-lm", "-o", str(output)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    output.with_suffix(".build.log").write_text(result.stdout)
    if result.returncode:
        raise SystemExit(result.returncode)
    report = {"command": cmd, "sources": [binding(s) for s in sources],
              "headers": [binding(a.api_dir / s) for s in ("fstapi.h", "fst_config.h")],
              "executable": binding(output), "build_log": binding(output.with_suffix(".build.log")),
              "purpose": "host-only selected closed-FST reader, no model/target execution"}
    output.with_suffix(".build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
