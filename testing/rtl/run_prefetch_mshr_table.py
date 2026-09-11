#!/usr/bin/env python3
"""Build and run the detached-prefetch MSHR table regression."""
import argparse
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verilator", type=Path, default=root / "install/bin/verilator")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bp = root / "import/black-parrot"
    command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert",
               "--top-module", "prefetch_mshr_table_tb", "--Mdir", str(out / "obj"),
               "-j", "2", "-Wno-fatal", str(bp / "bp_me/src/v/cce/bp_prefetch_mshr_table.sv"),
               str(root / "testing/rtl/prefetch_mshr_table_tb.sv"),
               str(root / "testing/rtl/prefetch_mshr_table_driver.cpp")]
    with (out / "build.log").open("w") as log:
        subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
    result = subprocess.run([str(out / "obj/Vprefetch_mshr_table_tb")], cwd=out,
                            text=True, capture_output=True, check=True)
    if "[PREFETCH-MSHR] PASS:" not in result.stdout:
        raise RuntimeError("prefetch table regression completed without PASS marker")
    (out / "run.log").write_text(result.stdout)
    print(result.stdout, end="")


if __name__ == "__main__":
    main()
