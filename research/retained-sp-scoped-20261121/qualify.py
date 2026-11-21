#!/usr/bin/env python3
"""One reviewed SP cold08 qualification; no build, retry or application execution."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
from common import *
from canonical import extract,declarations,equivalent,MAX_CANONICAL_BYTES
from framing import framing
from protocol import parse


def constraints(a):
    require(a['state']=='FROZEN-SP-COLD08-awaiting-root-target-review','not frozen cold08 admission')
    require(a['original_model']['sha256']==MODEL_SHA and a['proposal']['sha256']==PROPOSAL_SHA and
            a['native_identities']['sha256']==NATIVE_SHA,'wrong SP source/model identity')
    require(a['budget']==dict(native_seconds=180,host_seconds=360,FST_bytes=CAP,attempts=1,
            reader_seconds_per_domain=600,minimum_free_reserve_bytes=RESERVE,
            fixed_artifact_allocation_bytes=ARTIFACT_ALLOCATION,canonical_bytes_per_file=MAX_CANONICAL_BYTES),'changed fixed budget')
    p=proposal();require(a['domains']==p['reader_domains'] and a['writer_leaves']==p['leaves'],
                         'reviewed400-leaf/three-domain plan changed')
    require({n:len(x) for n,x in a['domains'].items()}==dict(core252=252,observer_and_geometry=45,SP_strict162=162),
            'wrong domain count/reader capacity')
    union={r['path']:r['width'] for rows in a['domains'].values() for r in rows}
    require(union=={r['path']:r['width'] for r in a['writer_leaves']},'writer/domain coverage gap')


def validate(a,approval_sha):
    require(bind(a['_path'])['sha256']==approval_sha,'reviewed admission SHA differs')
    constraints(a)
    for r in a['frozen_inputs'].values():verify(r)
    for r in a['compiled_sources'].values():verify(r)
    require(identities(tree(a['original_generated_root']))==identities(a['original_generated_files']),
            'original SP generated tree changed')
    require(identities(tree(Path(a['copied_model']['path']).parent))==identities(a['source_files']),
            'copied SP generated tree changed')
    b=json.loads(Path(a['build']['path']).read_text())
    require(b['state']=='BUILT-NOT-TARGET-QUALIFIED' and b['binary']==a['copied_model'] and
            b['baseline_relink']['sha256']==MODEL_SHA,'build/baseline-reproduction proof mismatch')


def claim_once(path,admission,output):
    with Path(path).open('x') as f:
        json.dump(dict(state='ONE-SP-cold08-ATTEMPT-no-retry',admission=bind(admission),output=str(output),pid=os.getpid()),f)
        f.flush();os.fsync(f.fileno())


def limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP))


def run_model(command,cwd,env,log):
    start=time.monotonic()
    with log.open('wb') as output:
        process=subprocess.Popen(command,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT,preexec_fn=limits)
        try:
            while process.poll() is None:
                require(time.monotonic()-start<HOST_SECONDS,'fixed360s host guard exceeded')
                require(shutil.disk_usage(HERE).free>RESERVE,'3GiB shared-HOME reserve breached')
                time.sleep(1)
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
    return process.returncode,time.monotonic()-start


def loader(binary,env):
    r=subprocess.run(['ldd',binary],env=env,capture_output=True,text=True,timeout=10)
    require(r.returncode==0 and 'not found' not in r.stdout,'loader preflight failed')
    libraries=[]
    for line in r.stdout.splitlines():
        for word in line.split():
            if word.startswith('/') and Path(word).is_file():libraries.append(bind(word))
    return r.stdout,libraries


def tool(argv,log,timeout):
    with log.open('w') as f:r=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    require(r.returncode==0,'maintained strict/observer verifier failed: '+str(log))


def qualify(admission,approval_sha,output):
    out=fresh_home(output);a=json.loads(Path(admission).read_text());a['_path']=str(Path(admission).resolve())
    validate(a,approval_sha);require(str(out)==a['qualifier_output'],'wrong fixed output')
    require(shutil.disk_usage(HERE).free>RESERVE+ARTIFACT_ALLOCATION,'reserve+fixed artifacts unavailable')
    claim_once(a['one_shot_claim'],admission,out);out.mkdir();runtime=out/'runtime';runtime.mkdir()
    journal=out/'qualification.json';state=dict(state='RUNNING-one-SP-cold08-attempt',admission=bind(admission),
        approval_sha256=approval_sha,source=bind(__file__),budget=a['budget'],domains={})
    save(journal,state)
    try:
        for key,file in (('elf','prog.riscv'),('nbf','prog.nbf')):
            shutil.copy2(a['reference'][key]['path'],runtime/file)
            require(bind(runtime/file)['sha256']==a['reference'][key]['sha256'],'copied cold08 input changed')
        env=dict(os.environ)
        for key in list(env):
            if key.startswith(('BSG_RUNTIME_PATCH_','BSG_TRACE_')):env.pop(key)
        env.update(a['environment']);text,libs=loader(a['copied_model']['path'],env)
        (runtime/'loader.log').write_text(text);require(libs==a['linked_libraries'],'native library identities changed')
        fst=runtime/'trace.fst';command=[a['copied_model']['path'],'+c_args=prog.nbf 180000','+bsg_trace='+str(fst)]
        save(runtime/'admission.json',dict(parent=bind(admission),model=a['copied_model'],command=command))
        validate(a,approval_sha);state.update(command=command,linked_libraries=libs);save(journal,state)
        rc,elapsed=run_model(command,runtime,env,runtime/'run.log')
        save(runtime/'process.json',dict(returncode=rc));state.update(returncode=rc,elapsed_seconds=elapsed,
            log=bind(runtime/'run.log'));save(journal,state)
        require(rc==a['reference']['returncode'],'native terminal behavior differs')
        guest=parse((runtime/'run.log').read_text(),rc)
        require(guest==a['reference']['guest'],'complete cold08/GP0/retired-count protocol differs')
        require(0<fst.stat().st_size<CAP,'missing/at-limit FST')
        frames=framing(fst);old_frames=framing(Path(a['reference']['trace']['path']))
        require((frames['header_start_tick'],frames['header_end_tick'])==
                (old_frames['header_start_tick'],old_frames['header_end_tick']),'complete clock endpoints differ')
        listing=subprocess.check_output([a['reader']['path'],str(fst),'--list'],text=True,timeout=60)
        declarations(listing,a['writer_leaves']);(out/'hierarchy.tsv').write_text(listing)
        state.update(state='COMPLETE-checks-PASS-awaiting-three-domain-equality',trace=bind(fst),
                     framing=frames,guest=guest,exact400_leaf_hierarchy=True);save(journal,state)
        # Same maintained source proof producer shape, parsed from actual output.
        spec=importlib.util.spec_from_file_location('SP_binding',SP/'research/retained-use-observation-20261121/build_full.py')
        producer=importlib.util.module_from_spec(spec);spec.loader.exec_module(producer)
        run_proof=dict(state='PASS complete scoped wholecore and actual GP0 1hit/1publish/8writes per lane; strict closed trace audit pending',
            actual_returncode=rc,known_postPASS_GPIO_exception=rc!=0,counter_values=guest['counter_values'],
            sources=producer.binding(ORIGINAL/'actual-source-list.json'),trace=bind(fst),
            files=[producer.binding(runtime/n) for n in ('admission.json','process.json','run.log','prog.riscv','prog.nbf','trace.fst')])
        save(runtime/'verification.json',run_proof)
        for name,leaves in a['domains'].items():
            require(shutil.disk_usage(HERE).free>RESERVE,'3GiB reserve breached before audit')
            result=extract(a['reader']['path'],fst,leaves,out/name,False)
            equivalent(a['original_canonical'][name],result)
            state['domains'][name]=result;save(journal,state)
        strict=SP/'testing/rtl/retained-advisory-trace/validate.py'
        tool([sys.executable,str(strict),'--fst',str(fst),'--reader',a['reader']['path'],
            '--model-source-list',str(ORIGINAL/'actual-source-list.json'),'--fixture-manifest',a['fixture_manifest']['path'],
            '--log',str(runtime/'run.log'),'--exit-code',str(rc),'--out',str(out/'strict'),'--reader-timeout','600'],
            out/'strict.log',720)
        strict_proof=json.loads((out/'strict/verification.json').read_text());require(strict_proof['accepted'] is True,'strict proof not accepted')
        observer=SP/'research/retained-use-observation-20261121/verify_counters.py'
        tool([sys.executable,str(observer),'--fst',str(fst),'--reader',a['reader']['path'],'--strict-proof',str(out/'strict/verification.json'),
            '--run-proof',str(runtime/'verification.json'),'--out',str(out/'observer')],out/'observer.log',300)
        obs=json.loads((out/'observer/verification.json').read_text())
        require(obs['state'].startswith('PASS actual counter transitions') and obs['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),
                'observer transition/GP0 proof not accepted')
        validate(a,approval_sha);require(shutil.disk_usage(HERE).free>RESERVE,'3GiB reserve breached')
        state.update(state='PASS-SP-COLD08-complete-three-domain-literal-equivalence-and-real-strict-observer-proofs',
            strict_proof=bind(out/'strict/verification.json'),observer_proof=bind(out/'observer/verification.json'))
    except BaseException as error:
        state.update(state='STOPPED-FAIL-preserved-no-retry-no-admission',error=repr(error))
        for n in ('run.log','trace.fst'):
            if (runtime/n).is_file():state[n]=bind(runtime/n)
        raise
    finally:
        save(journal,state);print(journal,state['state'],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--admission',type=Path,required=True)
    ap.add_argument('--approval-sha',required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();qualify(a.admission,a.approval_sha,a.output)
