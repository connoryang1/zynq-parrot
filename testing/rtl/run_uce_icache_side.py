#!/usr/bin/env python3
"""Build and run the UCE-to-I-cache advisory-buffer retirement test."""
import argparse
from pathlib import Path
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verilator", type=Path,
                        default=Path("/home/coyang/zynq-parrot/install/bin/verilator"))
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
               Path(__file__).with_name("uce_icache_replay_tb.sv")]
    driver = Path(__file__).with_name("uce_icache_side_driver.cpp")
    command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert",
               "--trace-fst", "--top-module", "uce_icache_replay_tb", "--prefix",
               "Vuce_icache_replay", "--Mdir", str(out / "obj"), "-Gside_buffer_p=1",
               "-j", "2", "-Wno-fatal"]
    command += [f"+incdir+{path}" for path in includes]
    for path in libraries:
        command += ["-y", str(path)]
    command += [str(path) for path in sources] + [str(driver)]
    with (out / "build.log").open("w") as log:
        subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    with (out / "run.log").open("w") as log:
        subprocess.run([str(out / "obj/Vuce_icache_replay")], cwd=out,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    result = (out / "run.log").read_text()
    if "[UCE-ICACHE-SIDE] PASS:" not in result:
        raise RuntimeError("unit test exited without its acceptance marker")
    print(result, end="")


if __name__ == "__main__":
    main()
