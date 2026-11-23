#!/usr/bin/env python3
"""Host namespace only: one source-bound tracewriter clone and cold08 qualification.

The outer supervisor owns only its worker process group. No FPGA commands, RTL
elaboration, make invocation, evaluation recompilation or original-tree writes.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tarfile
import time
sys.dont_write_bytecode=True
from common import *
from canonical import extract,declarations,equivalent
from framing import framing
from protocol import parse

ADMISSION=ROOT/'admission.json'
HOME_CAP=32*1024**2


def used(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file()) if Path(path).exists() else 0


def resource_guard(free,consumed,home_consumed):
    require(0<=consumed<=ARTIFACT_ALLOCATION,'256MiB clone allocation exceeded')
    require(free>=RESERVE+ARTIFACT_ALLOCATION-consumed,'host RAM minimum1GiB+remaining-stage reserve breached')
    require(home_consumed<=HOME_CAP,'32MiB whole durable allocation exceeded')


def validate(a):
    require(a['schema']=='csr768-observation-only-host-admission-v1','wrong admission')
    require(a['stage']==str(STAGE) and a['proposal']['path']==str(PROPOSAL),'changed fixed output/inputs')
    require(a['budget']==dict(stage_bytes=ARTIFACT_ALLOCATION,minimum_free_plus_remaining=RESERVE,
            home_bytes=HOME_CAP,native_seconds=180,host_seconds=360,FST_bytes=CAP,
            reader_seconds_per_domain=600,canonical_bytes_per_file=50*1024**2,attempts=1),'changed budget')
    for r in a['inputs'].values():verify(r)
    verify(a['proposal']);p=json.loads(PROPOSAL.read_text())
    stat=ORIGINAL.stat();require(p['namespace_identity']==dict(device=stat.st_dev,inode=stat.st_ino),'actual closed original namespace identity')
    require(p['original_model']['sha256']==MODEL_SHA,'wrong original ROOT-bound768 model')
    require(p['original_BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa' and p['original_TOP']=='1b24c915ed628f6d47a382b3aa89fb662884e1a1','new canonical original source identity')
    verify(p['fullcore_producer']);verify(p['inherited_cleanbuild']);verify(p['actual_source_list']);producer()
    require({n:len(rows) for n,rows in p['domains'].items()}==dict(core252=252,observer_and_geometry=45,SP_strict162=162,actual_geometry17=17,capacity167=167),'wrong domains')
    union={r['path']:r['width'] for rows in p['domains'].values() for r in rows}
    require(union=={r['path']:r['width'] for r in p['writer_leaves']} and len(union)==415,'415-leaf union gap')
    for r in [p['original_model'],p['original_session'],p['original_build_log'],p['model_stamp'],p['reader'],
              *p['runtime_sources'].values(),*p['linked_libraries'],*p['compiled_sources'].values(),*p['tools'].values()]:verify(r)
    for name,row in p['tools'].items():require(bind(shutil.which(name))==row,'actual PATH tool differs '+name)
    require(identities(tree(p['original_root']))==identities(p['original_inventory']),'original generated inventory changed')
    for r in a['PCH_inventory'].values():verify(r)
    return p


def filtered_source(text,leaves):
    needle='        __Vm_modelp->trace(__Vm_dumperp, 0, 0);\n'
    require(text.count(needle)==1 and text.index(needle)<text.index('__Vm_dumperp->open('),'ambiguous trace registration/open')
    require(len(leaves)==len({r['path'] for r in leaves}),'duplicate filter leaf')
    extra='        // Observation-only whole-callback selection; evaluation is unchanged.\n'
    extra+=''.join('        __Vm_dumperp->dumpvars(1, '+json.dumps(r['path'])+');\n' for r in leaves)
    return text.replace(needle,needle+extra),extra


def members(archive):
    names=subprocess.check_output(['ar','t',str(archive)],text=True,timeout=30).splitlines()
    require(len(names)==len(set(names)),'duplicate archive members')
    return {n:hashlib.sha256(subprocess.check_output(['ar','p',str(archive),n],timeout=30)).hexdigest() for n in names}


def command(argv,cwd,output,timeout):
    save(str(output)+'.argv.json',argv)
    with Path(output).open('wb') as log:
        proc=subprocess.Popen(argv,cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
        try:rc=proc.wait(timeout=timeout)
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
    require(rc==0,'command failed: '+str(output))


def loader(binary,p):
    env=dict(os.environ);env.update(p['environment'])
    ld=subprocess.run(['ldd',str(binary)],env=env,text=True,capture_output=True,timeout=10)
    require(ld.returncode==0 and 'not found' not in ld.stdout,'loader unresolved')
    libs=[bind(x) for line in ld.stdout.splitlines() for x in line.split() if x.startswith('/') and Path(x).is_file()]
    require(libs==p['linked_libraries'],'loader/library identity differs')
    return ld.stdout


def build(a,p):
    out=STAGE/'build';out.mkdir();obj=out/'obj';obj.mkdir();ev=out/'evidence';ev.mkdir()
    state=dict(state='BUILDING-only-copied-Syms-no-target',admission=bind(ADMISSION),original_model=p['original_model'])
    save(ev/'build.json',state)
    for name,r in p['required_copy'].items():
        verify(r);shutil.copy2(r['path'],obj/name)
        require(bind(obj/name)['sha256']==r['sha256'],'copied byte mismatch')
    before=tree(obj);archive=obj/(PREFIX+'__ALL.a');oldmembers=members(archive)
    require(oldmembers==p['archive_members'],'copied archive differs')
    original_compile=p['original_compile_argv']
    require(original_compile[-4:]==['-c','-o',SYMS+'.o',SYMS+'.cpp'],'actual no-PCH Syms compile shape')
    require(not any('.gch' in a or '__pch.h.slow' in a for a in original_compile),'no hidden PCH use')
    mapped=original_compile.copy()
    require(mapped==p['compile_argv'],'exact actual textual-header compiler argv')
    expected=['ps.o','main.o','bsg_nonsynth_dpi_clock_gen.o','verilated.o','verilated_dpi.o','verilated_fst_c.o','verilated_threads.o',PREFIX+'__ALL.a']
    require([x for x in p['link_argv'] if x.endswith(('.o','.a'))]==expected,'host object order differs')
    command(p['link_argv'],obj,ev/'untouched-link.log',600)
    require(bind(obj/PREFIX)['sha256']==MODEL_SHA,'untouched relink did not reproduce exact ROOT-bound768: no filter/target allowed')
    state['baseline_relink']=bind(obj/PREFIX);save(ev/'build.json',state)
    source=obj/(SYMS+'.cpp');modified,extra=filtered_source(source.read_text(),p['writer_leaves']);source.write_text(modified)
    (ev/'inserted-filter.txt').write_text(extra)
    command(mapped,obj,ev/'compile-Syms.log',600)
    command(['ar','rcs',archive.name,SYMS+'.o'],obj,ev/'replace-Syms.log',60)
    newmembers=members(archive)
    require(list(oldmembers)==list(newmembers) and [n for n in oldmembers if oldmembers[n]!=newmembers[n]]==[SYMS+'.o'],'archive mutation beyond single Syms object')
    command(p['link_argv'],obj,ev/'filtered-link.log',600)
    after=tree(obj);require(set(before)==set(after),'unexpected copied file created/deleted')
    changes=[n for n in before if identities(before)[n]!=identities(after)[n]]
    require(set(changes)<={SYMS+'.cpp',SYMS+'.o',SYMS+'.d',PREFIX+'__ALL.a',PREFIX} and {SYMS+'.cpp',SYMS+'.o'}<=set(changes),'copied evaluation/host object changed')
    (ev/'loader.log').write_text(loader(obj/PREFIX,p));validate(a)
    state.update(state='BUILT-only-copied-Syms-awaiting-one-cold08',binary=bind(obj/PREFIX),changed_files=changes,
                 initial_copy=before,final_copy=after,original_members=oldmembers,final_members=newmembers,
                 compiler=bind(shutil.which('g++')))
    save(ev/'build.json',state);return obj/PREFIX


def limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP))


def run_target(binary,runtime,env):
    argv=[str(binary),'+c_args=prog.nbf 180000','+bsg_trace='+str(runtime/'trace.fst')]
    save(runtime/'admission.json',dict(admission=bind(ADMISSION),model=bind(binary),command=argv))
    with (runtime/'run.log').open('wb') as log:
        proc=subprocess.Popen(argv,cwd=runtime,env=env,stdout=log,stderr=subprocess.STDOUT,preexec_fn=limits)
        start=time.monotonic()
        try:rc=proc.wait(timeout=HOST_SECONDS)
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
    save(runtime/'process.json',dict(returncode=rc,elapsed_seconds=time.monotonic()-start));return rc


def qualify(a,p,binary):
    out=STAGE/'qualification01';out.mkdir();runtime=out/'runtime';runtime.mkdir()
    with (ROOT/'target-one-shot-claim.json').open('x') as f:
        json.dump(dict(state='ONE-cold08-no-retry',admission=bind(ADMISSION),pid=os.getpid(),stage=str(STAGE)),f);f.flush();os.fsync(f.fileno())
    journal=out/'qualification.json';state=dict(state='RUNNING-one-cold08',admission=bind(ADMISSION),domains={});save(journal,state)
    for name,dest in (('elf','prog.riscv'),('nbf','prog.nbf')):
        shutil.copy2(a['reference'][name]['path'],runtime/dest)
        require(bind(runtime/dest)['sha256']==a['reference'][name]['sha256'],'cold08 image byte mismatch')
    env={k:v for k,v in os.environ.items() if not k.startswith(('BSG_RUNTIME_PATCH_','BSG_TRACE_'))};env.update(p['environment'])
    (runtime/'loader.log').write_text(loader(binary,p));validate(a)
    rc=run_target(binary,runtime,env);guest=parse((runtime/'run.log').read_text(),rc)
    require(rc==a['reference']['returncode'] and guest==a['reference']['guest'],'whole cold08/CORE/GP0/retired-count/terminal protocol differs')
    fst=runtime/'trace.fst';require(0<fst.stat().st_size<CAP,'FST absent/at cap')
    frame=framing(fst);old=framing(Path(a['reference']['trace']['path']))
    require((frame['header_start_tick'],frame['header_end_tick'])==(old['header_start_tick'],old['header_end_tick']),'full initialization-to-EOF clock endpoints differ')
    listing=subprocess.check_output([p['reader']['path'],str(fst),'--list'],text=True,timeout=60)
    declarations(listing,p['writer_leaves']);(out/'hierarchy.tsv').write_text(listing)
    spec=importlib.util.spec_from_file_location('unchanged_dense_binding',OLD_SOURCE/'research/retained-use-observation-20261121/build_full.py')
    producer=importlib.util.module_from_spec(spec);spec.loader.exec_module(producer)
    proof=dict(state='PASS complete scoped wholecore and actual GP0 1hit/1publish/8writes per lane; strict closed trace audit pending',
        actual_returncode=rc,known_postPASS_GPIO_exception=rc!=0,counter_values=guest['counter_values'],
        sources=producer.binding(Path(p['actual_source_list']['path'])),trace=bind(fst),
        files=[producer.binding(runtime/n) for n in ('admission.json','process.json','run.log','prog.riscv','prog.nbf','trace.fst')])
    save(runtime/'verification.json',proof)
    state.update(state='COMPLETE-cold08-awaiting-five-domain-and-maintained-checkers',guest=guest,framing=frame,trace=bind(fst));save(journal,state)
    for name,leaves in p['domains'].items():
        reference=a['original_canonical'][name]
        verify(reference['canonical_file'])
        selected=extract(p['reader']['path'],fst,leaves,out/('clone-'+name),False)
        equivalent(reference,selected);state['domains'][name]=dict(reference=reference,clone=selected,literal_bytes_equal=True);save(journal,state)
    strict=SP/'testing/rtl/retained-advisory-trace/validate.py'
    command([sys.executable,'-B',str(strict),'--fst',str(fst),'--reader',p['reader']['path'],'--model-source-list',p['actual_source_list']['path'],
        '--fixture-manifest',a['fixture_manifest']['path'],'--log',str(runtime/'run.log'),'--exit-code',str(rc),'--out',str(out/'strict'),'--reader-timeout','600'],out,out/'strict.log',720)
    require(json.loads((out/'strict/verification.json').read_text())['accepted'] is True,'strict512b/eight-real-writes/Iretire not accepted')
    command([sys.executable,'-B',str(OLD_SOURCE/'research/retained-use-observation-20261121/verify_counters.py'),'--fst',str(fst),'--reader',p['reader']['path'],
        '--strict-proof',str(out/'strict/verification.json'),'--run-proof',str(runtime/'verification.json'),'--out',str(out/'observer')],out,out/'observer.log',300)
    obs=json.loads((out/'observer/verification.json').read_text());require(obs['state'].startswith('PASS actual counter transitions') and obs['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'counter transitions/GP0 differ')
    command([sys.executable,'-B',str(GEOMETRY_TOOL),'--fst',str(fst),'--reader',p['reader']['path'],'--out',str(out/'geometry'),'--lines','768'],out,out/'geometry.log',660)
    geo=json.loads((out/'geometry/verification.json').read_text());require(geo['facts']['values']==a['reference']['actual_geometry'],'all17 actual geometry fields differ')
    validate(a);state.update(state='PASS-matched768-cold08-five-domain-literal-equivalence-strict-counter-geometry',strict=bind(out/'strict/verification.json'),observer=bind(out/'observer/verification.json'),geometry=bind(out/'geometry/verification.json'))
    save(journal,state);return out


def worker(a):
    journal=STAGE/'flow.json';state=dict(state='STARTED',admission=bind(ADMISSION));save(journal,state)
    try:
        p=validate(a);binary=build(a,p);out=qualify(a,p,binary)
        state.update(state='PASS-one-CSR768-observation-qualification',build=bind(STAGE/'build/evidence/build.json'),qualification=bind(out/'qualification.json'))
        save(journal,state) # ROOT archives the combined family separately within32MiB; no automatic HOME writes.
    except BaseException as error:
        state.update(state='FAIL-preserved-no-retry',error=repr(error));raise
    finally:save(journal,state)



if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--approval-sha',required=True);ap.add_argument('--worker',action='store_true',required=True);a=ap.parse_args()
    require(os.getpgrp()==os.getpid(),'worker must own its group')
    require(bind(ADMISSION)['sha256']==a.approval_sha,'external admitted SHA')
    worker(json.loads(ADMISSION.read_text()))
