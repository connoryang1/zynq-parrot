#!/usr/bin/env python3
"""Build and run the tagged D-cache footprint replay controller gate."""
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
    source = root / "import/black-parrot/bp_top/src/v/bp_dcache_replay_ctrl.sv"
    driver = Path(__file__).resolve().with_name("dcache_replay_ctrl_driver.cpp")
    command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert",
               "--top-module", "bp_dcache_replay_ctrl", "--prefix",
               "Vbp_dcache_replay_ctrl", "--Mdir", str(out / "obj"), "-j", "2",
               "-Wno-fatal", str(source), str(driver)]
    with (out / "build.log").open("w") as log:
        subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    executable = out / "obj/Vbp_dcache_replay_ctrl"
    with (out / "run.log").open("w") as log:
        subprocess.run([str(executable)], cwd=out, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=30)
    result = (out / "run.log").read_text()
    if "[DCACHE-REPLAY-CTRL] PASS:" not in result:
        raise RuntimeError("controller gate exited without its acceptance marker")
    print(result, end="")


if __name__ == "__main__":
    main()
