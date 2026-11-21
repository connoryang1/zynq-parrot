#!/usr/bin/env python3
"""Isolated real-regex host oracle/sanitizer and accepted-libc RV64 link gate.

Never executes an RV64 ELF, target, board tool or frozen benchmark.
"""
import hashlib
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
OLD = ROOT / "research/regex-natural-demand-20261121"
MASK = (1 << 64) - 1
BASIS, PRIME = 14695981039346656037, 1099511628211


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def mix(x):
    x &= MASK
    x = ((x ^ (x >> 30)) * 0xbf58476d1ce4e5b9) & MASK
    x = ((x ^ (x >> 27)) * 0x94d049bb133111eb) & MASK
    return x ^ (x >> 31)


def hash_bytes(data, h=BASIS):
    for byte in data: h = ((h ^ byte) * PRIME) & MASK
    return h


def scan(row):
    """Independent field scanner: no regex library or generated C metadata."""
    fields = row.split(b" ")
    keys = (b"id=", b"user=", b"status=", b"bytes=")
    if len(fields) != 4 or not all(s.startswith(k) for s,k in zip(fields,keys)):
        return 0, BASIS
    values = [s[len(k):] for s,k in zip(fields,keys)]
    digits = lambda s: all(48 <= c <= 57 for c in s)
    if not (1 <= len(values[0]) <= 6 and digits(values[0])
            and 3 <= len(values[1]) <= 8 and all(97 <= c <= 122 for c in values[1])
            and values[2] in (b"ok", b"warn", b"fail")
            and 1 <= len(values[3]) <= 5 and digits(values[3])):
        return 0, BASIS
    captures = [(0,len(row))]
    offset = 0
    for field,key in zip(fields,keys):
        captures.append((offset+len(key),offset+len(field)))
        offset += len(field)+1
    h = BASIS
    for begin,end in captures:
        h = hash_bytes(begin.to_bytes(8,"little"),h)
        h = hash_bytes(end.to_bytes(8,"little"),h)
        h = hash_bytes(row[begin:end],h)
    return {b"ok":1,b"warn":3,b"fail":7}[values[2]], h


def oracle(text, kib, seed, requests):
    lines = text.splitlines()
    header = dict(kv.split("=") for kv in lines[0].split()[1:])
    assert int(header["bytes"]) == kib*1024 and int(header["seed"]) == seed
    count = int(header["records"])
    corpus = bytearray(b"#" * (kib*1024))
    records, rows = [], []
    end = 0
    for line in lines[1:]:
        if not line.startswith("ROW "): continue
        _, number, offset, length, encoded = line.split()
        number, offset, length = int(number), int(offset), int(length)
        row = bytes.fromhex(encoded)
        assert number == len(rows) and offset == end and len(row) == length and b"\0" not in row
        assert length < 80 and offset+length < len(corpus)
        corpus[offset:offset+length+1] = row+b"\0"
        end = offset+length+1
        rows.append(row); records.append(scan(row))
    assert len(rows) == count and hash_bytes(corpus) == int(header["hash"],16)
    assert {mask for mask,_ in records} == {0,1,3,7}
    actual = [line.split() for line in lines if line.startswith("REQUEST ")]
    assert len(actual) == requests
    positives = negatives = 0
    for epoch,fields in enumerate(actual):
        _, number, observed, calls, positive, negative = fields
        expected = 0
        for query in range(64):
            random = mix(seed+epoch*64+query)
            pattern = (random >> 32) % 3
            matches,capture = records[random % count]
            matched = bool(matches & (1 << pattern))
            positives += int(matched); negatives += int(not matched)
            expected += mix(random ^ (pattern << 61) ^ (capture if matched else 0x6e6f6d6174636821))
        assert int(number) == epoch and int(observed,16) == expected & MASK
        assert int(calls.split("=")[1]) == (epoch+1)*64
        assert int(positive.split("=")[1]) == positives
        assert int(negative.split("=")[1]) == negatives
    assert positives and negatives and lines[-1] == "RETAINED29_REGEX_FUNCTIONAL_PASS"
    return dict(kib=kib,seed=seed,requests=requests,actual_regexec_calls=requests*64,
                positive_calls=positives,negative_calls=negatives,records=count,
                corpus_bytes=kib*1024,descriptor_bytes=int(header["metadata"]))


