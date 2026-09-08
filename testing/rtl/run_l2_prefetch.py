#!/usr/bin/env python3
"""Run a private two-bank L2-controller regression, without shared simulator files.

An optional saved controller source reproduces the pre-fix response blockage.
Only successful builds and the exact selected run marker produce a manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--controller", type=Path)
    parser.add_argument("--baseline-hol", action="store_true")
    parser.add_argument("--verilator", type=Path, default=root / "install/bin/verilator")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "verification.json"
    manifest.unlink(missing_ok=True)
    bp = root / "import/black-parrot"
    bsg = bp / "external/basejump_stl"
    includes = [bsg / name for name in ("bsg_misc", "bsg_cache", "bsg_mem", "bsg_dataflow", "bsg_noc")]
    includes += [bp / name / "src/include" for name in ("bp_common", "bp_me")]
    libraries = [bsg / name for name in ("bsg_misc", "bsg_dataflow", "bsg_mem", "bsg_noc")]
    libraries += [bp / "bp_me/src/v/network", bp / "bp_me/src/v/dev", bp / "bp_common/src/v"]
    controller = (args.controller or bp / "bp_me/src/v/dev/bp_me_cache_controller.sv").resolve()
    sources = [root / "cosim/black-parrot-example/v/bp_common_pkg.sv",
               bp / "bp_me/src/include/bp_me_pkg.sv", bsg / "bsg_cache/bsg_cache_pkg.sv",
               controller, Path(__file__).with_name("l2_prefetch_tb.sv").resolve()]
    driver = Path(__file__).with_name("l2_prefetch_driver.cpp").resolve()
    command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert", "--trace-fst",
               "--top-module", "l2_prefetch_tb", "--prefix", "Vl2_prefetch",
               "--Mdir", str(out / "obj"), "-j", "2", "-Wno-fatal"]
    command += [f"+incdir+{path}" for path in includes]
    for path in libraries:
        command += ["-y", str(path)]
    command += list(map(str, sources)) + [str(driver)]
    (out / "build-command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (out / "build.log").open("w") as log:
        subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    run = [str(out / "obj/Vl2_prefetch")] + (["--baseline-hol"] if args.baseline_hol else [])
    with (out / "run.log").open("w") as log:
        subprocess.run(run, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    result = (out / "run.log").read_text()
    marker = "[L2-PREFETCH] BASELINE HOL:" if args.baseline_hol else "[L2-PREFETCH] PASS:"
    if marker not in result:
        raise RuntimeError("controller regression exited without selected completion marker")
    extra_artifacts = []
    if args.baseline_hol:
        negative = out / "regression-failure"
        negative.mkdir(exist_ok=True)
        failure_log = negative / "run.log"
        with failure_log.open("w") as log:
            rejection = subprocess.run([str(out / "obj/Vl2_prefetch")], cwd=negative,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=30)
        if rejection.returncode != 1 or "HOL: ready normal bank 1 blocked behind pending bank 0 prefetch" not in failure_log.read_text():
            raise RuntimeError("saved baseline did not fail the exact normal-response bypass gate")
        extra_artifacts = [failure_log, negative / "l2-prefetch.fst"]
    dependencies = set(sources + [driver, Path(__file__).resolve()])
    for line in (out / "obj/Vl2_prefetch__verFiles.dat").read_text().splitlines():
        if line.startswith("S "):
            dependencies.add(Path(shlex.split(line)[-1]))
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(dependencies)}
    artifacts = {str(path.relative_to(out)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in [out / "run.log", out / "l2-prefetch.fst", out / "obj/Vl2_prefetch"] + extra_artifacts}
    manifest.write_text(json.dumps({"scope": "Real L2 controller/pumps with ordered mock cache banks; no core or FPGA validation",
                                    "baseline_hol_reproduced": args.baseline_hol,
                                    "regression_passed": not args.baseline_hol,
                                    "source_sha256": hashes, "artifact_sha256": artifacts}, indent=2) + "\n")
    print(result, end="")


if __name__ == "__main__":
    main()
