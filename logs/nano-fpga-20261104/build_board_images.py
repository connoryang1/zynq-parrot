"""Build one board Nano ELF and selector-patched NBFs for all eleven modes."""

from pathlib import Path
import hashlib
import json
import subprocess


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CANONICAL = Path("/home/coyang/zynq-parrot")
TOOLS = CANONICAL / "install"
CRT = CANONICAL / "logs/real-ddr-20260923/crt/dramfs_integer_crt0.o"
NBF_TOOL = CANONICAL / "logs/real-ddr-20260923/nbf.py"
PATCH_TOOL = ROOT / "codex-skills/bp-fpga-synthesis/scripts/patch_nbf_bytes.py"
SOURCE = ROOT / "testing/mt_nano_lookup_benchmark.c"
DATA = ROOT / "testing/nano_lookup_data.h"
PREFETCH = ROOT / "software/include/bp_prefetch.h"


def run(args, stdout=None):
    print(" ".join(map(str, args)), flush=True)
    if stdout is None:
        subprocess.run(list(map(str, args)), check=True)
    else:
        with stdout.open("w") as stream:
            subprocess.run(list(map(str, args)), check=True, stdout=stream)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


elf = OUT / "mt_nano_lookup_benchmark_fpga.riscv"
mem = OUT / "mt_nano_lookup_benchmark_fpga.mem"
base_nbf = OUT / "mt_nano_lookup_benchmark_fpga.nbf"
disassembly = OUT / "mt_nano_lookup_benchmark_fpga.disassembly"

cxx = TOOLS / "bin/riscv64-unknown-elf-g++"
run([
    cxx, "-o", elf, CRT, SOURCE, "-O3", "-nostartfiles",
    f"-I{ROOT / 'software/include'}",
    f"-I{TOOLS / 'riscv64-unknown-elf/include'}",
    f"--specs={TOOLS / 'riscv64-unknown-elf/lib/dramfs.specs'}",
    f"--specs={TOOLS / 'riscv64-unknown-elf/lib/perch.specs'}",
    "-DNUM_THREADS=2", "-DBP_NUM_THREADS=2", "-DBP_NUM_CONTEXTS=10",
    "-DBP_FPGA_PROGRAM", "-std=gnu++20", "-fno-exceptions", "-fno-rtti",
    "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
    "-nodefaultlibs", "-lgcc", "-Wl,--start-group", "-lc", "-lgloss_dramfs",
    "-Wl,--end-group", "-Wl,--start-group,--whole-archive", "-lperch",
    "-Wl,--no-whole-archive,--end-group", "-lgcc",
])
run([TOOLS / "bin/riscv64-unknown-elf-objcopy", "-O", "verilog", elf, mem])
mem.write_text(mem.read_text().replace("@8", "@0"))
run(["python3", NBF_TOOL, "--skip_zeros", "--config", "--debug", "--mem", mem,
     "--ncpus", "1"], base_nbf)
run([TOOLS / "bin/riscv64-unknown-elf-objdump", "-dr", elf], disassembly)

nm = subprocess.check_output(
    [str(TOOLS / "bin/riscv64-unknown-elf-nm"), "-S", str(elf)], text=True
)
fields = next(line.split() for line in nm.splitlines()
              if line.endswith(" benchmark_mode"))
selector_address = int(fields[0], 16)
assert int(fields[1], 16) == 8

images = {}
for mode in range(11):
    selector = mode | (8 << 8)
    patch = OUT / f"selector-mode{mode}-n8.bin"
    image = OUT / f"nano-mode{mode}-n8.nbf"
    patch.write_bytes(selector.to_bytes(8, "little"))
    run(["python3", PATCH_TOOL, base_nbf, image, "--patch",
         f"{selector_address:#x}:{patch}"])
    for record in image.read_text().splitlines():
        command, address, _ = record.split("_")
        if command == "03" and int(address, 16) >= 0x1_0000_0000:
            raise SystemExit(f"out-of-range NBF write in {image.name}: {record}")
    images[image.name] = sha256(image)

manifest_paths = [SOURCE, DATA, PREFETCH, CRT, NBF_TOOL, elf, mem, base_nbf,
                  disassembly]
manifest = {
    "top_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "black_parrot_gitlink": subprocess.check_output(
        ["git", "rev-parse", "HEAD:import/black-parrot"], cwd=ROOT,
        text=True).strip(),
    "workers": 8,
    "selector_address": hex(selector_address),
    "reviewed_integer_crt_sha256": sha256(CRT),
    "candidate_nbf_tool_sha256": sha256(NBF_TOOL),
    "sha256": {str(path): sha256(path) for path in manifest_paths},
    "images": images,
}
(OUT / "board-image-manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n"
)
