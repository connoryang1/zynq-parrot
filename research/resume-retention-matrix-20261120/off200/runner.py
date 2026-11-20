#!/usr/bin/env python3
"""Run synthetic nonresident-prefix controls on one already built full-core model.

Invoke separately for capture on/off and latency 40/200, after clean sequential
model builds. Reuse the first session's ELF with --elf-from for exact controls.
No Linux or FPGA performance claim follows from these simulated cycle counts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TEST = "mt_context_resume_prefix_benchmark"
MODEL = "Vbsg_nonsynth_zynq_testbench"
SCOPE = "Synthetic full-core nonresident instruction-prefix study; not Linux or FPGA performance."


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(path):
    return {"path": str(path.resolve()), "sha256": sha256(path), "bytes": path.stat().st_size}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def copy_verified(source, target):
    expected = sha256(source)
    shutil.copy2(source, target)
    if sha256(source) != expected or sha256(target) != expected:
        raise ValueError(f"source changed while archiving: {source}")
    return record(target)


def model_identity(directory, build_log, capture, latency):
    """Check ifdef semantics and the maintained model stamp before any run."""
    expected = (f".build_config-nt2-nc4-cfge_bp_custom_cfg-trace1"
                f"-axipipe-lat{latency}-q4" + ("-icapture" if capture == "on" else ""))
    stamps = sorted(path.name for path in (directory / "obj_dir").glob(".build_config-*"))
    if stamps != [expected]:
        raise ValueError(f"wrong or ambiguous model stamps: {stamps}; expected {expected}")
    lines = build_log.read_text(errors="replace").splitlines()
    commands = [line for line in lines if "--cc" in line and "--trace-fst" in line
                and re.search(r"(?:^|/)verilator(?:\s|$)", line)]
    command_source = {"kind": "closed-build-log", **record(build_log)}
    if not commands:
        # Verilator's tee build.log omits Make's echoed invocation. Its own
        # dependency manifest retains the actual argument record, independent
        # of stdout capture; preserve that record rather than inventing a log.
        verfiles = directory / "obj_dir" / (MODEL + "__verFiles.dat")
        if not verfiles.is_file():
            raise ValueError("build log has no command and Verilator command manifest is missing")
        commands = re.findall(r'^C "(.*)"\s*$', verfiles.read_text(errors="strict"), re.M)
        command_source = {"kind": "verilator-command-record", **record(verfiles)}
    if len(commands) != 1:
        raise ValueError("build log must contain one exact traced Verilator command")
    if "--cc" not in commands[0].split() or "--trace-fst" not in commands[0].split():
        raise ValueError("Verilator command record must enable full-core compilation and FST tracing")
    defines = {}
    for name, value in re.findall(r"\+define\+([A-Za-z_][A-Za-z_0-9]*)(?:=([^\s]+))?", commands[0]):
        defines[name] = value or "1"
    required = {"BP_NUM_THREADS": "2", "BP_NUM_CONTEXTS": "4",
                "BP_CUSTOM_BASE_CFG": "bp_unicore_zynqparrot_cfg_p",
                "HP0_DATA_WIDTH": "32", "ACLK_MHZ": "20",
                "BP_AXI_MEM_READ_LATENCY": str(latency), "BP_AXI_MEM_READ_QUEUE_DEPTH": "4"}
    if any(defines.get(name) != value for name, value in required.items()):
        raise ValueError(f"build command topology/latency/depth mismatch: {required}")
    if "BP_AXI_MEM_PIPELINED" not in defines:
        raise ValueError("model does not enable the pipelined memory responder")
    # Presence enables an RTL `ifdef even when the provided value is zero.
    if ("BP_ICACHE_REPLAY_DEMAND_CAPTURE" in defines) != (capture == "on"):
        raise ValueError("build command capture mode does not match requested control")
    if not (directory / "obj_dir" / MODEL).is_file():
        raise ValueError("completed model binary is missing")
    return {"stamp": expected, "verilator_command": commands[0],
            "verilator_command_source": command_source, "defines": defines,
            "physical_threads": 2, "logical_contexts": 4, "trace": "FST",
            "capture": capture, "configured_axi_memory_latency_ticks": latency,
            "memory_queue_depth": 4, "axi_data_width_bits": 32, "aclk_mhz": 20,
            "memory_return_pacing": "unchanged model defaults"}


def execute(command, cwd, log, env=None, host_timeout=None, simulator=False):
    with log.open("w") as transcript:
        completed = subprocess.run(command, cwd=cwd, env=env, stdout=transcript,
                                   stderr=subprocess.STDOUT, timeout=host_timeout,
                                   preexec_fn=(lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
                                   if simulator else None)
    return completed.returncode


def guest_metrics(text, mode, address):
    text = text.replace("\r", "")
    values = {}
    for label in ("Mode", "Prefix operations", "Resume cycles", "Prefix checksum"):
        found = re.findall(r"^" + re.escape(label) + r":\s*(0x[0-9a-fA-F]+)\s*$", text, re.M)
        if len(found) != 1:
            raise ValueError(f"expected one guest {label} result")
        values[label] = int(found[0], 16)
    if values["Mode"] != mode or values["Prefix operations"] != 0x60 or values["Prefix checksum"] != 0x60:
        raise ValueError("mode/operation/checksum does not match the unchanged benchmark")
    patches = re.findall(r"runtime patch address=(0x[0-9a-fA-F]+) value=(0x[0-9a-fA-F]+)", text)
    if len(patches) != 1 or tuple(int(value, 16) for value in patches[0]) != (address, mode):
        raise ValueError("missing or mismatched post-NBF runtime patch")
    if values["Resume cycles"] <= 0:
        raise ValueError("invalid complete prefix timing")
    return {"mode": mode, "resume_core_global_cycles": values["Resume cycles"],
            "counter": "CSR 0xCC0 core global cycles", "checksum": "0x60"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--capture", choices=("on", "off"), required=True)
    parser.add_argument("--latency", type=int, choices=(40, 200), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--modes", type=int, choices=range(4), nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--elf-from", type=Path, help="first session.json, binding one exact ELF and compiler command")
    parser.add_argument("--toolchain", type=Path, default=Path("/home/coyang/zynq-parrot/install"))
    parser.add_argument("--native-timeout", type=int, choices=(240, 600), default=240)
    args = parser.parse_args(argv)
    if len(set(args.modes)) != len(args.modes):
        parser.error("each mode may appear only once")
    directory, output = args.model_dir.resolve(), args.output.resolve()
    if output.exists():
        parser.error("output must be new; retained evidence is never overwritten")
    identity = model_identity(directory, args.build_log, args.capture, args.latency)
    output.mkdir(parents=True)
    state = {"scope": SCOPE, "state": "preparing", "model": identity, "runs": []}
    manifest = output / "session.json"
    save(manifest, state)
    try:
        # Archive the completed model before any software run or later reuse.
        model_dir = output / "model"
        model_dir.mkdir()
        state["model"]["binary"] = copy_verified(directory / "obj_dir" / MODEL, model_dir / MODEL)
        state["model"]["build_log"] = copy_verified(args.build_log, model_dir / "build.log")
        command_source = state["model"]["verilator_command_source"]
        snapshot = model_dir / (MODEL + "__verFiles.dat" if command_source["kind"] == "verilator-command-record"
                                else "build.log")
        if not snapshot.exists():
            copy_verified(Path(command_source["path"]), snapshot)
        if sha256(snapshot) != command_source["sha256"]:
            raise ValueError("model command provenance changed before archival")
        command_source["original_path"] = command_source["path"]
        command_source["path"] = str(snapshot.resolve())
        copy_verified(directory / "obj_dir" / identity["stamp"], model_dir / identity["stamp"])
        copy_verified(Path(__file__).resolve(), output / "runner.py")
        for name, location in (("top", ROOT), ("blackparrot", ROOT / "import/black-parrot")):
            revision = subprocess.check_output(["git", "-C", str(location), "rev-parse", "HEAD"], text=True).strip()
            state[name + "_revision"] = revision
            diff = subprocess.check_output(["git", "-C", str(location), "diff", "--binary"])
            (output / (name + ".diff")).write_bytes(diff)

        program = output / "program"
        program.mkdir()
        elf = program / "benchmark.riscv"
        source = ROOT / "testing" / (TEST + ".c")
        archived_source = copy_verified(source, program / (TEST + ".c"))
        if args.elf_from:
            earlier = json.loads(args.elf_from.read_text())
            previous = earlier["program"]
            supplied = Path(previous["elf"]["path"])
            if sha256(supplied) != previous["elf"]["sha256"] or sha256(source) != previous["source"]["sha256"]:
                raise ValueError("shared ELF or benchmark source changed")
            copy_verified(supplied, elf)
            compile_command = previous["compile_command"]
            state["elf_provenance"] = record(args.elf_from)
        else:
            install = args.toolchain.resolve()
            compile_command = [str(install / "bin/riscv64-unknown-elf-gcc"), "-O2",
                               "-I" + str(ROOT / "software/include"),
                               "-I" + str(install / "riscv64-unknown-elf/include"),
                               "--specs=" + str(install / "riscv64-unknown-elf/lib/dramfs.specs"),
                               "--specs=" + str(install / "riscv64-unknown-elf/lib/perch.specs"),
                               "-DNUM_THREADS=2", "-DBP_NUM_THREADS=2", "-DBP_NUM_CONTEXTS=4",
                               "-DBENCH_DIAGNOSTIC=0", "-DBENCH_BARRIER=0", "-o", str(elf), str(source)]
            save(program / "compile-command.json", compile_command)
            if execute(compile_command, ROOT, program / "compile.log"):
                raise ValueError("benchmark compilation failed")
        nm = args.toolchain.resolve() / "bin/riscv64-unknown-elf-nm"
        symbols = subprocess.check_output([str(nm), "-n", str(elf)], text=True)
        (program / "nm.txt").write_text(symbols)
        matches = re.findall(r"^([0-9a-fA-F]+) [Dd] benchmark_mode$", symbols, re.M)
        if len(matches) != 1:
            raise ValueError("benchmark_mode must be a unique initialized data symbol")
        address = int(matches[0], 16)
        objcopy = args.toolchain.resolve() / "bin/riscv64-unknown-elf-objcopy"
        mem = program / "prog.mem"
        if execute([str(objcopy), "-O", "verilog", str(elf), str(mem)], ROOT, program / "objcopy.log"):
            raise ValueError("ELF-to-memory conversion failed")
        mem.write_text(mem.read_text().replace("@8", "@0"))
        nbf = program / "prog.nbf"
        nbf_command = [sys.executable, str(ROOT / "import/black-parrot/bp_common/software/py/nbf.py"),
                       "--skip_zeros", "--keep_mem_zeros", "--mem", str(mem), "--ncpus", "1"]
        with nbf.open("w") as generated:
            subprocess.run(nbf_command, stdout=generated, check=True)
        if sha256(source) != archived_source["sha256"]:
            raise ValueError("benchmark source changed during preparation")
        state["program"] = {"elf": record(elf), "source": archived_source,
                            "compile_command": compile_command, "nbf": record(nbf), "mem": record(mem),
                            "nbf_command": nbf_command, "benchmark_mode_address": hex(address)}
        save(program / "compile-command.json", compile_command)
        save(manifest, state)
        for mode in args.modes:
            runtime = output / f"mode{mode}"
            runtime.mkdir()
            # Fresh per-mode working directories cannot consume stale prog.*.
            copied_elf = copy_verified(elf, runtime / "prog.riscv")
            copied_nbf = copy_verified(nbf, runtime / "prog.nbf")
            patch = {"RUN_INPUT": str(mode), "RUN_INPUT_ADDR": hex(address),
                     "BSG_RUNTIME_PATCH_VALUE": str(mode), "BSG_RUNTIME_PATCH_ADDR": hex(address),
                     "BSG_TRACE_TIMEOUT_S": str(args.native_timeout)}
            save(runtime / "runtime-patch.json", patch)
            command = [state["model"]["binary"]["path"], "+c_args=prog.nbf", "+bsg_trace=dump.fst"]
            save(runtime / "command.json", command)
            env = os.environ.copy()
            env.update({key: value for key, value in patch.items() if key.startswith("BSG_")})
            env["LD_LIBRARY_PATH"] = str(args.toolchain.resolve() / "lib") + ":" + env.get("LD_LIBRARY_PATH", "")
            log = runtime / "run.log"
            code = execute(command, runtime, log, env, args.native_timeout + 180, simulator=True)
            # Invoke the maintained gate for its exact post-PASS exit policy.
            check = [sys.executable, str(ROOT / "testing/check_run.py"), str(log),
                     "--test", TEST, "--exit-code", str(code)]
            passed = execute(check, ROOT, runtime / "acceptance.log") == 0
            row = {"mode": mode, "exit_code": code, "elf": copied_elf, "nbf": copied_nbf,
                   "patch": patch, "patch_file": record(runtime / "runtime-patch.json"),
                   "log": record(log), "acceptance": record(runtime / "acceptance.log"), "state": "failed"}
            fst = runtime / "dump.fst"
            if fst.is_file():
                row["fst"] = record(fst)  # Child exited; retain closed trace before next mode.
            state["runs"].append(row)
            save(manifest, state)
            if not passed or "fst" not in row or row["fst"]["bytes"] == 0:
                raise ValueError(f"mode {mode} failed transcript/closed-waveform acceptance")
            row.update(guest_metrics(log.read_text(errors="replace"), mode, address), state="pass")
            print(f"{SCOPE} capture={args.capture} axi_latency_ticks={args.latency} mode={mode} "
                  f"resume_core_global_cycles={row['resume_core_global_cycles']} checksum=0x60", flush=True)
            save(manifest, state)
        state["state"] = "complete"
    except BaseException as error:
        state.update(state="failed", error=repr(error))
        raise
    finally:
        save(manifest, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