def main():
    for n in range(1,1000):
        out=HERE/("preparation-%03d" % n)
        try: out.mkdir();break
        except FileExistsError:continue
    else:raise RuntimeError("no fresh output")
    own=[ROOT/"linux-tests/retained29_regex_workload.h",ROOT/"linux-tests/test_retained29_regex_workload.c",
         HERE/"functional_driver.c",HERE/"abi_probe.c",Path(__file__).resolve()]
    frozen=[ROOT/"linux-tests/scheduler_retained29_benchmark.c",ROOT/"linux-tests/resume_workload.h"]
    before={str(p):binding(p) for p in own+frozen+[OLD/"prepare.py",OLD/"preparation-003/manifest.json"]}
    assert before[str(frozen[0])]["sha256"] == "65adf577913f2c869ee7f97e9f43b706698e714f8634a0df12135569b9d52be9"
    record=dict(state="preparing",scope="new module only; host correctness and RV64 ABI/link preparation, no target execution",
                inputs=before,commands=[])
    (out/"source").mkdir()
    for p in own:shutil.copyfile(p,out/"source"/p.name)
    shutil.copyfile(OLD/"prepare.py",out/"source/old_regex_abi_helpers.py")
    def run(label,argv,env=None,expected=0):
        argv=list(map(str,argv));r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env=env,cwd=str(ROOT),timeout=120)
        stdout,stderr=out/(label+".stdout"),out/(label+".stderr")
        stdout.write_bytes(r.stdout);stderr.write_bytes(r.stderr)
        record["commands"].append(dict(label=label,argv=argv,returncode=r.returncode,expected_returncode=expected,
                                       stdout=binding(stdout),stderr=binding(stderr)))
        assert r.returncode == expected,(label,r.returncode,r.stderr.decode(errors="replace"))
        return r.stdout.decode()
    try:
        spec=importlib.util.spec_from_file_location("old_regex_abi",OLD/"prepare.py")
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        prior=json.loads((OLD/"preparation-003/manifest.json").read_text())
        # Reuse existing ABI helpers and evidence; do not rerun or change old prep.
        members=old.accepted_members()
        sysroot=Path(run("cross-sysroot",[old.CC,"-print-sysroot"]).strip())
        target,loader=old.SDK/"target/lib/libc.so.6",old.SDK/"target/lib/ld-linux-riscv64-lp64d.so.1"
        for path,name in ((target,"lib/libc.so.6"),(loader,"lib/ld-linux-riscv64-lp64d.so.1")):
            assert binding(path)["sha256"] == members[name]["sha256"]
        headers={name:binding(sysroot/"usr/include"/name) for name in ("features.h","regex.h")}
        assert all(headers[name]["sha256"] == prior["abi_proof"]["headers"][name]["sha256"] for name in headers)
        libc_sections=old.allocated_sections(sysroot/"lib/libc.so.6")
        loader_sections=old.allocated_sections(sysroot/"lib/ld-linux-riscv64-lp64d.so.1")
        assert libc_sections == old.allocated_sections(target) and len(libc_sections)==28
        assert loader_sections == old.allocated_sections(loader)
        common=["-std=c11","-Wall","-Wextra","-Werror","-I"+str(out/"source")]
        cross=common+["-O2","-march=rv64imafdc","-mabi=lp64d","-fno-pie","-no-pie"]
        run("cross-abi",[old.CC]+cross+["-H","-c",out/"source/abi_probe.c","-o",out/"abi_probe.o"])
        run("cross-build",[old.CC]+cross+[out/"source/functional_driver.c","-o",out/"regex-functional.riscv"])
        dynamic=run("cross-readelf",["readelf","-h","-l","-d","-V","-Ws",out/"regex-functional.riscv"])
        symbols=run("accepted-runtime-symbols",["readelf","-Ws",target,loader])
        needed=[line.split("[",1)[1].split("]",1)[0] for line in dynamic.splitlines() if "(NEEDED)" in line]
        assert needed == ["libc.so.6","ld-linux-riscv64-lp64d.so.1"] and "RISC-V" in dynamic
        imports=sorted(set(re.findall(r"\bUND\s+(\S+@GLIBC_\S+)",dynamic)))
        assert imports
        for symbol in imports:assert symbol in symbols or symbol.replace("@","@@",1) in symbols,symbol
        for function in ("regcomp","regexec","regfree"):
            assert function+"@GLIBC_2.27" in dynamic
        record["accepted_runtime_ABI"]=dict(prior_proof=binding(OLD/"preparation-003/manifest.json"),
            reused_helpers=binding(OLD/"prepare.py"),accepted_CPIO=binding(old.CPIO),members=members,
            compiler=binding(old.CC),headers=headers,libc=binding(target),loader=binding(loader),
            equal_allocated_libc_sections=libc_sections,equal_allocated_loader_sections=loader_sections,
            ABI_probe=binding(out/"abi_probe.o"),versioned_imports=imports,NEEDED=needed,
            limit="No RV64 execution; public glibc2.37 ABI and accepted allocated images, not local glibc2.42 sources or fresh Bootlin authentication")
        run("host-version",["cc","--version"])
        run("host-libc",["getconf","GNU_LIBC_VERSION"])
        host=common+["-O1","-g","-fno-omit-frame-pointer","-fno-pie","-no-pie","-fsanitize=address,undefined"]
        env=dict(os.environ,LC_ALL="C",ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        run("host-check-build",["cc"]+host+[out/"source/test_retained29_regex_workload.c","-o",out/"host-checks"])
        result=run("host-checks",[out/"host-checks"],env)
        assert result.strip()=="RETAINED29_REGEX_HOST_PASS"
        run("host-production-build",["cc"]+host+[out/"source/functional_driver.c","-o",out/"host-functional"])
        cases=[]
        for kib in (32,128):
            for seed in (0,7,0x123456789abcdef0,MASK):
                label="oracle-%d-%d"%(kib,seed)
                text=run(label,[out/"host-functional",kib,seed,17,"--dump"],env)
                cases.append(oracle(text,kib,seed,17))
        for n,args in enumerate((("129","1","1"),("32","-1","1"),("32","1","1001"),("32","abc","1"))):
            run("bad-args-%d"%n,[out/"host-functional"]+list(args),env,expected=2)
        for p,b in before.items():assert binding(p)==b,"input changed: "+p
        record.update(state="PASS-host-oracle-ASAN-UBSAN-and-RV64-link-only",oracle_cases=cases,
            cross_ELF=binding(out/"regex-functional.riscv"),
            host_checks=binding(out/"host-checks"),host_driver=binding(out/"host-functional"),
            sanitizer_environment={key:env[key] for key in ("LC_ALL","ASAN_OPTIONS","UBSAN_OPTIONS")},
            limits=["No RV64/model/FPGA execution or performance result","Libc DSO internals uninstrumented; LSan disabled, no whole-library leak or memory bound proof",
                    "Corpus32/128KiB excludes descriptors, regex opaque/lazy allocations, allocator overhead, stack and code; later full resource admission required",
                    "Future whole-cell scope must charge init/regcomp, every request, check_total/integrity and regfree/free"])
    except BaseException as error:
        record.update(state="FAILED-PREPARATION-NOT-TARGET-EVIDENCE",error=repr(error))
        raise
    finally:
        (out/"manifest.json").write_text(json.dumps(record,indent=2)+"\n")
        print(out,record["state"])


if __name__=="__main__":main()
