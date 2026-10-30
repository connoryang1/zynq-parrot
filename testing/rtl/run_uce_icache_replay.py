#!/usr/bin/env python3
"""Build and run the directed physical I-cache replay UCE test."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def dependency_name(path, root):
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verilator", type=Path,
                        default=Path("/home/coyang/zynq-parrot/install/bin/verilator"))
    parser.add_argument("--side-buffer", action="store_true",
                        help="exercise the FPGA detached instruction buffer mode")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bp = root / "import/black-parrot"
    bsg = bp / "external/basejump_stl"
    includes = [bsg / name for name in ("bsg_misc", "bsg_cache", "bsg_mem",
                                         "bsg_dataflow", "bsg_noc")]
    includes += [bp / name / "src/include" for name in ("bp_common", "bp_me")]
    libraries = [bsg / name for name in ("bsg_misc", "bsg_dataflow", "bsg_mem")]
    libraries += [bp / "bp_me/src/v/network", bp / "bp_common/src/v"]
    sources = [bp / "bp_common/src/include/bp_common_pkg.sv",
               bp / "bp_me/src/include/bp_me_pkg.sv",
               bp / "bp_me/src/v/cce/bp_uce.sv",
               Path(__file__).resolve().with_name("uce_icache_replay_tb.sv")]
    driver = Path(__file__).resolve().with_name("uce_icache_replay_driver.cpp")
    command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert",
               "--trace-fst", "--top-module", "uce_icache_replay_tb", "--prefix",
               "Vuce_icache_replay", "--Mdir", str(out / "obj"), "-j", "2", "-Wno-fatal"]
    if args.side_buffer:
        command += ["-Gside_buffer_p=1"]
    command += [f"+incdir+{path}" for path in includes]
    for path in libraries:
        command += ["-y", str(path)]
    command += list(map(str, sources)) + [str(driver)]
    (out / "build-command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (out / "build.log").open("w") as log:
        subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    with (out / "run.log").open("w") as log:
        subprocess.run([str(out / "obj/Vuce_icache_replay")], cwd=out,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    result = (out / "run.log").read_text()
    marker = "[UCE-ICACHE-REPLAY] PASS:"
    if marker not in result:
        raise RuntimeError("unit executable exited without its acceptance marker")
    dependencies = set(sources + [driver, Path(__file__).resolve()])
    for line in (out / "obj/Vuce_icache_replay__verFiles.dat").read_text().splitlines():
        if line.startswith("S "):
            dependencies.add(Path(shlex.split(line)[-1]))
    verification = {
        "scope": ("Standalone UCE physical I-cache replay protocol; "
                  f"side_buffer={int(args.side_buffer)}; no core/FPGA acceptance"),
        "source_sha256": {
            dependency_name(path, root): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(dependencies)
        },
        "artifact_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (out / "run.log", out / "uce-icache-replay.fst",
                         out / "obj/Vuce_icache_replay")
        },
        "passed": True,
    }
    (out / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print(result, end="")


if __name__ == "__main__":
    main()
