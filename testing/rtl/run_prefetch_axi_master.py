#!/usr/bin/env python3
"""Build and run the dedicated prefetch AXI bridge regression in isolation."""
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
    parser.add_argument("--verilator", type=Path, default=root / "install/bin/verilator")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    verification = out / "verification.json"
    if verification.exists():
        verification.unlink()

    bp = root / "import/black-parrot"
    bsg = bp / "external/basejump_stl"
    includes = [bsg / name for name in
                ("bsg_misc", "bsg_cache", "bsg_mem", "bsg_dataflow", "bsg_noc")]
    includes += [bp / name / "src/include" for name in ("bp_common", "bp_me")]
    libraries = [bsg / name for name in ("bsg_misc", "bsg_dataflow", "bsg_mem")]
    sources = [root / "cosim/black-parrot-minimal-example/v/bp_common_pkg.sv",
               bp / "bp_me/src/include/bp_me_pkg.sv",
               root / "cosim/black-parrot-minimal-example/v/bp_prefetch_axi_master.sv",
               Path(__file__).resolve().with_name("prefetch_axi_master_tb.sv")]
    driver = Path(__file__).resolve().with_name("prefetch_axi_master_driver.cpp")
    command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert",
               "--top-module", "prefetch_axi_master_tb", "--Mdir", str(out / "obj"),
               "-j", "2", "-Wno-fatal"]
    command += [f"+incdir+{path}" for path in includes]
    for path in libraries:
        command += ["-y", str(path)]
    command += list(map(str, sources)) + [str(driver)]
    (out / "build-command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (out / "build.log").open("w") as log:
        subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    result = subprocess.run([str(out / "obj/Vprefetch_axi_master_tb")], cwd=out,
                            text=True, capture_output=True, check=True, timeout=30)
    if "[PREFETCH-AXI] PASS:" not in result.stdout:
        raise RuntimeError("prefetch AXI regression completed without PASS marker")
    (out / "run.log").write_text(result.stdout)

    dependencies = set(sources + [driver, Path(__file__).resolve()])
    for line in (out / "obj/Vprefetch_axi_master_tb__verFiles.dat").read_text().splitlines():
        if line.startswith("S "):
            dependencies.add(Path(shlex.split(line)[-1]))
    hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(dependencies)}
    artifact = out / "obj/Vprefetch_axi_master_tb"
    verification.write_text(json.dumps({
        "scope": "Dedicated prefetch AXI bridge protocol and data-path regression",
        "source_sha256": hashes,
        "artifact_sha256": {
            "run.log": hashlib.sha256((out / "run.log").read_bytes()).hexdigest(),
            str(artifact.relative_to(out)): hashlib.sha256(artifact.read_bytes()).hexdigest(),
        },
        "passed": True,
    }, indent=2) + "\n")
    print(result.stdout, end="")


if __name__ == "__main__":
    main()
