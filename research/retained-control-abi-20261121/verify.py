#!/usr/bin/env python3
"""Reproduce the small host/ABI build gate; never build a kernel or run a target."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SDK = Path("/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot")
KERNEL = SDK / "build/linux-6.6"
HOST = SDK / "host"
CC = HOST / "bin/riscv64-linux-gcc"
TOOLS = {
    "compiler_wrapper": (HOST / "bin/toolchain-wrapper",
        "d622d63cceefe24a106c8ff485a60bf494264323377cb50e8cac1dbdf5dfda7b"),
    "compiler_real": (HOST / "opt/ext-toolchain/bin/riscv64-buildroot-linux-gnu-gcc.br_real",
        "fb81e8ee099c785fed2eaebf966c7966802039f7469e4d21b7dd9a36ab4b9d7a"),
    "readelf": (HOST / "opt/ext-toolchain/bin/riscv64-buildroot-linux-gnu-readelf",
        "ff8a0dedbd379e0813508434c81cb05454c2f69fe7bbe72fd7f488b06233d008"),
}
READELF = TOOLS["readelf"][0]
OBJDUMP = HOST / "opt/ext-toolchain/bin/riscv64-buildroot-linux-gnu-objdump"
INPUTS = [ROOT / "linux-tests" / name for name in (
    "retained_store_probe.c", "retained_control_test_support.py",
    "test_retained_store_probe.py", "test_retained_store_kernel_patch.py",
    "kernel-patches/0027-blackparrot-icache-retention-control.patch",
    "kernel-patches/0028-blackparrot-mode14-early-only.patch",
    "kernel-patches/0029-blackparrot-retained-control.patch",
    "icache_retention_probe.c", "test_icache_retention_probe.py",
    "test_icache_retention_kernel_patch.py", "Makefile")]
INPUTS += [ROOT / "import/black-parrot" / name for name in (
    "bp_top/src/v/bp_unicore_lite.sv", "bp_be/src/v/bp_be_calculator/bp_be_csr.sv",
    "bp_me/src/v/cce/bp_uce.sv", "bp_common/src/v/bp_retained_line_store.sv")]
INPUTS += [KERNEL / name for name in (
    "kernel/sys.c", "include/uapi/linux/prctl.h", "kernel/sched/core.c",
    "arch/riscv/include/asm/asm-extable.h", "arch/riscv/include/asm/gpr-num.h",
    "include/linux/stringify.h", "arch/riscv/mm/extable.c", "arch/riscv/kernel/traps.c")]
INPUTS += [ROOT / "research/retention-kernel-20261120/accepted-rootfs/accepted-kernel_sys.c"]


def record(path):
    path = Path(path)
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def run(command, log, cwd=ROOT, env=None):
    result = subprocess.run(list(map(str, command)), cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    (HERE / log).write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}); see {log}")
    return {"argv": list(map(str, command)), "cwd": str(cwd), "exit_code": result.returncode,
            "log": record(HERE / log)}


def extable_entries(path):
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01":
        raise AssertionError("expected little-endian ELF64")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    entsize, count, names_index = struct.unpack_from("<HHH", data, 58)
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + n * entsize) for n in range(count)]
    names_section = sections[names_index]
    names = data[names_section[4]:names_section[4] + names_section[5]]
    target = [s for s in sections if names[s[0]:].split(b"\0", 1)[0] == b"__ex_table"]
    if len(target) != 1 or not target[0][5] or target[0][5] % 12:
        raise AssertionError("missing/invalid actual RISC-V exception entries")
    section = target[0]
    entries = []
    for offset in range(section[4], section[4] + section[5], 12):
        _, _, kind, regs = struct.unpack_from("<iiHH", data, offset)
        error_reg, zero_reg = regs & 31, (regs >> 5) & 31
        if kind != 3 or not error_reg or not zero_reg or error_reg == zero_reg or regs >> 10:
            raise AssertionError("bad UACCESS_ERR_ZERO/independent output encoding")
        entries.append({"type": kind, "error_register": error_reg, "zero_register": zero_reg})
    return entries


def main():
    before = [record(path) for path in INPUTS]
    tool_records = {}
    for name, (path, expected) in TOOLS.items():
        tool_records[name] = record(path)
        if tool_records[name]["sha256"] != expected:
            raise AssertionError(f"accepted compiler/tool mismatch: {name}")
    tool_records["objdump"] = record(OBJDUMP)
    snapshot = HERE / "source"
    snapshot.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "linux-tests/retained_store_probe.c", snapshot / "retained_store_probe.c")
    patch = ROOT / "linux-tests/kernel-patches/0029-blackparrot-retained-control.patch"
    shutil.copyfile(patch, snapshot / "0029-blackparrot-retained-control.diff")
    env = dict(os.environ, TMPDIR="/dev/shm", PYTHONDONTWRITEBYTECODE="1")
    host = run(["python3", "-m", "unittest", "-v", "test_retained_store_probe",
                "test_retained_store_kernel_patch", "test_icache_retention_probe",
                "test_icache_retention_kernel_patch"], "host-tests.log", ROOT / "linux-tests", env)
    flags = ["-O2", "-Wall", "-Wextra", "-Werror", "-march=rv64imafdc_zicsr_zifencei", "-mabi=lp64d"]
    binary = HERE / "retained_store_probe.elf"
    compile_probe = run([CC, *flags, "-no-pie", "-std=c11", "-o", binary,
                         snapshot / "retained_store_probe.c"], "compile.log")
    readelf = run([READELF, "-h", "-l", "-d", "-A", binary], "probe-readelf.log")
    text = (HERE / "probe-readelf.log").read_text()
    if "ELF64" not in text or "RISC-V" not in text or "EXEC (Executable file)" not in text:
        raise AssertionError("wrong probe ABI")
    if "/lib/ld-linux-riscv64-lp64d.so.1" not in text or "libz.so" in text:
        raise AssertionError("wrong dynamic loader or unexpected zlib dependency")
    # Compile only these actual functions, with the real exception-table and
    # register-number macros. linux/bits.h is unused by this macro expansion;
    # suppressing its include avoids pretending this is a configured kernel TU.
    added = "\n".join(line[1:] for line in patch.read_text().splitlines()
                      if line.startswith("+") and not line.startswith("+++"))
    helpers = "static int bp_retained_probe" + added.split("static int bp_retained_probe", 1)[1].split("#else", 1)[0]
    asm_source = snapshot / "actual-kernel-helpers.c"
    asm_source.write_text("#define CONFIG_MMU 1\n#define __LINUX_BITS_H\n"
        "#include <asm/asm-extable.h>\ntypedef unsigned long u64;\n#define ENODEV 19\n"
        "extern void preempt_disable(void);\nextern void preempt_enable(void);\n" + helpers +
        "\nint check_control(unsigned long mask) { return bp_retained_control(mask); }\n"
        "int check_status(u64 *status) { return bp_retained_status(status); }\n")
    obj = HERE / "actual-kernel-helpers.o"
    compile_asm = run([CC, *flags, "-std=gnu11", "-I" + str(KERNEL / "arch/riscv/include"),
                      "-I" + str(KERNEL / "include"), "-c", asm_source, "-o", obj], "compile-helpers.log")
    disassembly = run([OBJDUMP, "-dr", obj], "helpers-objdump.log")
    if "fence.i" in (HERE / "helpers-objdump.log").read_text():
        raise AssertionError("unexpected normal L1I invalidation in new submission")
    table = extable_entries(obj)
    if before != [record(path) for path in INPUTS]:
        raise AssertionError("bound input changed during offline validation")
    outputs = [record(path) for path in sorted(HERE.rglob("*")) if path.is_file()
               and path.name not in ("manifest.json", "verify.py", "README.md")]
    manifest = {
        "state": "host-validated-and-RV64-crosscompiled; no kernel build or target run",
        "inputs": before, "tools": tool_records,
        "prior_toolchain_reference": record(ROOT / "research/complete-policy-scope-20261120/compiled/manifest.json"),
        "verification_script": record(Path(__file__)), "host_validation": host,
        "probe_compile": compile_probe, "probe_readelf": readelf,
        "helpers_compile": compile_asm, "helpers_disassembly": disassembly,
        "actual_extable_entries": table, "outputs": outputs,
        "limits": ["No full kernel compilation or hardware illegal-CSR trap execution",
                   "Host mocks check C control flow; do not prove RTL readback or progress",
                   "Busy snapshot covers UCE/client/backend, not lower-L2/AXI/DRAM drain",
                   "Control submits clear/write; caller must bound/poll and charge both calls",
                   "Probe is correctness only; no workload benefit or deployment claim"],
    }
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("PASS: host tests, RV64 probe and actual exception-table micro-object; no target")


if __name__ == "__main__":
    main()
