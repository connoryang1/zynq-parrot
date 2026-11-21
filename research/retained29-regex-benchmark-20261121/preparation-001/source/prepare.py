#!/usr/bin/env python3
"""Standalone regex derivative host/link gates; no Makefile or target execution."""
import difflib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "linux-tests"))
import run_retained29_session_v2 as frozen_protocol
import derive


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


abi = load(ROOT / "research/regex-natural-demand-20261121/prepare.py", "accepted_regex_abi")
helpers = load(ROOT / "research/retained29-regex-20261121/prepare.py", "module_preparation")
binding = helpers.binding


def main():
    for n in range(1,1000):
        out = HERE / ("preparation-%03d" % n)
        try: out.mkdir(); break
        except FileExistsError: continue
    else: raise RuntimeError("no fresh preparation directory")
    own = [derive.NEW, ROOT / "linux-tests/retained29_regex_workload.h",
           ROOT / "linux-tests/test_retained29_regex_benchmark.py", HERE / "derive.py", Path(__file__).resolve()]
    reused = [ROOT / "linux-tests/test_retained29_benchmark.py", ROOT / "linux-tests/test_resume_resource_accounting.py"]
    frozen = [ROOT / name for name in (*frozen_protocol.p.SOURCE_FILES, *frozen_protocol.NEW_SOURCES)]
    assert len(frozen) == 17
    frozen += [ROOT / "linux-tests/Makefile"]
    inputs = {str(p):binding(p) for p in dict.fromkeys(own + reused + frozen)}
    source = out / "source"; source.mkdir()
    for p in own + reused: shutil.copyfile(p, source / p.name)
    provenance = derive.verify()
    (out / "provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    (out / "plain-to-regex.patch").write_text("".join(difflib.unified_diff(
        derive.BASE.read_text().splitlines(True), derive.NEW.read_text().splitlines(True),
        fromfile=str(derive.BASE), tofile=str(derive.NEW))))
    module_gate = ROOT / "research/retained29-regex-20261121/preparation-001/manifest.json"
    record = dict(state="preparing", inputs=inputs, frozen_runtime_sources=len(frozen)-1,
                  provenance=binding(out / "provenance.json"), commands=[], module_preparation=binding(module_gate))

    def run(label, command, cwd=ROOT, env=None):
        command = list(map(str,command))
        result = subprocess.run(command,cwd=str(cwd),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        log = out / (label+".log"); log.write_bytes(result.stdout)
        record["commands"].append(dict(label=label,argv=command,cwd=str(cwd),returncode=result.returncode,log=binding(log)))
        assert result.returncode == 0, (label,result.returncode,result.stdout.decode(errors="replace"))
        return result.stdout.decode()

    try:
        module = json.loads(module_gate.read_text())
        assert module["state"] == "PASS-host-oracle-ASAN-UBSAN-and-RV64-link-only"
        assert module["inputs"][str(own[1])] == binding(own[1])
        env = dict(os.environ,LC_ALL="C",PYTHONDONTWRITEBYTECODE="1")
        env.pop("R29_REGEX_SANITIZE",None)
        run("host-protocol",["python3","-B","-m","unittest","-v","test_retained29_regex_benchmark.RegexBenchmarkTests"],source,env)
        san = dict(env,R29_REGEX_SANITIZE="1",ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                   UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        run("host-protocol-sanitizers",["python3","-B","-m","unittest","-v","test_retained29_regex_benchmark.RegexBenchmarkTests"],source,san)
        members = abi.accepted_members()
        sysroot = Path(run("sysroot",[abi.CC,"-print-sysroot"]).strip())
        libc = abi.SDK / "target/lib/libc.so.6"
        loader = abi.SDK / "target/lib/ld-linux-riscv64-lp64d.so.1"
        for p,name in ((libc,"libc.so.6"),(loader,"ld-linux-riscv64-lp64d.so.1")):
            assert binding(p)["sha256"] == members["lib/"+name]["sha256"]
            assert abi.allocated_sections(p) == abi.allocated_sections(sysroot / "lib" / name)
        assert binding(libc) == module["accepted_runtime_ABI"]["libc"]
        assert binding(loader) == module["accepted_runtime_ABI"]["loader"]
        binary = out / "scheduler_retained29_regex_benchmark_dynamic"
        flags = ["-std=c11","-O2","-Wall","-Wextra","-Werror","-march=rv64imafdc","-mabi=lp64d","-fno-pie","-no-pie"]
        command = [abi.CC,*flags,source / derive.NEW.name,"-o",binary]
        run("cross-build",command)
        repeat = out / "reproducible_dynamic"
        run("cross-rebuild",[abi.CC,*flags,source / derive.NEW.name,"-o",repeat])
        assert repeat.read_bytes() == binary.read_bytes()
        dynamic = run("readelf",["readelf","-h","-l","-d","-V","-Ws",binary])
        symbols = run("accepted-runtime-symbols",["readelf","-Ws",libc,loader])
        needed = re.findall(r"\(NEEDED\).*?\[(.*?)\]",dynamic)
        assert needed == ["libc.so.6","ld-linux-riscv64-lp64d.so.1"]
        assert "RISC-V" in dynamic and "/lib/ld-linux-riscv64-lp64d.so.1" in dynamic
        imports = sorted(set(re.findall(r"\bUND\s+(\S+@GLIBC_\S+)",dynamic)))
        for symbol in imports: assert symbol in symbols or symbol.replace("@","@@",1) in symbols,symbol
        for name in ("regcomp","regexec","regfree"):assert name+"@GLIBC_2.27" in imports
        assert all("HOST_VERIFY" not in line for line in run("production-strings",["strings",binary]).splitlines())
        assert "RESUME_RETAINED29_REGEX_PASS" in (out / "production-strings.log").read_text()
        assert inputs == {path:binding(path) for path in inputs},"input changed during gate"
        record.update(state="PASS-real-regex-host-protocol-and-RV64-link-only",elf=binding(binary),
            rebuilt_elf=binding(repeat),reproducible_bytes=True,needed=needed,versioned_imports=imports,
            accepted_runtime=dict(cpio=binding(abi.CPIO),libc=binding(libc),loader=binding(loader),
                                  members=members,allocated_sections_match_sysroot=True,
                                  public_ABI_preparation=module["accepted_runtime_ABI"]),
            sanitizer_environment={k:san[k] for k in ("ASAN_OPTIONS","UBSAN_OPTIONS","R29_REGEX_SANITIZE")},
            limits=["No RV64/model/FPGA execution or performance evidence",
                    "Host libc DSO uninstrumented; LSan disabled; no library-internal leak proof",
                    "Corpus excludes descriptors, regex lazy/compiled storage, allocator, code and stack; resource admission remains required",
                    "Same matched controller lifecycle as plain, not an unmodified deployment baseline",
                    "No generated advisory source; advisory masks remain source-none controls; busy scope only UCE/client/backend"])
    except BaseException as error:
        record.update(state="FAILED-PREPARATION-NOT-TARGET-EVIDENCE",error=repr(error));raise
    finally:
        (out / "manifest.json").write_text(json.dumps(record,indent=2)+"\n")
        print(out,record["state"])


if __name__ == "__main__":main()
