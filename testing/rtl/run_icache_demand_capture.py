#!/usr/bin/env python3
"""Run traced ordinary-demand capacity controls with capture both off and on."""
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
    args = parser.parse_args()
    bp = root / "import/black-parrot"
    bsg = bp / "external/basejump_stl"
    includes = [bsg / name for name in ("bsg_misc", "bsg_cache", "bsg_mem", "bsg_dataflow", "bsg_noc")]
    includes += [bp / name / "src/include" for name in ("bp_common", "bp_fe")]
    libraries = [bsg / name for name in ("bsg_misc", "bsg_dataflow", "bsg_mem")]
    libraries += [bp / "bp_common/src/v"]
    sources = [bp / "bp_common/src/include/bp_common_pkg.sv",
               bp / "bp_fe/src/include/bp_fe_pkg.sv",
               bp / "bp_fe/src/v/bp_fe_icache.sv",
               Path(__file__).with_name("icache_demand_capture_tb.sv")]
    driver = Path(__file__).with_name("icache_demand_capture_driver.cpp")
    for enabled in (0, 1):
        out = (args.out / ("enabled" if enabled else "disabled")).resolve()
        out.mkdir(parents=True, exist_ok=True)
        command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert",
                   "--trace-fst", "--top-module", "icache_demand_capture_tb", "--prefix",
                   "Vicache_demand_capture", "--Mdir", str(out / "obj"), "-j", "2",
                   "-Wno-fatal", "-MAKEFLAGS", "VM_PARALLEL_BUILDS=0",
                   f"-Gcapture_enabled_p={enabled}",
                   "-CFLAGS", f"-DCAPTURE_ENABLED={enabled}"]
        command += [f"+incdir+{path}" for path in includes]
        for path in libraries:
            command += ["-y", str(path)]
        command += [str(path) for path in sources] + [str(driver)]
        (out / "build-command.json").write_text(json.dumps(command, indent=2) + "\n")
        with (out / "build.log").open("w") as log:
            subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        with (out / "run.log").open("w") as log:
            subprocess.run([str(out / "obj/Vicache_demand_capture")], cwd=out,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
        result = (out / "run.log").read_text()
        if "[ICACHE-DEMAND-CAPTURE] PASS:" not in result:
            raise RuntimeError("unit test exited without its acceptance marker")
        dependencies = set(sources + [driver, Path(__file__).resolve()])
        for line in (out / "obj/Vicache_demand_capture__verFiles.dat").read_text().splitlines():
            if line.startswith("S "):
                dependencies.add(Path(shlex.split(line)[-1]))
        verification = {
            "scope": "Standalone demand-populated I replay capacity; no full-core/FPGA acceptance",
            "capture_enabled": bool(enabled),
            "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in sorted(dependencies)},
            "artifact_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (out / "run.log", out / "icache-demand-capture.fst",
                                             out / "obj/Vicache_demand_capture")},
            "passed": True,
        }
        (out / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
        print(result, end="")


if __name__ == "__main__":
    main()
