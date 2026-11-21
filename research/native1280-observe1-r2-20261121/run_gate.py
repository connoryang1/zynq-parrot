#!/usr/bin/env python3
"""Clean actual-fulltop 1280+observer gate; isolated HOME outputs, no FPGA tools."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
INSTALL = Path('/home/coyang/zynq-parrot-linux-research/install')
READER = Path('/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121/fst-reader/fst_events')
R1 = '6f29d685332a44e89dcaba5b5adb33520b678da4'
BP = 'e10992a3eea3ba2ef6ae3ccb42ff5e8c658286a8'
PROGRAMS = {
    'integrity': ('2fab907445c24b77a3181fd870d7ae8370c72bfc80bff13b4b14ecfc4b3edac7',
                  '7c47ff60c11d5639555ca10422b9ce7b8d023e9549a5f512131be427d01b4fe2'),
    'advisory': ('3fe096173e3a63b2656c1fadf0a058a328fb5f1ee375be652176408856f897b8',
                 '627662f775f9c2645e5b5687a9df3bfaed25d42265e125a0386047ebe1daad4b')}


def bind(path):
    path = Path(path).resolve(); h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576), b''):h.update(block)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=h.hexdigest())


def full_bind(path):
    result = bind(path); stat = Path(path).stat()
    result.update(inode=stat.st_ino,mtime_ns=stat.st_mtime_ns,ctime_ns=stat.st_ctime_ns)
    return result


def git(path,*args):
    return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**3,2*1024**3))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true')
    args = parser.parse_args(); out = args.out.resolve()
    if out.exists() or not str(out).startswith('/home/coyang/'):raise ValueError('new HOME output required')
    if shutil.disk_usage(out.parent).free < 8*1024**3:raise ValueError('need8GiB free')
    if git(ROOT,'rev-parse','refs/heads/experiment/linux-retained-native1280-r1') != R1:raise ValueError('r1 ref changed')
    repos = [(ROOT,git(ROOT,'rev-parse','HEAD')),(ROOT/'import/black-parrot',BP)]
    for relative,sha in [('external/basejump_stl','3dff9f43af8e1bb850da0b41696514396fa0fa7e'),
                         ('external/HardFloat','5b7d5fe2df7e297b5ba095b3eb8a9517dc2e9d88'),
                         ('external/bedrock','ed68e749079df57afa4b2e153184bf9301137bf2')]:
        repos.append((ROOT/'import/black-parrot'/relative,sha))
    repos += [(ROOT/'import/basejump_stl','6cd7d830b732079ab7316c6288e2e819e3fab474'),
              (ROOT/'import/black-parrot-subsystems','f6ce99ea7ebdcb97a46f73c296505071e9fb22ab'),
              (ROOT/'import/bsg_replicant','83e2441b3bab646a69159fa9dee80de2af9b24ae')]
    before_repos = []
    for path,sha in repos:
        if not (path/'.git').is_file() or git(path,'rev-parse','--show-toplevel') != str(path):
            raise ValueError('missing real initialized worktree '+str(path))
        if git(path,'rev-parse','HEAD') != sha:raise ValueError('wrong commit '+str(path))
        status=git(path,'status','--porcelain','--untracked-files=normal')
        if status and not (args.prepare_only and path==ROOT):raise ValueError('dirty source '+str(path))
        before_repos.append(dict(path=str(path),head=sha,status=status))
    out.mkdir(); runtime=out/'verilator';runtime.mkdir()
    (out/'Makefile.design').symlink_to(ROOT/'cosim/black-parrot-example/Makefile.design')
    recipe=ROOT/'research/hp0-response-path-20261121/full-system-delay200-10/source-before.json.gz'
    command=json.loads(gzip.decompress(recipe.read_bytes()))['command_prefix']
    command=[arg.replace('/home/coyang/zynq-parrot-linux-capacity',str(ROOT)) for arg in command]
    # Admit defaults from the candidate Makefile rather than forcing the four
    # retained geometry/observe flags in this model's command line.
    command=[arg for arg in command if not arg.startswith(('BP_RETAINED_BUFFER=','BP_RETAINED_I_LINES=',
                 'BP_RETAINED_D_LINES=','BP_RETAINED_SETS=','BP_RETAINED_OBSERVE='))]
    command=[('BP_AXI_RESPONSE_DELAY=0' if arg.startswith('BP_AXI_RESPONSE_DELAY=') else arg) for arg in command]
    command+=['ZP_IMPORT_DIR='+str(ROOT/'import'),'COSIM_VSRC_DIR='+str(ROOT/'cosim/v')]
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    env['LD_LIBRARY_PATH']=str(INSTALL/'lib')+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    for key in list(env):
        if key.startswith(('BP_RETAINED_','BP_AXI_RESPONSE_DELAY')):env.pop(key)
    critical=[ROOT/p for p in ('cosim/black-parrot-example/Makefile.design','cosim/black-parrot-example/Makefile.hardware',
        'cosim/black-parrot-example/v/top_zynq.sv','cosim/black-parrot-example/ps.cpp','cosim/black-parrot-example/ps.hpp',
        'cosim/v/bp_retained_use_counters.sv','cosim/mk/Makefile.verilator','cosim/tcl/vivado-utils.tcl',
        'cosim/src/main.cpp','testing/rtl/scoped-assertions/bsg_clkgate_optional.sv',
        'import/black-parrot/bp_top/src/v/bp_unicore_lite.sv','import/black-parrot/bp_me/src/v/cce/bp_uce.sv',
        'import/black-parrot/bp_common/src/v/bp_retained_line_store.sv')]
    before={str(path):full_bind(path) for path in critical}
    record=dict(state='prepared',source_repositories=before_repos,source_before=before,script=bind(__file__),
        recipe=bind(recipe),command_prefix=command,environment=dict(LD_LIBRARY_PATH=env['LD_LIBRARY_PATH']),commands=[],
        geometry=dict(i_lines=1280,d_lines=1280,sets=256,line_bytes=64,observe=1,delay=0),
        scope='Synthetic scoped actual-fulltop correctness; runtime BP assertions after reset, guarded library/timezero checks excluded. No all-slot fullcore utilization, FPGA fit or application performance claim.')

    def run(label,argv,cwd=out,timeout=120):
        entry=dict(label=label,argv=list(map(str,argv)),cwd=str(cwd),timeout_seconds=timeout)
        record['commands'].append(entry);write(out/'session.json',record)
        start=time.monotonic()
        with (out/(label+'.log')).open('wb') as log:
            result=subprocess.run(entry['argv'],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,
                                  timeout=timeout,preexec_fn=limits)
        entry.update(returncode=result.returncode,elapsed_seconds=time.monotonic()-start,log=bind(out/(label+'.log')))
        write(out/'session.json',record)
        return result.returncode

    try:
        if run('make-preflight',command+['-n','build'],runtime):raise ValueError('Make parse/preflight failed')
        dry=(out/'make-preflight.log').read_text()
        for flag in ('BP_RETAINED_BUFFER=1','BP_RETAINED_I_LINES=1280','BP_RETAINED_D_LINES=1280',
                     'BP_RETAINED_SETS=256','BP_RETAINED_OBSERVE=1','BP_AXI_RESPONSE_DELAY=0'):
            if flag not in dry:raise ValueError('candidate default not expanded: '+flag)
        if args.prepare_only:
            record['state']='PASS preparation/default-expansion-only; no build or runtime';return
        if run('clean',command+['clean'],runtime):raise ValueError('clean failed')
        record['state']='clean complete; building'
        if run('build',command+['build'],runtime,3600):raise ValueError('clean model build failed')
        metadata=runtime/'obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat';actual={}
        for line in metadata.read_text().splitlines():
            match=re.fullmatch(r'S\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"([^"]+)"',line)
            if not match:continue
            size,inode,ctime,cnsec,mtime,mnsec=map(int,match.groups()[:6]);path=Path(match[7])
            if not path.is_absolute():path=runtime/path
            bound=full_bind(path)
            if (bound['bytes'],bound['inode'],bound['ctime_ns'],bound['mtime_ns'])!=(size,inode,ctime*10**9+cnsec,mtime*10**9+mnsec):
                raise ValueError('actual source ingestion metadata differs: '+str(path))
            actual[str(path.resolve())]=bound
        for name in ('cosim/v/bp_retained_use_counters.sv','cosim/black-parrot-example/v/top_zynq.sv',
                     'import/black-parrot/bp_top/src/v/bp_unicore_lite.sv'):
            if str(ROOT/name) not in actual:raise ValueError('candidate source not consumed '+name)
        write(out/'actual-source-list.json',dict(sources=actual,metadata=bind(metadata)))
        model=runtime/'obj_dir/Vbsg_nonsynth_zynq_testbench';record['model']=full_bind(model)
        record['actual_source_list']=bind(out/'actual-source-list.json')
        stamps=list((runtime/'obj_dir').glob('.build_config-*'))
        tokens=('BP_RETAINED_BUFFER_1','BP_RETAINED_I_LINES_1280','BP_RETAINED_D_LINES_1280',
                'BP_RETAINED_SETS_256','BP_RETAINED_OBSERVE_1','BP_AXI_RESPONSE_DELAY_0','trace1','-assert-bsgsimhidden-support')
        if len(stamps)!=1 or not all(t in stamps[0].name for t in tokens):raise ValueError('wrong actual model stamp')
        record['model_stamp']=bind(stamps[0]);record['state']='PASS clean build; runtime pending'
        if run('loader',['ldd',model]):raise ValueError('loader preflight failed')
        if 'not found' in (out/'loader.log').read_text():raise ValueError('unresolved loader input')
        closure=ROOT/'research/retained-system-geometry-20261121/closure'
        for name,hashes in PROGRAMS.items():
            target=out/name;target.mkdir()
            for suffix,wanted in zip(('riscv','nbf'),hashes):
                raw=gzip.decompress((closure/(name+'-prog.'+suffix+'.gz')).read_bytes())
                if hashlib.sha256(raw).hexdigest()!=wanted:raise ValueError('closed program mismatch '+name)
                (target/('prog.'+suffix)).write_bytes(raw)
            native,guard=(600000,780) if name=='integrity' else (180000,240)
            argv=[model,'+c_args=prog.nbf '+str(native),'+bsg_trace='+str(target/'trace.fst')]
            write(target/'admission.json',dict(model=record['model'],compiled_sources=record['actual_source_list'],
                elf=bind(target/'prog.riscv'),nbf=bind(target/'prog.nbf'),command=list(map(str,argv)),
                native_host_runtime_ms=native,outer_timeout_s=guard,geometry=record['geometry']))
            rc=run(name+'-run',argv,target,guard)
            shutil.copyfile(out/(name+'-run.log'),target/'run.log')
            write(target/'process.json',dict(returncode=rc))
            check=['python3','-B',ROOT/'testing/check_run.py',target/'run.log','--exit-code',str(rc)]
            if name=='integrity':check+=['--test','mt_large_retained_system_test']
            if run(name+'-checker',check):raise ValueError('complete execution checker rejected '+name)
            text=(target/'run.log').read_text()
            if text.count('Verilator assertion setting restored to 1')!=1:raise ValueError('runtime assertions not restored')
            if name=='advisory':
                marker='[BSG-PASS] retained advisory full-line I/D checked all words completed'
                if text.count(marker)!=1 or text.index(marker)>text.index('CORE PASS'):raise ValueError('exact advisory fixture incomplete')
                rows=re.findall(r'RETAINED_USE_COUNTERS version=1 i_hits=(\d+) d_hits=(\d+) i_published=(\d+) d_published=(\d+) i_write_beats=(\d+) d_write_beats=(\d+) saturating_bits=16 reset=axi_only',text)
                if len(rows)!=1 or tuple(map(int,rows[0]))!=(1,1,1,1,8,8):raise ValueError('actual GP0 observer counts '+repr(rows))
                state='PASS complete scoped wholecore and actual GP0 1hit/1publish/8writes per lane; strict closed trace audit pending'
            else:state='PASS-complete-checked-system-1280-native0-scoped-assertions'
            runproof=dict(state=state,actual_returncode=rc,known_postPASS_GPIO_exception=rc!=0,
                counter_values=rows[0] if name=='advisory' else None,sources=record['actual_source_list'],
                trace=bind(target/'trace.fst'),files=[full_bind(target/p) for p in ('admission.json','process.json','run.log','prog.riscv','prog.nbf','trace.fst')])
            write(target/'verification.json',runproof)
        if before!={str(path):full_bind(path) for path in critical}:raise ValueError('critical source changed during gate')
        if record['model']!=full_bind(model):raise ValueError('model changed during gate')
        for row in before_repos:
            if git(row['path'],'rev-parse','HEAD')!=row['head'] or git(row['path'],'status','--porcelain','--untracked-files=normal'):
                raise ValueError('source repository changed during gate '+row['path'])
        record['state']='PASS clean1280+observe1 integrity/advisory execution; closed trace audits pending'
    except BaseException as error:
        record.update(state='FAIL preserved, no accepted result',error=repr(error));raise
    finally:
        write(out/'session.json',record);print(out/'session.json',record['state'],flush=True)


if __name__=='__main__':main()
