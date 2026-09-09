#!/usr/bin/env python3
"""Build and run the real UCE prefetch testbench in an isolated output directory.

This runner never invokes the shared core simulator or changes its collateral.
Build failures cannot fall through to a previously generated executable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shlex
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verilator", type=Path, default=root / "install/bin/verilator")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    verification = out / "verification.json"
    if verification.exists():
        verification.unlink()
    bp = root / "import/black-parrot"
    bsg = bp / "external/basejump_stl"
    includes = [bsg / name for name in ("bsg_misc", "bsg_cache", "bsg_mem", "bsg_dataflow", "bsg_noc")]
    includes += [bp / name / "src/include" for name in ("bp_common", "bp_me")]
    libraries = [bsg / name for name in ("bsg_misc", "bsg_dataflow", "bsg_mem")]
    libraries += [bp / "bp_me/src/v/network", bp / "bp_common/src/v"]
    sources = [bp / "bp_common/src/include/bp_common_pkg.sv",
               bp / "bp_me/src/include/bp_me_pkg.sv",
               bp / "bp_me/src/v/cce/bp_uce.sv",
               Path(__file__).resolve().with_name("uce_prefetch_tb.sv")]
    driver = Path(__file__).resolve().with_name("uce_prefetch_driver.cpp")
    command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert", "--trace-fst",
               "--top-module", "uce_prefetch_tb", "--prefix", "Vuce_prefetch",
               "--Mdir", str(out / "obj"), "-j", "2", "-Wno-fatal"]
    command += [f"+incdir+{path}" for path in includes]
    for path in libraries:
        command += ["-y", str(path)]
    command += list(map(str, sources))
    command += [str(driver)]
    (out / "build-command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (out / "build.log").open("w") as log:
        subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    with (out / "run.log").open("w") as log:
        subprocess.run([str(out / "obj/Vuce_prefetch")], cwd=out,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    result = (out / "run.log").read_text()
    if "[UCE-PREFETCH] PASS:" not in result:
        raise RuntimeError("unit executable exited without its acceptance marker")
    negative = out / "bad-response"
    negative.mkdir(exist_ok=True)
    with (negative / "run.log").open("w") as log:
        rejection = subprocess.run([str(out / "obj/Vuce_prefetch"), "--bad-response"],
                                   cwd=negative, stdout=log, stderr=subprocess.STDOUT,
                                   timeout=30, preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
    rejected_log = (negative / "run.log").read_text()
    if rejection.returncode == 0 or "UCE prefetch response address does not match its slot" not in rejected_log:
        raise RuntimeError("malformed-response negative gate did not trip its specific RTL assertion")
    dependencies = set(sources + [driver, Path(__file__).resolve()])
    for line in (out / "obj/Vuce_prefetch__verFiles.dat").read_text().splitlines():
        if line.startswith("S "):
            dependencies.add(Path(shlex.split(line)[-1]))
    hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(dependencies)}
    artifact_hashes = {str(path.relative_to(out)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (out / "run.log", out / "uce-prefetch.fst",
                                   out / "obj/Vuce_prefetch", negative / "run.log")}
    verification.write_text(json.dumps({
        "scope": "Standalone UCE+stream-pump functional checks; no core/FPGA acceptance",
        "source_sha256": hashes, "artifact_sha256": artifact_hashes, "passed": True,
        "malformed_response_rejected": True,
    }, indent=2) + "\n")
    print(result, end="")


if __name__ == "__main__":
    main()
