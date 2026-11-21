#!/usr/bin/env python3
"""Host-only cohort/parser qualification and unlaunchable concrete draft plans."""
from datetime import datetime, timezone
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'linux-tests'))
import retained29_application_protocol as p
import emit_resume_transfer


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def main():
    for n in range(1,1000):
        out=HERE/('preparation-%03d'%n)
        try:out.mkdir();break
        except FileExistsError:continue
    else:raise ValueError('no fresh output')
    sources=p.source_hashes();old={name:sources[name] for name in p.FROZEN}
    base_commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','47b8bb31b'],text=True).strip()
    unchanged={}
    for name in (*p.FROZEN,'linux-tests/Makefile','linux-tests/scheduler_retained29_regex_benchmark.c','linux-tests/retained29_regex_workload.h'):
        raw=subprocess.check_output(['git','-C',str(ROOT),'show',base_commit+':'+name])
        expected=hashlib.sha256(raw).hexdigest();p.require(p.binding(ROOT/name)['sha256']==expected,'base47 source changed '+name)
        unchanged[name]=expected
    record=dict(state='preparing',sources=sources,frozen17_before=old,unchanged_base_commit=base_commit,
                unchanged_sources=unchanged,preparer=p.binding(__file__),commands=[],
                scope='Offline protocol/host-library and accepted-RV64-input binding only; no physical operation or application performance claim')
    def run(label,argv,cwd=ROOT,env=None):
        r=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        log=out/(label+'.log');log.write_bytes(r.stdout)
        record['commands'].append(dict(label=label,argv=list(map(str,argv)),cwd=str(cwd),returncode=r.returncode,log=p.binding(log)))
        if r.returncode:raise ValueError((label,r.returncode,r.stdout.decode(errors='replace')))
        return r.stdout.decode()
    try:
        abi=load(ROOT/'research/regex-natural-demand-20261121/prepare.py','accepted_abi_helpers')
        module_gate=ROOT/'research/retained29-regex-benchmark-20261121/preparation-002/manifest.json'
        regex=json.loads(module_gate.read_text());p.require(regex['state']=='PASS-real-regex-host-protocol-and-RV64-link-only','prior real-regex gate')
        plain_gate=ROOT/'research/retained29-natural-workload-20261121/preparation-002-cleanup/manifest.json'
        plain=json.loads(plain_gate.read_text())
        inputs=dict(plain=Path(plain['new_elf']['path']),regex=Path(regex['elf']['path']),
            probe=Path('/home/coyang/zynq-parrot-linux-capacity/research/retained-control-abi-20261121/retained_store_probe.elf'))
        (out/'programs').mkdir();programs={}
        symbols=run('accepted-runtime-symbols',['readelf','-Ws',abi.SDK/'target/lib/libc.so.6',abi.SDK/'target/lib/ld-linux-riscv64-lp64d.so.1'])
        members=abi.accepted_members();runtime={}
        for name in ('libc.so.6','ld-linux-riscv64-lp64d.so.1'):
            path=abi.SDK/'target/lib'/name;p.require(p.binding(path)['sha256']==members['lib/'+name]['sha256'],'accepted CPIO runtime')
            runtime[name]=p.binding(path)
        imports={};needed={}
        for kind,path in inputs.items():
            p.require(p.binding(path)['sha256']==p.ELF_SHAS[kind],'fixed ELF '+kind)
            target=out/'programs'/(kind+'.elf');shutil.copyfile(path,target)
            transfer=out/'programs'/(kind+'.transfer');transfer.write_text('\n'.join(emit_resume_transfer.commands(target))+'\n')
            programs[kind]=dict(elf=p.binding(target),transfer=p.binding(transfer))
            p.transfer_commands(dict(programs=programs),kind)
            text=run(kind+'-readelf',['readelf','-h','-l','-d','-V','-Ws',target])
            p.require('RISC-V' in text and '/lib/ld-linux-riscv64-lp64d.so.1' in text,'RV64 public ABI/loader')
            needed[kind]=re.findall(r'\(NEEDED\).*?\[(.*?)\]',text)
            p.require(needed[kind]==['libc.so.6','ld-linux-riscv64-lp64d.so.1'],'fixed accepted library dependencies')
            imported=sorted(set(re.findall(r'\bUND\s+(\S+@GLIBC_\S+)',text)))
            p.require(imported,'versioned imports')
            for symbol in imported:p.require(symbol in symbols or symbol.replace('@','@@',1) in symbols,'accepted runtime import '+symbol)
            if kind=='regex':
                p.require(all(name+'@GLIBC_2.27' in imported for name in ('regcomp','regexec','regfree')),'real POSIX imports')
            imports[kind]=imported
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',R29_APP_HOST_FIXTURE_DIR=str((out/'real-host-fixtures').resolve()))
        run('host-compiler-version',[os.environ.get('BP_HOST_CC','cc'),'--version'])
        run('host-libc-version',['getconf','GNU_LIBC_VERSION'])
        record['host_compiler']=p.binding(shutil.which(os.environ.get('BP_HOST_CC','cc')))
        run('application-tests',['python3','-B','-m','unittest','-v','test_retained29_application'],ROOT/'linux-tests',env)
        run('legacy17-regression',['python3','-B','-m','unittest','-v','test_retained29_session','test_retained29_session_v2','test_retained29_stage_v2'],ROOT/'linux-tests',env)
        kernel=ROOT/'research/retained-control-kernel29-20261121/verification.json'
        package=json.loads((ROOT/'research/retained-control-kernel29-20261121/package-manifest.json').read_text())
        p.require(p.binding(kernel)['sha256']==p.base.KERNEL_PROOF_SHA,'actual46M kernel proof')
        p.verify_binding(package['candidate']);p.require(package['candidate']['sha256']==p.base.NBF_SHA,'exact kernel29 NBF')
        drafts=out/'drafts';drafts.mkdir();draft_records=[]
        for index,(role,work) in enumerate([('pilot-functional',None)]+[('performance-acquisition',w) for w in p.WORKLOADS]):
            plan=p.plan_for(role,work,index);stem='pilot' if work is None else 'performance-'+work
            declared=dict(schema=p.PLAN_SCHEMA,state='DRAFT-UNLAUNCHABLE',declared_utc=datetime.now(timezone.utc).isoformat(),
                plan=plan,sources=sources,elf_sha256=p.ELF_SHAS,primary='WHOLE',secondary='steady',effect_selection='none',
                limits='Draft case order only, not physical permission/performance evidence; no automatic reschedule/retry or expansion')
            plan_path=drafts/(stem+'-plan.json');plan_path.write_text(json.dumps(declared,indent=2)+'\n')
            admission=dict(schema=p.SCHEMA,state='DRAFT-UNLAUNCHABLE',role=role,plan=plan,plan_record=p.binding(plan_path),
                host='xilinx@192.168.4.35',runtime_ms=3600000,one_guest_boot=True,runner_sha256=p.base.RUNNER_SHA,
                board_helper_sha256=p.base.HELPER_SHA,sources=sources,legacy_sources=old,programs=programs,
                hardware=dict(cfg='e_bp_unicore_zynqparrot_prefetch16k_cfg',l1i_bytes=32768,l1d_bytes=32768,l2_bytes=16384,
                              retained=dict(i_lines=1280,d_lines=1280,set_log2=8)),
                artifacts=dict(nbf=package['candidate'],kernel_verification=p.binding(kernel),package=None,bit=None,fit=None),
                capability_gate=None,functional_gate=None,stage_admission=None,
                unlaunchable_reasons=['No passed routed-bit/package binding','No actual recovered present probe on that exact bit',
                    'No unchanged fixed V1 functional first gate on that bit','No matching maintained V2 stage admission',
                    'Plan not reviewed/predeclared for physical acquisition'])
            path=drafts/(stem+'.json');path.write_text(json.dumps(admission,indent=2)+'\n')
            run(stem+'-offline',['python3','-B',ROOT/'linux-tests/run_retained29_application_session.py',path])
            try:p.validate_admission(admission)
            except ValueError as error:p.require('UNLAUNCHABLE' in str(error),'draft refusal reason')
            else:raise ValueError('draft unexpectedly executable')
            draft_records.append(p.binding(path))
        p.require(sources==p.source_hashes(),'source changed during qualification')
        p.require(old=={name:p.source_hashes()[name] for name in p.FROZEN},'frozen17 changed')
        p.require(unchanged=={name:p.binding(ROOT/name)['sha256'] for name in unchanged},'base47 inputs changed')
        snapshots=out/'source';snapshots.mkdir()
        for name in (*p.SOURCE_FILES,'linux-tests/test_retained29_application.py'):
            dest=snapshots/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(__file__,snapshots/'prepare.py')
        record.update(state='PASS offline host/protocol and fixed accepted ELF bindings; all drafts UNLAUNCHABLE',
            frozen17_after=old,programs=programs,versioned_imports=imports,needed=needed,accepted_runtime=runtime,accepted_CPIO=p.binding(abi.CPIO),
            prior_regex_sanitizer_gate=p.binding(module_gate),prior_plain_gate=p.binding(plain_gate),drafts=draft_records,
            limits=['No board/SSH/power/load/real runner action invoked','Original HOST_VERIFY outputs retained and refused by physical parser',
                    'Production-shaped parser/transport fixtures are synthetic, never FPGA evidence',
                    'Performance8-cell schemas are synthetic shape tests, not256-loop host/application performance',
                    'Prior ASAN/UBSAN gate applies to unchanged regex C/module; host libc DSO uninstrumented/LSan off'])
    except BaseException as error:record.update(state='FAIL offline preparation',error=repr(error));raise
    finally:
        (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n');print(out,record['state'],flush=True)


if __name__=='__main__':main()
