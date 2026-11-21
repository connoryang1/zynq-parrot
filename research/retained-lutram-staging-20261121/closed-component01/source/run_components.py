#!/usr/bin/env python3
"""One frozen D64 then I64/BedRock64 real-UCE component gate; no other runs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BP=ROOT/'import/black-parrot'
BASE_BP='19bd0da2afa835230a19669ecb06e40498373a4b'
BASE_TOP='7bef800a3410754d228612664fe738e8f633ae05'
RESERVE=3*1024**3
ALLOCATION=256*1024**2
REL='bp_me/src/v/cce/bp_uce.sv'

def bind(p):
    raw=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def git(p,*args):return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()

def freeze():
    assert git(ROOT,'rev-parse','HEAD')==BASE_TOP and git(BP,'rev-parse','HEAD')==BASE_BP
    original=subprocess.check_output(['git','-C',str(BP),'show',BASE_BP+':'+REL]).decode()
    old='  for (genvar i = 0; i < block_size_in_fill_lp; i++) begin : prefetch_fill_bank\n    (* ram_style = "block" *)'
    new='  for (genvar i = 0; i < block_size_in_fill_lp; i++) begin : prefetch_fill_bank\n    // Retained production uses shallow four-slot banks. Use LUTRAM while\n    // preserving the registered read and same-slot old-data RTL semantics.\n    (* ram_style = "distributed" *)'
    assert original.count(old)==1 and (BP/REL).read_text()==original.replace(old,new),'only authorized attr/comment delta'
    assert git(BP,'diff','--name-only').splitlines()==[REL]
    runner=ROOT/'testing/rtl/run_uce_retained.py'
    tb=ROOT/'testing/rtl/uce_retained_tb.sv'
    for p in (runner,tb,ROOT/'testing/rtl/uce_retained_driver.cpp'):
        expected=subprocess.check_output(['git','-C',str(ROOT),'show',BASE_TOP+':'+str(p.relative_to(ROOT))])
        assert p.read_bytes()==expected,'existing UCE gate changed'
    assert '.prefetch_els_p(2)' in tb.read_text(),'record actual two-slot component scope'
    bsg=BP/'external/basejump_stl'
    assert (bsg/'.git').is_file() and git(bsg,'rev-parse','HEAD')=='3dff9f43af8e1bb850da0b41696514396fa0fa7e'
    assert not git(bsg,'status','--porcelain','--untracked-files=normal')
    sources=[BP/REL,BP/'bp_common/src/v/bp_retained_line_store.sv',runner,tb,ROOT/'testing/rtl/uce_retained_driver.cpp',Path(__file__).resolve()]
    sources += list((BP/'bp_common/src/include').glob('*'))+list((BP/'bp_me/src/include').glob('*'))
    return [bind(p) for p in sources if p.is_file()]

def check(out):
    used=sum(p.stat().st_size for p in out.rglob('*') if p.is_file());free=shutil.disk_usage(out).free
    assert used<=ALLOCATION and free>=RESERVE+max(0,ALLOCATION-used),'fixed256MiB allocation/3GiB reserve'
    return dict(output_bytes=used,free_bytes=free)

def groups(pgid):
    found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:fields=(p/'stat').read_text().rpartition(')')[2].split()
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
        if int(fields[2])==pgid and int(fields[3])==pgid:found.append(int(p.name))
    return found

def cancel(child):
    # Only the new session/process group created for this exact gate may be
    # signaled; cleanup remains necessary if its Python leader already exited.
    if groups(child.pid):
        os.killpg(child.pid,signal.SIGTERM)
        deadline=time.monotonic()+5
        while groups(child.pid) and time.monotonic()<deadline:time.sleep(.1)
        if groups(child.pid):os.killpg(child.pid,signal.SIGKILL)
    child.wait()

def limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(ALLOCATION,ALLOCATION))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    out=a.out.resolve();assert out.parent==Path('/home/coyang/fpga-artifacts/context-resume/retained-lutram-staging-20261121') and not out.exists()
    out.parent.mkdir(exist_ok=True);assert shutil.disk_usage(out.parent).free>=RESERVE+ALLOCATION
    frozen=freeze();out.mkdir()
    admission=dict(state='root-admitted-single-attribute-D64-then-I64-component-gate',base_top=BASE_TOP,base_bp=BASE_BP,sources=frozen,
        plan=[dict(id='d64',lines=64,instruction=False),dict(id='i64-bedrock64',lines=64,instruction=True,icache_fill_width=64)],
        component_prefetch_slots=2,mapped_bank_evidence_scope='separate root four-slot mapped proof',allocation_bytes=ALLOCATION,reserve_bytes=RESERVE,
        inner_build_timeout_s=240,inner_run_timeout_s=60,inner_short_assert_timeout_s=30,inner_short_drain_timeout_s=30,attempts_per_gate=1,
        resources=check(out),scope='Real UCE component functional gates only; no fullmodel/routed fit/FPGA/application/performance claim.')
    (out/'admission.json').write_text(json.dumps(admission,indent=2)+'\n');record=dict(state='running',admission=bind(out/'admission.json'),gates=[])
    def save():(out/'session.json').write_text(json.dumps(record,indent=2)+'\n')
    save();print('ADMISSION '+record['admission']['sha256'],flush=True)
    try:
        for ident,instruction in (('d64',False),('i64-bedrock64',True)):
            dest=out/ident;argv=[sys.executable,str(ROOT/'testing/rtl/run_uce_retained.py'),'--lines','64','--out',str(dest)]
            if instruction:argv+=['--icache','--icache-fill-width','64']
            row=dict(id=ident,argv=argv);record['gates'].append(row);save();started=time.monotonic()
            with (out/(ident+'.log')).open('wb') as log:
                child=subprocess.Popen(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
                row['owned_pgid']=child.pid;save()
                try:
                    while child.poll() is None:
                        check(out)
                        if time.monotonic()-started>400:raise TimeoutError('bounded sum of unchanged inner budgets plus setup')
                        try:child.wait(timeout=1)
                        except subprocess.TimeoutExpired:pass
                    assert child.returncode==0,ident+' failed'
                    assert not groups(child.pid),'owned component process group remains'
                except BaseException:cancel(child);raise
            proof=dest/'verification.json';v=json.loads(proof.read_text())
            assert v['passed'] is True and v['short_response_rejected'] is True and v['assertion_disabled_short_response_drained'] is True
            assert v['lines']==64 and v['instruction']==instruction
            if instruction:assert v['icache_fill_width']==64
            assert freeze()==frozen,'frozen sources changed'
            row.update(returncode=child.returncode,elapsed_seconds=time.monotonic()-started,verification=bind(proof),resources=check(out));save()
        record.update(state='PASS-D64-I64-original-UCE-gates-with-specific-short-assert-and-drain',resources_after=check(out))
    except BaseException as e:record.update(state='FAIL-preserved-no-retry-or-extension',error=repr(e));raise
    finally:save();print(record['state'],flush=True)

if __name__=='__main__':main()
