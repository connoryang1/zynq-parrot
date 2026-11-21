#!/usr/bin/env python3
"""Clean, traced cancellation and complete-line assembly gate for the I adapter."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import os


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bp", type=Path, default=root / "import/black-parrot")
    parser.add_argument("--evidence", type=Path, help="Copy closed small artifacts out of a temporary build mount")
    parser.add_argument("--sanitize", action="store_true", help="Instrument the host test harness for memory errors")
    parser.add_argument("--verilator", type=Path,
                        default=Path("/home/coyang/zynq-parrot/install/bin/verilator"))
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = args.bp.resolve() / "bp_fe/src/v/bp_fe_icache_retained_bram.sv"
    driver = Path(__file__).resolve().with_name("icache_retained_bram_driver.cpp")
    inputs = (source, driver, Path(__file__).resolve())
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    command = [str(args.verilator), "--cc", "--exe", "--build", "--assert", "--trace-fst",
               "--top-module", "bp_fe_icache_retained_bram", "--Mdir", str(out / "obj"),
               "-j", "2", "-Wno-fatal", str(source), str(driver)]
    if args.sanitize:
        command += ["-CFLAGS", "-fsanitize=address -g", "-LDFLAGS", "-fsanitize=address"]
    (out / "build-command.json").write_text(json.dumps(command, indent=2) + "\n")
    try:
        with (out / "build.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        with (out / "run.log").open("w") as log:
            env = os.environ.copy()
            if args.sanitize:
                # LSan cannot enumerate threads under the managed ptrace
                # sandbox. This gate checks address errors, not leak freedom.
                env["ASAN_OPTIONS"] = "detect_leaks=0"
            subprocess.run([str(out / "obj/Vbp_fe_icache_retained_bram")], cwd=out,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60, env=env)
    except (subprocess.SubprocessError, OSError):
        for name in ("build.log", "run.log"):
            if (out / name).exists():
                print((out / name).read_text()[-6000:])
        if args.evidence:
            shutil.copytree(out, args.evidence, ignore=shutil.ignore_patterns("obj", "*.fst"))
        raise
    if "[ICACHE-RETAINED-ADAPTER] PASS:" not in (out / "run.log").read_text():
        raise RuntimeError("missing adapter acceptance marker")
    for path in inputs:
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[str(path)]:
            raise RuntimeError("source changed during clean verification: " + str(path))
    result = {"scope": "Standalone I adapter only; no full-core, FPGA, fit or performance evidence",
              "passed": True, "host_address_sanitizer": args.sanitize,
              "leak_sanitizer": False, "source_sha256": hashes,
              "artifact_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in (out / "build-command.json", out / "build.log",
                                            out / "run.log", out / "icache-retained-adapter.fst",
                                            out / "obj/Vbp_fe_icache_retained_bram")}}
    (out / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    if args.evidence:
        shutil.copytree(out, args.evidence, ignore=shutil.ignore_patterns("obj"))
    print((out / "run.log").read_text(), end="")


if __name__ == "__main__":
    main()
