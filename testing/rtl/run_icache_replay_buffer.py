#!/usr/bin/env python3
"""Build and run the detached instruction replay-buffer test."""
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
    includes += [bp / name / "src/include" for name in ("bp_common", "bp_fe")]
    libraries = [bsg / name for name in ("bsg_misc", "bsg_dataflow", "bsg_mem")]
    libraries += [bp / "bp_common/src/v"]
    sources = [bp / "bp_common/src/include/bp_common_pkg.sv",
               bp / "bp_fe/src/include/bp_fe_pkg.sv",
               bp / "bp_fe/src/v/bp_fe_icache.sv",
               Path(__file__).with_name("icache_replay_buffer_tb.sv")]
    driver = Path(__file__).with_name("icache_replay_buffer_driver.cpp")
    command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert",
               "--trace-fst", "--top-module", "icache_replay_buffer_tb", "--prefix",
               "Vicache_replay_buffer", "--Mdir", str(out / "obj"), "-j", "2",
               "-Wno-fatal"]
    command += [f"+incdir+{path}" for path in includes]
    for path in libraries:
        command += ["-y", str(path)]
    command += [str(path) for path in sources] + [str(driver)]
    with (out / "build.log").open("w") as log:
        subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    with (out / "run.log").open("w") as log:
        subprocess.run([str(out / "obj/Vicache_replay_buffer")], cwd=out,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    result = (out / "run.log").read_text()
    if "[ICACHE-REPLAY-BUFFER] PASS:" not in result:
        raise RuntimeError("unit test exited without its acceptance marker")
    print(result, end="")


if __name__ == "__main__":
    main()
