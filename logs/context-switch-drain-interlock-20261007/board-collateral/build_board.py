#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

repo = Path(__file__).resolve().parents[3]
out = Path(__file__).resolve().parent
prior = repo / "logs/nonblocking-prefetch-20260908/board-collateral"
tool = repo / "install"
cc = tool / "bin/riscv64-unknown-elf-gcc"
commands = []


def run(args, stdout=None):
    args = [str(arg) for arg in args]
    commands.append(args)
    print(" ".join(args), flush=True)
    if stdout is None:
        subprocess.run(args, check=True)
    else:
        with stdout.open("w") as stream:
            subprocess.run(args, stdout=stream, check=True)


(out / "crt").mkdir(exist_ok=True)
(out / "source").mkdir(exist_ok=True)
for name in ["crt0.S", "crtmain.S", "tls.c", "traps.c", "main.c",
             "asm.h", "encoding.h"]:
    shutil.copy2(prior / "crt" / name, out / "crt" / name)
shutil.copy2(prior / "mt_fpga_early_start.S", out / "mt_fpga_early_start.S")
assert (out / "mt_fpga_early_start.S").read_bytes() == subprocess.check_output(
    ["git", "show", "e4242c1c:testing/mt_fpga_early_start.S"], cwd=repo)
for source in [repo / "testing/mt_ctxtsw_store_handoff_benchmark.c",
               repo / "testing/mt_seed.h"]:
    shutil.copy2(source, out / "source" / source.name)
shutil.copy2(repo / "import/black-parrot/bp_common/software/py/nbf.py",
             out / "nbf.py")

base = [cc, "-I" + str(out / "crt"), "-mcmodel=medany", "-mstrict-align"]
for name, source, flags in [
        ("early", out / "mt_fpga_early_start.S", ["-D__ASSEMBLY__"]),
        ("crt0", out / "crt/crt0.S",
         ["-D__ASSEMBLY__", "-D_start=dramfs_start", "-U__riscv_flen"]),
        ("crtmain", out / "crt/crtmain.S", ["-D__ASSEMBLY__"])]:
    run(base + ["-c", source, "-o", out / "crt" / (name + ".o")] + flags)
for name in ["tls", "traps", "main"]:
    run(base + ["-c", out / "crt" / (name + ".c"), "-o",
                out / "crt" / (name + ".o"), "-fno-common", "-fno-builtin",
                "-nostdlib", "-nostartfiles"])
crt = out / "crt/dramfs_integer_crt0.o"
run([tool / "bin/riscv64-unknown-elf-ld", "-r", "-o", crt] +
    [out / "crt" / (name + ".o")
     for name in ["early", "crt0", "crtmain", "tls", "traps", "main"]])

name = "mt_ctxtsw_store_handoff_benchmark"
elf = out / (name + "_fpga.riscv")
mem = out / (name + "_fpga.mem")
nbf = out / (name + "_fpga.nbf")
run([cc, "-o", elf, crt, out / "source" / (name + ".c"), "-O2",
     "-I" + str(out / "source"),
     "-I" + str(tool / "riscv64-unknown-elf/include"),
     "--specs=" + str(tool / "riscv64-unknown-elf/lib/dramfs.specs"),
     "--specs=" + str(tool / "riscv64-unknown-elf/lib/perch.specs"),
     "-DNUM_THREADS=2", "-DBP_NUM_THREADS=2", "-DBP_NUM_CONTEXTS=10",
     "-DBP_FPGA_PROGRAM", "-nostartfiles"])
run([tool / "bin/riscv64-unknown-elf-objcopy", "-O", "verilog", elf, mem])
mem.write_text(mem.read_text().replace("@8", "@0"))
run(["python3", out / "nbf.py", "--skip_zeros", "--config", "--debug",
     "--mem", mem, "--ncpus", "1"], nbf)
run([tool / "bin/riscv64-unknown-elf-objdump", "-dr", elf],
    out / (name + ".disassembly"))

(out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
archive = [path for path in out.rglob("*")
           if path.is_file() and path.name != "manifest.json"]
manifest = {
    "top_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
    "black_parrot_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo / "import/black-parrot",
        text=True).strip(),
    "banks": 2,
    "contexts": 10,
    "sha256": {str(path.relative_to(out)): digest(path) for path in archive},
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
