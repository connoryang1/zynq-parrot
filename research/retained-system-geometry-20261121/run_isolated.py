#!/usr/bin/env python3
"""Clean isolated1280/1280 retained full-system integration gate; no FPGA actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
TOP=HERE.parents[1]
INSTALL=Path('/home/coyang/zynq-parrot-linux-research/install')
IMPORT=Path('/home/coyang/zynq-parrot-linux-research/import')
SOURCE=TOP/'testing/rtl/large_retained_system_test.c'
SUPPORT=TOP/'testing/rtl/scoped-assertions/bsg_clkgate_optional.sv'
BACKEND=TOP/'import/black-parrot/bp_common/src/v/bp_retained_line_store.sv'
PIN='06dfafa133e612f214ea3cb5c5755505602984ed47ff6dac1a1af06afc4d7a4e'


def artifact(path):
    p=Path(path).resolve();h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def git(path,*args):return subprocess.check_output(['git','-C',str(path)]+list(args),text=True).strip()


def limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**3,2*1024**3))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--prepare-only',action='store_true');a=ap.parse_args()
    out=a.output.resolve()
    if out.exists():raise ValueError('new isolated output required; preserve failures, no retries')
    if not str(out).startswith('/home/coyang/'):raise ValueError('durable HOME output required')
    if shutil.disk_usage(out.parent).free<8*1024**3:raise ValueError('need8GiB free for clean full model')
    if artifact(BACKEND)['sha256']!=PIN:raise ValueError('backend differs from frozen06df')
    out.mkdir();design=out/'design';run=design/'verilator';run.mkdir(parents=True)
    for n in ('Makefile.design','Makefile.hardware','Makefile.collateral','ps.cpp','ps.hpp'):
        shutil.copyfile(TOP/'cosim/black-parrot-example'/n,design/n)
    # Source symlink preserves the live source identity; exact used hashes are
    # pinned before elaboration and checked after the complete run.
    (design/'v').symlink_to(TOP/'cosim/black-parrot-example/v',target_is_directory=True)
    shutil.copyfile(TOP/'cosim/black-parrot-example/verilator/Makefile',run/'Makefile')
    programs=out/'program';(programs/'bp-tests').mkdir(parents=True);(programs/'bootrom').mkdir()
    boot=Path('/home/coyang/zynq-parrot-linux-research/riscv/bootrom/bootrom.none.riscv')
    shutil.copyfile(boot,programs/'bootrom/bootrom.none.riscv')
    software=out/'software';software.mkdir()
    rootfiles=[SOURCE,TOP/'testing/Makefile',TOP/'testing/check_run.py',TOP/'cosim/mk/Makefile.verilator',
               TOP/'cosim/include/verilator/bsg_zynq_pl.h',TOP/'cosim/include/common/bsg_zynq_pl_simulation.h',
               TOP/'cosim/src/main.cpp',TOP/'cosim/black-parrot-example/ps.cpp',TOP/'cosim/black-parrot-example/ps.hpp',INSTALL/'bin/verilator_bin',SUPPORT,
               TOP/'cosim/black-parrot-example/Makefile.design',TOP/'cosim/black-parrot-example/Makefile.hardware']
    # Pin every readable RTL/package/header and shared cosim input, not merely git HEAD.
    for base in (TOP/'import/black-parrot',TOP/'cosim/v',TOP/'cosim/include',TOP/'cosim/black-parrot-example/v',IMPORT/'basejump_stl',IMPORT/'black-parrot-subsystems',IMPORT/'bsg_replicant',INSTALL/'share/verilator/include',INSTALL/'include'):
        rootfiles.extend(p for p in base.rglob('*') if p.is_file() and p.suffix in ('.sv','.svh','.v','.vi','.vh','.h','.hpp','.cpp','.vlt'))
    bindings={str(p.resolve()):artifact(p) for p in rootfiles}
    include_dirs=[design,TOP/'cosim/include/common',TOP/'cosim/include/verilator',INSTALL/'include',IMPORT/'basejump_stl/bsg_mem',IMPORT/'black-parrot-subsystems/blackparrot/src',IMPORT/'bsg_replicant/libraries',IMPORT/'basejump_stl/bsg_test']
    includes=[]
    for host in (design/'ps.cpp',design/'ps.hpp'):
        for name in re.findall(r'^#include \"([^\"]+)\"',host.read_text(),re.M):
            found=next((d/name for d in include_dirs if (d/name).is_file()),None)
            if found is None:raise ValueError('host quoted include unresolved: '+name)
            includes.append(dict(including=artifact(host),name=name,resolved=artifact(found)))
    (out/'host-include-closure.json').write_text(json.dumps(includes,indent=2)+'\n')
    record=dict(state='prepared',geometry=dict(i_lines=1280,d_lines=1280,retained_sets=256,payload_bytes_per_line=64),
                topology=dict(resident_slots=2,logical_contexts=4),hp0_response_delay=0,inner_build_jobs=3,
                source_top=git(TOP,'rev-parse','HEAD'),source_bp=git(TOP/'import/black-parrot','rev-parse','HEAD'),
                source_top_diff=git(TOP,'diff','--stat'),source_bp_diff=git(TOP/'import/black-parrot','diff','--stat'),
                sources_before=bindings,commands=[],scope='Synthetic checked full-system correctness only. Post-init BP/runtime assertion scope; guarded Basejump/library checks excluded, timezero parameter assertions suppressed until reset completes. No global assertion acceptance, full-capacity usage, physical fit, application or FPGA performance claim.')
    (out/'source').mkdir()
    for p in (SOURCE,TOP/'testing/Makefile',SUPPORT,Path(__file__)):
        shutil.copyfile(p,out/'source'/p.name)
    task_env=dict(os.environ)
    task_env['LD_LIBRARY_PATH']=str(INSTALL/'lib')+((':'+task_env['LD_LIBRARY_PATH']) if task_env.get('LD_LIBRARY_PATH') else '')
    record['launch_environment']={'LD_LIBRARY_PATH':task_env['LD_LIBRARY_PATH']}
    def command(label,argv,cwd,timeout):
        c=dict(label=label,argv=list(map(str,argv)),cwd=str(cwd),timeout_seconds=timeout)
        record['commands'].append(c);start=time.monotonic()
        try:
            with (out/(label+'.log')).open('wb') as log:
                r=subprocess.run(c['argv'],cwd=cwd,env=task_env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,preexec_fn=limits)
            c.update(returncode=r.returncode,elapsed_seconds=time.monotonic()-start,log=artifact(out/(label+'.log')))
        finally:(out/'session.json').write_text(json.dumps(record,indent=2)+'\n')
        return r.returncode
    options=['TOP='+str(TOP),'ZP_INSTALL_DIR='+str(INSTALL),'ZP_RISCV_DIR='+str(programs),
             'NUM_THREADS=2','NUM_CONTEXTS=4','BP_RETAINED_I_LINES=1280','BP_RETAINED_D_LINES=1280','BP_RETAINED_SETS=256']
    elf=programs/'bp-tests/mt_large_retained_system_test.riscv'
    compilecmd=['make','-f',TOP/'testing/Makefile',elf]+options
    buildcmd=['make','-j1','build']+options+['ZP_IMPORT_DIR='+str(IMPORT),'BP_RTL_DIR='+str(TOP/'import/black-parrot'),
              'TRACE=1','BP_AXI_RESPONSE_DELAY=0','VERILATOR_BUILD_JOBS=3','VERILATOR='+str(INSTALL/'bin/verilator')+' --assert',
              'EXTRA_DEFINES=BSG_HIDE_FROM_SYNTHESIS','VERILATOR_SUPPORT_SOURCES='+str(SUPPORT)]
    record['prepared_commands']=dict(compile=list(map(str,compilecmd)),build=list(map(str,buildcmd)))
    (out/'session.json').write_text(json.dumps(record,indent=2)+'\n')
    if a.prepare_only:print(out/'session.json');return
    try:
        if command('compile',compilecmd,software,60):raise RuntimeError('software compile failed')
        record['elf']=artifact(elf)
        if command('build',buildcmd,run,1800):raise RuntimeError('model build failed; no runtime accepted')
        executable=run/'obj_dir/Vbsg_nonsynth_zynq_testbench';record['executable']=artifact(executable)
        actual={}
        for line in (run/'obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat').read_text().splitlines():
            if not line.startswith('S '):continue
            match=re.search(r'"([^"]+)"$',line)
            if not match:raise ValueError('unparsed actual source record')
            p=Path(match.group(1));p=p if p.is_absolute() else run/p
            binding=artifact(p);actual[binding['path']]=binding
            if binding['path'] not in bindings and out not in p.resolve().parents:
                raise ValueError('actual source not covered before elaboration: '+str(p))
        (out/'actual-source-list.json').write_text(json.dumps(actual,indent=2)+'\n')
        record['actual_source_list']=artifact(out/'actual-source-list.json')
        # Generate NBF only in this isolated directory using the maintained rule.
        shutil.copyfile(elf,run/'prog.riscv')
        nbfcommand=['make','prog.nbf']+options+['ZP_IMPORT_DIR='+str(IMPORT),'BP_RTL_DIR='+str(TOP/'import/black-parrot')]
        if command('nbf',nbfcommand,run,60):raise RuntimeError('NBF generation failed')
        record['nbf']=artifact(run/'prog.nbf')
        stamps=list((run/'obj_dir').glob('.build_config-*'))
        if len(stamps)!=1 or not all(s in stamps[0].name for s in ('nt2-nc4','trace1','I_LINES_1280','D_LINES_1280','SETS_256','BP_AXI_RESPONSE_DELAY_0','-assert-bsgsimhidden-support')):
            raise ValueError('wrong model configuration identity')
        record['build_stamp']=stamps[0].name
        trace=run/'retained1280-native0.fst'
        rc=command('run',[executable,'+c_args='+str(run/'prog.nbf')+' 600000','+bsg_trace='+str(trace)],run,780)
        record['run_returncode']=rc
        if command('checker',['python3',TOP/'testing/check_run.py',out/'run.log','--test','mt_large_retained_system_test','--exit-code',str(rc)],out,10):raise RuntimeError('maintained checker rejected complete execution')
        text=(out/'run.log').read_text()
        if text.count('Verilator assertion setting restored to 1')!=1:raise ValueError('runtime assertions not restored')
        record['trace']=artifact(trace)
        for path,binding in bindings.items():
            if artifact(path)!=binding:raise ValueError('source changed during full-system gate: '+path)
        record['state']='PASS-complete-checked-system-1280-native0-scoped-assertions'
    except BaseException as e:
        record.update(state='FAIL-preserved-no-result',error=repr(e));raise
    finally:
        (out/'session.json').write_text(json.dumps(record,indent=2)+'\n')
        print(out/'session.json',record['state'])

if __name__=='__main__':main()
