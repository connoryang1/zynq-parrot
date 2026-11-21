#!/usr/bin/env python3
"""Exactly three fresh near-limit component builds, two clocks each; no retry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ORIGINAL=ROOT/'testing/rtl/retained-metadata'
BP=ROOT/'import/black-parrot'
RESERVE=3*1024**3
ALLOCATION=768*1024**2
CAPACITIES=(1792,1856,1920)
RTL=BP/'bp_common/src/v/bp_retained_line_store.sv'

def bind(p):
    data=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

def git(p,*args):return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()

def usage(out):return sum(p.stat().st_size for p in out.rglob('*') if p.is_file())

def check_resources(out):
    used=usage(out);free=shutil.disk_usage(out).free
    assert used<=ALLOCATION and free>=RESERVE+max(0,ALLOCATION-used),'fixed768MiB allocation/3GiB reserve'
    return dict(output_bytes=used,free_bytes=free)

def validate_sources():
    assert git(BP,'rev-parse','HEAD')=='19bd0da2afa835230a19669ecb06e40498373a4b'
    assert not git(BP,'status','--porcelain','--untracked-files=normal')
    assert bind(RTL)['sha256']=='bd4cd65c92bdaf8af80c9c6f4643383c8bfa7fd335ca131319d44c2e45ee2e24'
    assert bind(HERE/'reference-d766.sv')['sha256']=='aa36581844c5563f77bcc12f531776a4c858b1470a202d8f8394c7a02a7f8ea7'
    for n in ('driver.cpp','retained_metadata_wrapper.sv','reference-d766.sv'):
        assert (HERE/n).read_bytes()==(ORIGINAL/n).read_bytes(),'frozen original collateral differs'
    return [bind(RTL)]+[bind(HERE/n) for n in ('driver.cpp','retained_metadata_wrapper.sv','reference-d766.sv','run.py','cohort.py')]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve()
    assert out.parent==Path('/home/coyang/fpga-artifacts/context-resume/retained-metadata-near-limit-20261121') and not out.exists()
    out.parent.mkdir(exist_ok=True)
    assert shutil.disk_usage(out.parent).free>=RESERVE+ALLOCATION
    frozen=validate_sources();out.mkdir()
    admission=dict(state='root-admitted-one-three-capacity-component-sweep',source_top=git(ROOT,'rev-parse','HEAD'),source_bp=git(BP,'rev-parse','HEAD'),sources=frozen,capacities=list(CAPACITIES),sets=256,epoch_width=8,clocks=['inverted','different-periods'],allocation_bytes=ALLOCATION,reserve_bytes=RESERVE,runtime_file_bytes=150*1024**2,build_timeout_s=300,run_timeout_s=120,attempts_per_capacity=1,resources=check_resources(out),authority='Root NEW_TASK: one bounded component sweep, no automatic retry/extension; no RTL/fullmodel/FPGA/apps/board.')
    (out/'admission.json').write_text(json.dumps(admission,indent=2)+'\n')
    record=dict(state='running',admission=bind(out/'admission.json'),closed=[])
    def save(): (out/'session.json').write_text(json.dumps(record,indent=2)+'\n')
    save();print('ADMISSION '+admission['source_bp']+' '+record['admission']['sha256'],flush=True)
    try:
        for cap in CAPACITIES:
            name='s256-i%d-d%d-e8'%(cap,cap);dest=out/name
            argv=[sys.executable,str(HERE/'run.py'),'--output',str(dest),'--sets','256','--i-lines',str(cap),'--d-lines',str(cap),'--epoch-width','8']
            rec=dict(capacity=cap,argv=argv,started=time.time());record['closed'].append(rec);save()
            with (out/(name+'.log')).open('wb') as log:
                child=subprocess.Popen(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                rec['owned_pgid']=child.pid;save()
                try:
                    while child.poll() is None:
                        check_resources(out)
                        # Inner timeouts are the unchanged build300/run120;
                        # this guard covers only their fixed total plus setup.
                        if time.time()-rec['started']>600:raise TimeoutError('outer component setup/build/two-run watchdog')
                        try:child.wait(timeout=1)
                        except subprocess.TimeoutExpired:pass
                except BaseException:
                    if child.poll() is None:
                        os.killpg(child.pid,signal.SIGTERM)
                        try:child.wait(timeout=5)
                        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                    raise
            rec.update(returncode=child.returncode,elapsed_seconds=time.time()-rec['started'],log=bind(out/(name+'.log')))
            save();assert child.returncode==0,name+' failed'
            m=json.loads((dest/'manifest.json').read_text());assert m['state']=='PASS-metadata-cycle-payload-coherence-miter'
            assert [r['mode'] for r in m['runs']]==['inverted','different-periods']
            rec['manifest']=bind(dest/'manifest.json');rec['resources']=check_resources(out)
            assert validate_sources()==frozen,'frozen source changed';save()
        record['state']='PASS-three-near-limit-capacities-six-clock-runs-component-only'
        record['resources_after']=check_resources(out)
    except BaseException as e:
        record.update(state='FAIL-preserved-no-retry-or-extension',error=repr(e));raise
    finally:save();print(record['state'],flush=True)

if __name__=='__main__':main()
