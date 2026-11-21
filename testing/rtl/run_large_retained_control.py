#!/usr/bin/env python3
"""Clean traced 0x5c2 retirement-bank, privilege and optional-feature gates."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--bp", type=Path, default=root / "import/black-parrot")
    parser.add_argument("--verilator", type=Path,
                        default=Path("/home/coyang/zynq-parrot/install/bin/verilator"))
    args = parser.parse_args()
    bp = args.bp.resolve(); bsg = bp / "external/basejump_stl"
    includes = [bsg / n for n in ("bsg_misc", "bsg_cache", "bsg_mem", "bsg_dataflow", "bsg_noc")]
    includes += [bp / n / "src/include" for n in ("bp_common", "bp_be")]
    includes += [bp / "external/HardFloat/source", bp / "external/HardFloat/source/RISCV"]
    libraries = [bsg / n for n in ("bsg_misc", "bsg_dataflow", "bsg_mem")]
    libraries += [bp / "bp_common/src/v"]
    sources = [bp / "bp_common/src/include/bp_common_pkg.sv", bp / "bp_be/src/include/bp_be_pkg.sv",
               bp / "bp_be/src/v/bp_be_calculator/bp_be_csr.sv",
               bp / "bp_be/src/v/bp_be_csr_wrapper_mt.sv",
               bp / "bp_be/src/v/bp_be_checker/bp_be_instr_decoder.sv",
               Path(__file__).resolve().with_name("large_retained_control_tb.sv")]
    driver = Path(__file__).resolve().with_name("large_retained_control_driver.cpp")
    initial = {str(p): digest(p) for p in sources + [driver, Path(__file__).resolve()]}
    args.out.mkdir(parents=True, exist_ok=False)
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=False)
    for feature in (0, 1):
        out = (args.out / ("feature" + str(feature))).resolve(); out.mkdir()
        command = [str(args.verilator), "--cc", "--exe", "--build", "--assert", "--trace-fst",
                   "--top-module", "large_retained_control_tb", "--prefix", "Vlarge_retained_control",
                   "--Mdir", str(out / "obj"), "-j", "2", "-Wno-fatal",
                   "-MAKEFLAGS", "VM_PARALLEL_BUILDS=0", "-Gfeature_p=" + str(feature),
                   "+define+BP_CUSTOM_BASE_CFG=bp_default_cfg_p", "+define+BP_NUM_THREADS=2",
                   "+define+BP_NUM_CONTEXTS=4"]
        command += ["+incdir+" + str(p) for p in includes]
        for path in libraries:
            command += ["-y", str(path)]
        command += [str(p) for p in sources] + [str(driver)]
        (out / "build-command.json").write_text(json.dumps(command, indent=2) + "\n")
        try:
            with (out / "build.log").open("w") as log:
                subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=240)
            with (out / "run.log").open("w") as log:
                subprocess.run([str(out / "obj/Vlarge_retained_control"), str(feature)], cwd=out,
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
            if "[LARGE-RETAINED-CONTROL] PASS: feature=" + str(feature) not in (out / "run.log").read_text():
                raise RuntimeError("missing exact feature acceptance marker")
            for name, expected in initial.items():
                if digest(Path(name)) != expected:
                    raise RuntimeError("source changed during gate: " + name)
            deps = {Path(p) for p in initial}
            for line in (out / "obj/Vlarge_retained_control__verFiles.dat").read_text().splitlines():
                if line.startswith("S "):
                    deps.add(Path(shlex.split(line)[-1]))
            (out / "source").mkdir()
            snapshots = {}
            for index, path in enumerate(sources + [driver, Path(__file__).resolve()]):
                target = out / "source" / (str(index) + "-" + path.name + ".gz")
                target.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
                snapshots[str(target.relative_to(out))] = digest(target)
            report = {"passed": True, "feature_enabled": bool(feature), "physical_threads": 2,
                      "logical_contexts": 4, "csr_address": "0x5c2", "control_bits": 4,
                      "scope": "Real banked CSR wrapper and instruction decoder with cache-owned status stand-in; no complete processor, FPGA or performance acceptance",
                      "source_sha256": {str(p): digest(p) for p in sorted(deps)},
                      "source_archive_sha256": snapshots,
                      "artifact_sha256": {p.name: digest(p) for p in (out / "build-command.json", out / "build.log",
                                                                  out / "run.log", out / "large-retained-control.fst",
                                                                  out / "obj/Vlarge_retained_control")}}
            (out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
            print((out / "run.log").read_text(), end="", flush=True)
        except (subprocess.SubprocessError, OSError, RuntimeError):
            for name in ("build.log", "run.log"):
                if (out / name).exists(): print((out / name).read_text()[-8000:], flush=True)
            raise
        finally:
            if args.evidence:
                shutil.copytree(out, args.evidence / out.name, ignore=shutil.ignore_patterns("obj", "core*"))


if __name__ == "__main__":
    main()
