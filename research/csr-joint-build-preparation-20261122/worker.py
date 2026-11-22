#!/usr/bin/env python3
"""Default offline; one new joint guest compile/static/NBF proof, never target run."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import socket
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PLAN=HERE/'plan.json'
FINAL=HERE/'admission.FINAL.json'
RUN=Path('/run/user/1001/zp-csr-joint-software-20261122-01')
CLAIM='ONE new joint256 I+D guest build and linked static/NBF proof; no model/audit/board/vendor'


def require(value,message):
    if not value:raise RuntimeError(message)


def bind(path):
    path=Path(path);raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def verify(row):require(bind(row['path'])==row,'fixed source/tool/CRT drift '+row['path'])


def load_module(name,row):
    verify(row);spec=importlib.util.spec_from_file_location(name,row['path'])
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def usage(path):return sum(x.stat().st_size for x in path.rglob('*') if x.is_file())if path.exists()else 0


def load(expected=None,execute=False):
    plan=json.loads(PLAN.read_text())
    require(plan['schema']=='csr-joint-software-plan-v1' and plan['stage']==str(RUN),'fixed software-only plan')
    require(plan['old_program']['sha256']=='88546c8afc17c482e42cb731459f44c2a40f2f6aeee2c172321534c872dabd72'
            and plan['old_toolchain_proof']['sha256']=='05ff02b7d070e74b437376374df4cde2e62d894d320d40528b8c320c4430819b','accepted old compile/CRT anchors')
    require(plan['linux_claim']==CLAIM,'exact scope')
    require(bind(sys.executable)==plan['python'],'actual NBF/worker Python interpreter')
    require(usage(HERE)<=65536,'source/authority family64KiB')
    for row in plan['inputs']:verify(row)
    require(bind(Path(__file__).resolve())in plan['inputs'],'actual worker source pin')
    for path in plan['required_absences']:require(not Path(path).exists(),'unqualified include shadow '+path)
    old=json.loads(Path(plan['old_program']['path']).read_text())
    require(old['compile_command']==plan['old_argv'] and old['compiler']==plan['tools']['gcc'],
            'exact old capacity compiler/flags')
    require(old['max_lines']==1792 and old['max_sets']==256 and old['code_functions']==1792,'unchanged generated bounds')
    if not execute:return plan,None
    require(expected and bind(FINAL)['sha256']==expected,'ROOT exact FINAL SHA')
    final=json.loads(FINAL.read_text())
    require(final['schema']=='csr-joint-software-admission-v1' and final['launchable']is True,'DRAFT cannot execute')
    require(final['source_plan']==bind(PLAN) and final['limits']==plan['limits']
            and final['linux_claim']==CLAIM,'fixed source/limits/scope')
    verify(final['ROOT_release'])
    external=0 if HERE in Path(final['ROOT_release']['path']).resolve().parents else final['ROOT_release']['bytes']
    require(usage(HERE)+external<=65536,'source plus external authority64KiB')
    release=json.loads(Path(final['ROOT_release']['path']).read_text())
    require(release.get('allow_csr_joint_software_build')is True and release.get('source_plan')==bind(PLAN)
            and release.get('linux_claim')==CLAIM,'fresh ROOT software-only release')
    other=final['fixed_OTHER_reservations']
    require(set(other)=={'RUN_bytes','HOME_bytes'}and all(type(x)is int and x>=0 for x in other.values()),'fixed prospective OTHER')
    require(release.get('fixed_OTHER_reservations')==other,'ROOT resource identity')
    external=0 if HERE in Path(final['ROOT_release']['path']).resolve().parents else final['ROOT_release']['bytes']
    require(usage(HERE)+external<=65536,'source plus authority64KiB')
    require(socket.gethostname()==plan['target_hostname'],'actual software host')
    for name in plan['forbidden_compiler_env']:
        require(not os.environ.get(name),'compiler search override must be absent: '+name)
    return plan,final


def compile_command(plan):
    argv=plan['old_argv'][:]
    old=plan['old_output_directory']
    require(argv.count('-I'+old)==1,'one old generated include directory')
    argv[argv.index('-I'+old)]='-I'+str(RUN)
    require(argv.count('-o')==1 and argv[-2:]==plan['old_guest_sources'],'fixed old GCC shape')
    argv[argv.index('-o')+1]=str(RUN/'retained_joint_capacity.elf')
    argv[-2:]=[plan['guest_C']['path'],plan['guest_S']['path']]
    # No added flags; only input/output/generated-include paths are changed.
    return argv


def budget(plan,final):
    limit=plan['limits'];used=usage(RUN);home=usage(HERE);other=final['fixed_OTHER_reservations']
    require(used<=limit['RUN_bytes']and home<=65536,'whole32MiB output/64KiB source caps')
    require(all(x.stat().st_size<=limit['file_bytes']for x in RUN.rglob('*')if x.is_file())if RUN.exists()else True,'per-file8MiB')
    require(shutil.disk_usage(RUN.parent).free>=limit['RUN_floor_bytes']+limit['RUN_bytes']-used+other['RUN_bytes'],'RUN floor+remaining+OTHER')
    require(shutil.disk_usage(HERE).free>=limit['HOME_floor_bytes']+65536-home+other['HOME_bytes'],'HOME floor+remaining+OTHER')
    available=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()if x.startswith('MemAvailable:'))
    require(available>=limit['MemAvailable_floor_bytes'],'host memory floor')
    return dict(RUN_bytes=used,source_HOME_bytes=home,MemAvailable_bytes=available)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');ap.add_argument('--admission-sha256');args=ap.parse_args()
    plan,final=load(args.admission_sha256,args.execute)
    if not args.execute:
        print(json.dumps(dict(state='DRAFT no compiler/generator/targets',plan=bind(PLAN),compile_argv=compile_command(plan)),indent=2));return
    require(not RUN.exists(),'fresh one-shot software stage only')
    budget(plan,final);RUN.mkdir();(RUN/'tmp').mkdir()
    owned=load_module('joint_qualified_owned',plan['owned_worker'])
    tools=load_module('joint_linked_static',plan['static_helper'])
    generate=load_module('joint_unchanged_generator',plan['generator'])
    started=time.monotonic();last_budget=-1
    state=dict(state='RUNNING one guest build/static proof only',source_plan=bind(PLAN),admission=bind(FINAL),commands=[],
               process=dict(pid=os.getpid(),pgid=os.getpgrp()),no_model_audit_board_vendor=True)
    def save():
        tmp=RUN/'session.json.tmp';tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(RUN/'session.json')
    def guard(force=False):
        nonlocal last_budget
        require(time.monotonic()-started<plan['limits']['whole_seconds'],'fixed480s whole software gate')
        now=time.monotonic()
        if force or now-last_budget>=.25:
            budget(plan,final);require(bind(FINAL)['sha256']==args.admission_sha256,'FINAL drift');last_budget=now
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(plan['limits']['file_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_AS,(plan['limits']['process_AS_bytes'],)*2)
    def interrupted(sig,frame):raise RuntimeError('ROOT software worker signal '+str(sig))
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,interrupted)
    env=dict(os.environ,CCACHE_DISABLE='1',SCCACHE_DISABLE='1',OBJCACHE='',PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(RUN/'tmp'))
    def run(label,argv):
        load(args.admission_sha256,True);guard(True)
        row=dict(label=label,argv=list(map(str,argv)),timeout_seconds=60);state['commands'].append(row);save()
        try:
            with (RUN/(label+'.log')).open('wb')as log:
                row['owned']=owned.run(row['argv'],RUN,env,log,60,guard,limits)
            require(row['owned']['returncode']==0 and not row['owned']['owned_group_remaining'],'software phase failed '+label)
        except BaseException as error:
            row['owned']=getattr(error,'owned_receipt',row.get('owned',dict(failure=repr(error),owned_group_remaining=False)))
            raise
        finally:
            row['log']=bind(RUN/(label+'.log'));save()
        guard(True)
    previous_AS=resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS,(min(plan['limits']['process_AS_bytes'],previous_AS[0])if previous_AS[0]>0 else plan['limits']['process_AS_bytes'],previous_AS[1]))
    try:
        generated,count=generate.text(1792,256);require(count==1792,'unchanged target function count')
        (RUN/'capacity_targets.inc').write_text(generated);state['generated']=bind(RUN/'capacity_targets.inc');guard(True)
        elf=RUN/'retained_joint_capacity.elf'
        run('compile',compile_command(plan))
        run('symbols',[plan['tools']['nm']['path'],'-n','-S',elf])
        run('disassembly',[plan['tools']['objdump']['path'],'-d',elf])
        run('readelf',[plan['tools']['readelf']['path'],'-a',elf])
        run('compiler-comment',[plan['tools']['readelf']['path'],'-p','.comment',elf])
        require((RUN/'compiler-comment.log').read_bytes()==Path(plan['old_compiler_comment']['path']).read_bytes(),'same accepted compiler comment')
        syms=tools.symbols((RUN/'symbols.log').read_text())
        image,payload=tools.verify_payloads(elf,syms,generate,guard)
        old_header=Path(plan['old_ELF']['path']).read_bytes()[:64];new_header=elf.read_bytes()[:64]
        require(new_header[16:24]==old_header[16:24] and new_header[48:52]==old_header[48:52],'same ELF type/machine/version/RV64 ABI flags')
        mem=RUN/'prog.mem'
        with mem.open('w')as stream:
            previous=None
            for number,(address,byte)in enumerate(sorted(image.items())):
                if number%4096==0:guard()
                if previous is None or address!=previous+1:stream.write('@%08x\n'%(address-tools.BASE))
                stream.write('%02x\n'%byte);previous=address
        run('nbf',[sys.executable,plan['converter']['path'],'--skip_zeros','--keep_mem_zeros','--config','--mem',mem,'--ncpus','1'])
        nbf=RUN/'prog.nbf';nbf.write_bytes((RUN/'nbf.log').read_bytes())
        coverage=tools.verify_coverage(elf,nbf,payload['config'],0xc641000000000000)
        require(coverage['missing_bytes']==coverage['wrong_bytes']==0,'complete file-backed NBF coverage')
        require(len(state['commands'])==6,'exact six commands/one compile')
        load(args.admission_sha256,True);guard(True)
        program=dict(joint_schema='retained-joint-capacity-program-v1',state='PASS NEW joint ELF/NBF linked payload/CFG/ABI proof; model execution pending',
                     elf=bind(elf),nbf=bind(nbf),symbols=syms,max_lines=1792,max_sets=256,code_functions=1792,
                     data_base=payload['data_base'],code_base=payload['code_base'],code_stride=192,i_lines=256,d_lines=256,sets=256,
                     expected_six_GP0=[256,256,256,256,2048,2048],compile_command=compile_command(plan),compiler=plan['tools']['gcc'],
                     sources=plan['guest_sources']+[state['generated']],converter=plan['converter'],payload_proof=payload,NBF_coverage=coverage,
                     admission=bind(FINAL),source_plan=bind(PLAN),same_ELF_for_later_native_and_physical=True,
                     requires_complete_session=str(RUN/'session.json'),not_valid_without_session_PASS_source_endcheck_and_cleanup=True,
                     limits='46MiB bounds are native/static only, NOT FPGA RAM ownership. Board requires its own corrected runner/allocation gate; no runtime/physical/performance PASS.')
        (RUN/'manifest.json').write_text(json.dumps(program,indent=2)+'\n')
        state.update(state='PASS one NEW joint guest software/static proof only; no model/audit/board',program=bind(RUN/'manifest.json'))
    except BaseException as error:
        state.update(state='FAIL preserved; no retry',error=repr(error));raise
    finally:
        for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_AS,previous_AS)
        try:load(args.admission_sha256,True);state['source_endcheck']='PASS'
        except BaseException as error:state.update(state='FAIL source-endcheck',source_endcheck_error=repr(error))
        remaining=any(x.get('owned',{}).get('owned_group_remaining',False)for x in state['commands'])
        if remaining:state['state']='FAIL owned process group remains; do not release ROOT CPU claim'
        state.update(elapsed_seconds=time.monotonic()-started,owned_group_remaining=remaining);save()
    require(state['state'].startswith('PASS one NEW joint'),'final software acceptance')


if __name__=='__main__':main()
