#!/usr/bin/env python3
"""Crosscompile only the fixture and check linked payload/layout; no model run."""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INSTALL = Path("/home/coyang/zynq-parrot/install")
SOURCE = ROOT / "testing/rtl/retained_advisory_full_line_test.c"
ELF = HERE / "retained_advisory_full_line_test.elf"


def binding(path):
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def tool(name):
    return INSTALL / "bin" / ("riscv64-unknown-elf-" + name)


def main():
    command = [tool("gcc"), "-O2", "-Wall", "-Wextra", "-Werror",
               "-I" + str(ROOT / "software/include"),
               "-I" + str(INSTALL / "riscv64-unknown-elf/include"),
               "--specs=" + str(INSTALL / "riscv64-unknown-elf/lib/dramfs.specs"),
               "--specs=" + str(INSTALL / "riscv64-unknown-elf/lib/perch.specs"),
               "-DBP_FPGA_PROGRAM=1", "-DNUM_THREADS=2", "-DBP_NUM_THREADS=2", "-DBP_NUM_CONTEXTS=4",
               "-o", ELF, SOURCE]
    result = subprocess.run(list(map(str, command)), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=30)
    (HERE / "compile.log").write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError("fixture compile failed; see compile.log")
    nm = subprocess.check_output([tool("nm"), "-n", "-S", ELF], text=True)
    (HERE / "symbols.log").write_text(nm)
    symbols = {}
    for line in nm.splitlines():
        fields = line.split()
        if len(fields) == 4:
            addr, size, kind, name = fields
            symbols[name] = (int(addr, 16), int(size, 16), kind)
        elif len(fields) == 3:
            addr, kind, name = fields
            symbols[name] = (int(addr, 16), 0, kind)
    raw = ELF.read_bytes()
    phoff = struct.unpack_from("<Q", raw, 32)[0]
    phsize, phcount = struct.unpack_from("<HH", raw, 54)
    headers = [struct.unpack_from("<IIQQQQQQ", raw, phoff + n * phsize) for n in range(phcount)]

    def memory(addr, size):
        for p in headers:
            if p[0] == 1 and p[3] <= addr and addr + size <= p[3] + p[5]:
                offset = p[2] + addr - p[3]
                return raw[offset:offset + size]
        raise AssertionError("requested bytes not file-backed")

    target_addresses = []
    for n in range(10):
        addr, size, _ = symbols[f"retained_advisory_code{n}"]
        assert size == 64 and addr % 4096 == 0
        expected = [((101 + n) << 20) | 0x513]
        expected += [(k << 20) | (10 << 15) | 0x513 for k in range(1, 15)]
        expected += [0x8067]
        assert memory(addr, 64) == struct.pack("<16I", *expected)
        if n:
            assert addr - target_addresses[-1] == 4096
            assert not any(memory(target_addresses[-1] + 64, 4096 - 64))
        target_addresses.append(addr)
    hot = [symbols[name] for name in ("fail", "wait_idle", "main")]
    page = hot[0][0] & ~4095
    assert all(page == (a & ~4095) and a % 4096 >= 128 and (a + s - 1) // 4096 == page // 4096
               for a, s, _ in hot)
    data, size, kind = symbols["retained_advisory_data"]
    assert data % 4096 == 0 and size == 10 * 4096 and kind.lower() == "d"
    words = [0xd176a0943bf52e81 ^ (0x1728394a5b6c7d8 * (w + 1)) for w in range(8)]
    assert memory(data, 64) == struct.pack("<8Q", *words)
    for n in range(1, 10):
        assert struct.unpack("<Q", memory(data + n * 4096, 8))[0] == n + 1
    for n in range(10):
        first_unused = 64 if not n else 8
        assert not any(memory(data + n * 4096 + first_unused, 4096 - first_unused))
    for label in ("submit", "demand", "completed"):
        addr = symbols["retained_advisory_" + label][0]
        assert page == addr & ~4095 and addr % 4096 >= 128
    disassembly = subprocess.check_output([tool("objdump"), "-d", ELF], text=True)
    (HERE / "disassembly.log").write_text(disassembly)
    # These are static opcode counts, not evidence of actual retired commands.
    assert len(re.findall(r"csrw\s+0x7c0,", disassembly)) == 1
    assert len(re.findall(r"csrw\s+0x9c0,", disassembly)) == 1
    report = {"state": "crosscompiled and static layout/payload checks PASS; execution pending",
              "source": binding(SOURCE), "build_script": binding(Path(__file__)),
              "command": list(map(str, command)), "compiler": binding(tool("gcc")),
              "specs": [binding(INSTALL / "riscv64-unknown-elf/lib" / name)
                        for name in ("dramfs.specs", "perch.specs")],
              "elf": binding(ELF), "targets": target_addresses,
              "hot_page": page, "hot_end": max(a + s for a, s, _ in hot),
              "data_address": data, "data_bytes": size,
              "markers": {name: symbols["retained_advisory_" + name][0]
                          for name in ("submit", "demand", "completed")},
              "logs": [binding(HERE / name) for name in
                       ("compile.log", "symbols.log", "disassembly.log")],
              "required_runtime_gate": "closed FST: true I/D retained backend hits, all eight normal-L1 refill beats, checked completion",
              "limits": ["No model execution or target result", "No retry on dropped/unsampled advisory hint",
                         "CSR busy/ready snapshots are not global lower-memory drain proof",
                         "No performance, application-capacity or FPGA claim"]}
    (HERE / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: static linked full64B functions, sparse data and hot-code layout; no execution")


if __name__ == "__main__":
    main()
