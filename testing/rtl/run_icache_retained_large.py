#!/usr/bin/env python3
"""Clean real-I-cache + shared-BRAM full-payload capacity and cancellation gates."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--bp", type=Path, default=root / "import/black-parrot")
    parser.add_argument("--lines", type=int, nargs="+", default=[64, 128, 256, 512, 1024])
    parser.add_argument("--verilator", type=Path,
                        default=Path("/home/coyang/zynq-parrot/install/bin/verilator"))
    args = parser.parse_args()
    if len(set(args.lines)) != len(args.lines) or any(n < 64 for n in args.lines):
        parser.error("capacities must be unique and at least 64 actual full lines")
    bp = args.bp.resolve()
    bsg = bp / "external/basejump_stl"
    includes = [bsg / n for n in ("bsg_misc", "bsg_cache", "bsg_mem", "bsg_dataflow", "bsg_noc")]
    includes += [bp / n / "src/include" for n in ("bp_common", "bp_fe")]
    libraries = [bsg / n for n in ("bsg_misc", "bsg_dataflow", "bsg_mem")]
    libraries += [bp / "bp_common/src/v"]
    sources = [bp / "bp_common/src/include/bp_common_pkg.sv", bp / "bp_fe/src/include/bp_fe_pkg.sv",
               bp / "bp_common/src/v/bp_retained_line_store.sv",
               bp / "bp_fe/src/v/bp_fe_icache_retained_bram.sv",
               bp / "bp_fe/src/v/bp_fe_icache.sv",
               Path(__file__).resolve().with_name("icache_retained_large_tb.sv")]
    driver = Path(__file__).resolve().with_name("icache_retained_large_driver.cpp")
    initial = {str(p): sha(p) for p in sources + [driver, Path(__file__).resolve()]}
    args.out.mkdir(parents=True, exist_ok=False)
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=False)
    for lines in args.lines:
        out = (args.out / str(lines)).resolve(); out.mkdir()
        command = [str(args.verilator), "--cc", "--exe", "--build", "--assert", "--trace-fst",
                   "--top-module", "icache_retained_large_tb", "--prefix", "Vicache_retained_large",
                   "--Mdir", str(out / "obj"), "-j", "2", "-Wno-fatal",
                   "-MAKEFLAGS", "VM_PARALLEL_BUILDS=0", "-Gretained_lines_p=" + str(lines)]
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
                subprocess.run([str(out / "obj/Vicache_retained_large"), str(lines)], cwd=out,
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
            if "[ICACHE-RETAINED-LARGE] PASS:" not in (out / "run.log").read_text():
                raise RuntimeError("missing full I-cache acceptance marker")
            for path, digest in initial.items():
                if sha(Path(path)) != digest:
                    raise RuntimeError("source changed during capacity verification: " + path)
            dependencies = {Path(p) for p in initial}
            for record in (out / "obj/Vicache_retained_large__verFiles.dat").read_text().splitlines():
                if record.startswith("S "):
                    dependencies.add(Path(shlex.split(record)[-1]))
            result = {"passed": True, "actual_full_line_slots": lines, "actual_payload_bytes": lines*64,
                      "scope": "Directed real I-cache + shared backend only; no full-core, routed fit, FPGA or application performance acceptance",
                      "source_sha256": {str(p): sha(p) for p in sorted(dependencies)},
                      "artifact_sha256": {p.name: sha(p) for p in (out / "build-command.json", out / "build.log",
                                                                  out / "run.log", out / "icache-retained-large.fst",
                                                                  out / "obj/Vicache_retained_large")}}
            (out / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
            print((out / "run.log").read_text(), end="", flush=True)
        except (subprocess.SubprocessError, OSError, RuntimeError):
            for name in ("build.log", "run.log"):
                if (out / name).exists():
                    print((out / name).read_text()[-8000:], flush=True)
            raise
        finally:
            if args.evidence:
                shutil.copytree(out, args.evidence / str(lines), ignore=shutil.ignore_patterns("obj", "core*"))


if __name__ == "__main__":
    main()
