#!/usr/bin/env python3
"""Run traced shared retention CSR routing and decoder privilege checks."""
import argparse
import hashlib
import json
import shlex
from pathlib import Path
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verilator", type=Path,
                        default=Path("/home/coyang/zynq-parrot/install/bin/verilator"))
    parser.add_argument("--bp", type=Path, default=Path("/home/coyang/bp-linux-retention-policy"))
    args = parser.parse_args()
    bp = args.bp.resolve()
    bsg = bp / "external/basejump_stl"
    includes = [bsg / name for name in ("bsg_misc", "bsg_cache", "bsg_mem", "bsg_dataflow", "bsg_noc")]
    includes += [bp / name / "src/include" for name in ("bp_common", "bp_be")]
    includes += [bp / "external/HardFloat/source", bp / "external/HardFloat/source/RISCV"]
    libraries = [bsg / name for name in ("bsg_misc", "bsg_dataflow", "bsg_mem")]
    libraries += [bp / "bp_common/src/v"]
    sources = [bp / "bp_common/src/include/bp_common_pkg.sv",
               bp / "bp_be/src/include/bp_be_pkg.sv",
               bp / "bp_be/src/v/bp_be_calculator/bp_be_csr.sv",
               bp / "bp_be/src/v/bp_be_csr_wrapper_mt.sv",
               bp / "bp_be/src/v/bp_be_checker/bp_be_instr_decoder.sv",
               Path(__file__).with_name("retention_csr_tb.sv")]
    driver = Path(__file__).with_name("retention_csr_driver.cpp")
    for enabled in (1,):
        out = (args.out / "runtime-policy").resolve()
        out.mkdir(parents=True, exist_ok=True)
        command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert",
                   "--trace-fst", "--top-module", "retention_csr_tb", "--prefix",
                   "Vretention_csr", "--Mdir", str(out / "obj"), "-j", "2",
                   "-Wno-fatal", "+define+BP_CUSTOM_BASE_CFG=bp_default_cfg_p",
                   "+define+BP_NUM_THREADS=2", "+define+BP_NUM_CONTEXTS=4", "-MAKEFLAGS", "VM_PARALLEL_BUILDS=0",
                   ]
        command += [f"+incdir+{path}" for path in includes]
        for path in libraries:
            command += ["-y", str(path)]
        command += [str(path) for path in sources] + [str(driver)]
        (out / "build-command.json").write_text(json.dumps(command, indent=2) + "\n")
        with (out / "build.log").open("w") as log:
            subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        with (out / "run.log").open("w") as log:
            subprocess.run([str(out / "obj/Vretention_csr")], cwd=out,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        result = (out / "run.log").read_text()
        if "[RETENTION-CSR] PASS:" not in result:
            raise RuntimeError("unit test exited without its acceptance marker")
        dependencies = set(sources + [driver, Path(__file__).resolve()])
        for line in (out / "obj/Vretention_csr__verFiles.dat").read_text().splitlines():
            if line.startswith("S "):
                dependencies.add(Path(shlex.split(line)[-1]))
        verification = {
            "scope": "Real CSR wrapper and decoder with shared status stand-in; no complete processor/FPGA acceptance",
            "physical_threads": 2,
            "logical_contexts": 4,
            "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in sorted(dependencies)},
            "artifact_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (out / "run.log", out / "retention-csr.fst",
                                             out / "obj/Vretention_csr")},
            "passed": True,
        }
        (out / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
        print(result, end="")


if __name__ == "__main__":
    main()
