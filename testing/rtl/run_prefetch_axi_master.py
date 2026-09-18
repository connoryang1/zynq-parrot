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
               root / "import/black-parrot-subsystems/blackparrot/v/bp_prefetch_axi_master.sv",
               Path(__file__).resolve().with_name("prefetch_axi_master_tb.sv")]
    driver = Path(__file__).resolve().with_name("prefetch_axi_master_driver.cpp")
    commands = {}
    run_output = []
    for width in (32, 64):
        obj = out / f"obj{width}"
        command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert",
                   "--top-module", "prefetch_axi_master_tb", "--Mdir", str(obj),
                   f"-Gaxi_data_width_p={width}", "-j", "2", "-Wno-fatal"]
        command += [f"+incdir+{path}" for path in includes]
        for path in libraries:
            command += ["-y", str(path)]
        command += list(map(str, sources)) + [str(driver)]
        commands[str(width)] = command
        with (out / f"build-{width}.log").open("w") as log:
            subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        result = subprocess.run([str(obj / "Vprefetch_axi_master_tb")], cwd=out,
                                text=True, capture_output=True, check=True, timeout=30)
        marker = f"[PREFETCH-AXI] PASS: {width}-bit AXI"
        if marker not in result.stdout:
            raise RuntimeError(f"{width}-bit prefetch AXI regression completed without PASS marker")
        run_output.append(result.stdout)
    (out / "build-command.json").write_text(json.dumps(commands, indent=2) + "\n")
    (out / "run.log").write_text("".join(run_output))

    dependencies = set(sources + [driver, Path(__file__).resolve()])
    for width in (32, 64):
        verfiles = out / f"obj{width}/Vprefetch_axi_master_tb__verFiles.dat"
        for line in verfiles.read_text().splitlines():
            if line.startswith("S "):
                dependencies.add(Path(shlex.split(line)[-1]))
    hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(dependencies)}
    artifacts = {f"obj{width}/Vprefetch_axi_master_tb":
                 hashlib.sha256((out / f"obj{width}/Vprefetch_axi_master_tb").read_bytes()).hexdigest()
                 for width in (32, 64)}
    artifacts["run.log"] = hashlib.sha256((out / "run.log").read_bytes()).hexdigest()
    verification.write_text(json.dumps({
        "scope": "Dedicated prefetch AXI bridge protocol and data-path regression",
        "source_sha256": hashes,
        "artifact_sha256": artifacts,
        "passed": True,
    }, indent=2) + "\n")
    print("".join(run_output), end="")


if __name__ == "__main__":
    main()
