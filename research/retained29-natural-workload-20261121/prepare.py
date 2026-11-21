#!/usr/bin/env python3
"""Run host protocol gates and cross-link separate ABI29 plus legacy byte proofs."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SDK = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot')
CC = SDK / 'host/bin/riscv64-linux-gcc'
READELF = SDK / 'host/opt/ext-toolchain/bin/riscv64-buildroot-linux-gnu-readelf'
SOURCE = ROOT / 'linux-tests/scheduler_retained29_benchmark.c'
OLD = ROOT / 'research/complete-policy-scope-20261120/compiled/manifest.json'


def record(path):
    path = Path(path).resolve()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def load(path, name):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def main():
    out = HERE/'compiled'
    if out.exists() or (HERE/'manifest.json').exists(): raise RuntimeError('refusing to overwrite closed software preparation')
    out.mkdir()
    files = [SOURCE,ROOT/'linux-tests/resume_workload.h',ROOT/'linux-tests/Makefile',
             ROOT/'linux-tests/test_retained29_benchmark.py',ROOT/'linux-tests/test_resume_resource_accounting.py',
             ROOT/'linux-tests/scheduler_pipe_hint_benchmark.c',ROOT/'linux-tests/icache_retention_probe.c',
             ROOT/'linux-tests/emit_resume_transfer.py',Path(__file__).resolve()]
    before = [record(p) for p in files]
    reference = json.loads(OLD.read_text())
    abi = json.loads((ROOT/'research/retained-control-abi-20261121/manifest.json').read_text())
    tools = {}
    for name in ('compiler_wrapper','compiler_real','readelf'):
        bound = abi['tools'][name]; actual = record(bound['path'])
        assert actual['sha256']==bound['sha256'],name
        tools[name]=actual
    assert record(ROOT/'linux-tests/scheduler_pipe_hint_benchmark.c')['sha256']=='b242d76a3bc5fb754ea92a6167ede622397e19630c7b9e5a415715deb085378e'
    assert record(ROOT/'linux-tests/resume_workload.h')['sha256']=='5d4766cb71b144a93e2b896acf970fce05b349688233a0fae1a5b3458ebe6caa'
    commands = []
    def run(label, argv, cwd=ROOT, env=None):
        result = subprocess.run(list(map(str,argv)),cwd=cwd,env=env,stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,timeout=180)
        path = HERE/(label+'.log');path.write_bytes(result.stdout)
        commands.append(dict(label=label,argv=list(map(str,argv)),cwd=str(cwd),exit_code=result.returncode,log=record(path)))
        assert result.returncode==0,label
        return result.stdout.decode()
    env = dict(os.environ,TMPDIR='/dev/shm',PYTHONDONTWRITEBYTECODE='1')
    run('host-tests',['python3','-m','unittest','-v','test_retained29_benchmark'],ROOT/'linux-tests',env)
    goals = ['retained29-benchmark-dynamic','pipe-hint-benchmark-dynamic','pipe-hint-benchmark-zlib-dynamic',
             'pipe-hint-benchmark-retention-dynamic','icache-retention-probe-dynamic',
             'pipe-hint-benchmark-resources-dynamic','pipe-hint-benchmark-retention-resources-dynamic',
             'pipe-hint-benchmark-plain-resources-dynamic','pipe-hint-benchmark-plain-scoped-resources-dynamic',
             'pipe-hint-benchmark-zlib-scoped-resources-dynamic']
    command = ['make','--no-print-directory','-C',ROOT/'linux-tests','OUT='+str(out),
               'BP_LINUX_DYNAMIC_CC='+str(CC),*goals]
    run('cross-build',command)
    legacy = {}
    for name, old in reference['references'].items():
        actual = record(out/name)
        assert (actual['bytes'],actual['sha256'])==(old['bytes'],old['sha256']),name
        legacy[name]=dict(rebuilt=actual,reference=old,byte_identical=True)
    assert len(legacy)==9
    binary = out/'scheduler_retained29_benchmark_dynamic'
    dynamic = run('retained29-readelf',[READELF,'-h','-l','-d','-V','-Ws',binary])
    needed = re.findall(r'\(NEEDED\).*?\[(.*?)\]',dynamic)
    assert needed==['libc.so.6','ld-linux-riscv64-lp64d.so.1']
    assert 'ELF64' in dynamic and 'RISC-V' in dynamic and 'EXEC (Executable file)' in dynamic
    assert '/lib/ld-linux-riscv64-lp64d.so.1' in dynamic
    # Reuse the already reviewed independent ELF/accepted-CPIO parsers only;
    # no regex workload or library operation is executed.
    helper_path = ROOT/'research/regex-natural-demand-20261121/prepare.py'
    helper = load(helper_path,'accepted_runtime_helpers')
    members = helper.accepted_members()
    sysroot = Path(run('compiler-sysroot',[CC,'-print-sysroot']).strip())
    libc, loader = SDK/'target/lib/libc.so.6', SDK/'target/lib/ld-linux-riscv64-lp64d.so.1'
    for name, runtime in (('libc.so.6',libc),('ld-linux-riscv64-lp64d.so.1',loader)):
        assert record(runtime)['sha256']==members['lib/'+name]['sha256']
        assert helper.allocated_sections(runtime)==helper.allocated_sections(sysroot/'lib'/name)
    symbols = run('accepted-runtime-symbols',[READELF,'-Ws',libc,loader])
    required = sorted(set(re.findall(r'\bUND\s+(\S+@GLIBC_\S+)',dynamic)))
    for symbol in required: assert symbol in symbols or symbol.replace('@','@@',1) in symbols,symbol
    sys.path.insert(0,str(ROOT/'linux-tests'))
    emitter = load(ROOT/'linux-tests/emit_resume_transfer.py','retained29_transfer')
    transfer = emitter.commands(binary)
    encoded = ''.join(re.fullmatch(r"echo '([^']+)' >> .*",line)[1] for line in transfer if line.startswith('echo '))
    assert gzip.decompress(base64.b64decode(encoded,validate=True))==binary.read_bytes()
    (HERE/'retained29.transfer').write_text('\n'.join(transfer)+'\n')
    snapshots = HERE/'source';snapshots.mkdir()
    for p in files: shutil.copyfile(p,snapshots/p.name)
    assert before==[record(p) for p in files],'software source changed during preparation'
    manifest = dict(state='PASS host protocol and RV64 crosscompile/accepted-runtime/9legacy-byte-identity preparation; no target run',
        sources=before,tools=tools,commands=commands,new_elf=record(binary),needed=needed,
        resolved_versioned_imports=required,accepted_runtime=dict(libc=record(libc),loader=record(loader),
           cpio=record(helper.CPIO),members=members,parser=record(helper_path),allocated_images_equal_to_sysroot=True),
        legacy_reference_manifest=record(OLD),legacy=legacy,transfer=record(HERE/'retained29.transfer'),
        transfer_roundtrip_exact=True,transfer_guest_path='fixed existing emitter temporary path; distinct host ELF and new protocol',
        limits=['No RV64/FPGA/model/library workload execution or performance claim',
                'No advisory generation; advisory-only masks are null-source controls',
                'Matched lifecycle/control observers are not an unmodified Linux deployment baseline',
                'Corpus bytes are per process and not total I/D working footprint; all setup/check/free costs priced',
                'Existing nine ELF checks compile/link only; unresolved zlib workload is not rerun'])
    (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('PASS retained29 ELF',manifest['new_elf']['sha256'],'nine legacy ELFs byte-identical; no target')


if __name__=='__main__': main()
