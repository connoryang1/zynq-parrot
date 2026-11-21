#!/usr/bin/env python3
"""Bounded host-only reproduction of the rejected by-value regex adapter."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
import derive
import prepare

ROOT, HERE = derive.ROOT, Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT / "linux-tests"))
import test_retained29_regex_benchmark as tests
import test_retained29_benchmark as protocol
from test_resume_resource_accounting import MOCK as RESOURCE


def main():
    out = HERE / "rejected-by-value-adapter"
    out.mkdir()
    # Reconstruct the initial proposal from the pinned original and the same
    # enumerated edits, omitting only the six in-place allocation corrections.
    raw = derive.BASE.read_text()
    assert prepare.binding(derive.BASE)["sha256"] == derive.BASE_SHA
    skipped = []
    for index,(before,after) in enumerate(derive.REPLACEMENTS):
        if 9 <= index <= 14:
            skipped.append(dict(before=before,after=after));continue
        assert before in raw,before
        raw = raw.replace(before,after)
    assert "return work;" in raw
    source = out / "reconstructed_initial.c";source.write_text(raw)
    with tempfile.TemporaryDirectory(prefix="regex-adapter-repro-",dir="/dev/shm") as directory:
        temp = Path(directory)
        mock = temp / "mock.c"
        observed = tests.REGEX_MOCK.replace("if(p==3 || n!=5 || flags) _exit(101);",
                    'if(p==3 || n!=5 || flags) {event("regex_owner_error",p);_exit(101);}')
        assert observed != tests.REGEX_MOCK
        mock.write_text(RESOURCE.replace("int __wrap_getrusage(","int deterministic_getrusage(") + protocol.MOCK + observed)
        (out / "mock.c").write_text(mock.read_text())
        binary = temp / "by_value"
        command = ["cc","-std=c11","-O2","-Wall","-Wextra","-Werror","-DBP_RETAINED29_HOST_VERIFY=1",
                   "-I"+str(ROOT / "linux-tests"),str(source),str(mock),"-o",str(binary)]
        command += ["-Wl,--wrap="+name for name in ("prctl","fork","waitpid","free","munmap","getrusage",
                    "calloc","malloc","printf","puts","regcomp","regexec","regfree")]
        compiled = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
        (out / "build.log").write_bytes(compiled.stdout);assert compiled.returncode==0
        argv = [str(binary),"3","2","ordinary-joint","2","pipe","plain","32","regex","none"]
        result = subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=15,
                  env=dict(os.environ,LC_ALL="C",BP_RESOURCE_MOCK_LOG=str(out / "events.log")))
        (out / "run.log").write_bytes(result.stdout)
        assert result.returncode!=0 and b"_PASS" not in result.stdout
        assert "regex_owner_error" in (out / "events.log").read_text()
        manifest = dict(state="EXPECTED-REJECTION-host-mock-object-identity-only",command=command,argv=argv,
           returncode=result.returncode,reconstructed_initial=prepare.binding(source),omitted_corrections=skipped,
           inputs=[prepare.binding(derive.BASE),prepare.binding(ROOT / "linux-tests/retained29_regex_workload.h"),
                   prepare.binding(ROOT / "linux-tests/test_retained29_regex_benchmark.py"),prepare.binding(__file__)],
           evidence=[prepare.binding(out / name) for name in ("mock.c","build.log","run.log","events.log")],
           limit="Reproduces the test's original regex_t address-ownership rejection after a struct copy; does not prove a production glibc malfunction. Corrected variant initializes caller storage in place.")
        (out / "manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
        print(manifest["state"])


if __name__ == "__main__":main()
