#!/usr/bin/env python3
"""Software-only cold08 advisory gate on the exact passed1280/native0 model."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from run_isolated import artifact,limits,TOP

HERE=Path(__file__).resolve().parent
COLD=TOP/'research/large-retained-capacity-20261121/advisory-full-system08'
FIXTURE=TOP/'research/retained-control-abi-20261121/advisory-fixture-cold08/manifest.json'
PASS='[BSG-PASS] retained advisory full-line I/D checked all words completed'


def verify(b):
    if artifact(b['path'])!=b:raise ValueError('changed binding: '+b['path'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--integrity-session',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    integrity=a.integrity_session.resolve();m=json.loads(integrity.read_text());out=a.output.resolve()
    if out.exists() or not str(out).startswith('/home/coyang/'):raise ValueError('new HOME runtime output required')
    if m['state']!='PASS-complete-checked-system-1280-native0-scoped-assertions':raise ValueError('closed1280 integration PASS required')
    verify(m['build_session']);build=json.loads(Path(m['build_session']['path']).read_text())
    for b in build['sources_before'].values():verify(b)
    for key in ('executable','actual_source_list'):verify(build[key])
    f=json.loads(FIXTURE.read_text());verify(f['source']);verify(f['elf'])
    if f['elf']['sha256']!='3fe096173e3a63b2656c1fadf0a058a328fb5f1ee375be652176408856f897b8':raise ValueError('not exact frozen cold08 ELF')
    archive=json.loads((COLD/'archive.json').read_text());out.mkdir()
    compressed={}
    for n in ('prog.riscv.gz','prog.nbf.gz'):
        raw=(COLD/n).read_bytes();expected=archive['files'][n]
        if hashlib.sha256(raw).hexdigest()!=expected['sha256']:raise ValueError('compressed archive mismatch')
        content=gzip.decompress(raw)
        if len(content)!=expected['raw_bytes'] or hashlib.sha256(content).hexdigest()!=expected['raw_sha256']:raise ValueError('raw archive mismatch')
        (out/n[:-3]).write_bytes(content);compressed[n]=artifact(COLD/n)
    if artifact(out/'prog.riscv')['sha256']!=f['elf']['sha256']:raise ValueError('ELF archive differs from fixture')
    env=dict(os.environ);env['LD_LIBRARY_PATH']=m['environment']['LD_LIBRARY_PATH']
    trace=out/'retained1280-cold08-native0.fst';cmd=[m['executable']['path'],'+c_args='+str(out/'prog.nbf')+' 600000','+bsg_trace='+str(trace)]
    record=dict(state='running',integrity_session=artifact(integrity),build_session=m['build_session'],script=artifact(__file__),
                executable=m['executable'],model_source_list=build['actual_source_list'],fixture_manifest=artifact(FIXTURE),
                archived_program=compressed,elf=artifact(out/'prog.riscv'),nbf=artifact(out/'prog.nbf'),geometry=m['geometry'],topology=m['topology'],hp0_response_delay=0,
                environment=m['environment'],command=dict(argv=cmd,cwd=str(out),native_seconds=600,host_seconds=780),
                scope='Scaled synthetic full-core advisory functionality only. No capacity utilization/application performance/FPGA claim. Strict publication/hit/full-refill trace audit required separately.')
    (out/'session.json').write_text(json.dumps(record,indent=2)+'\n')
    try:
        start=time.monotonic()
        with (out/'run.log').open('wb') as log:r=subprocess.run(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=780,preexec_fn=limits)
        record['command'].update(returncode=r.returncode,elapsed_seconds=time.monotonic()-start,log=artifact(out/'run.log'))
        check=['python3',str(TOP/'testing/check_run.py'),str(out/'run.log'),'--exit-code',str(r.returncode)]
        checked=subprocess.run(check,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);(out/'checker.log').write_text(checked.stdout)
        record['checker']=dict(argv=check,returncode=checked.returncode,log=artifact(out/'checker.log'))
        if checked.returncode:raise ValueError('maintained generic completion checker rejected run')
        text=(out/'run.log').read_text()
        if text.count(PASS)!=1 or text.index(PASS)>text.index('CORE PASS'):raise ValueError('fixture success absent/bad order')
        if text.count('Verilator assertion setting restored to 1')!=1:raise ValueError('runtime assertions absent')
        for b in build['sources_before'].values():verify(b)
        verify(f['source']);verify(f['elf']);verify(m['executable'])
        record['trace']=artifact(trace);record['state']='PASS-complete-advisory-execution-awaiting-strict-trace-audit'
    except BaseException as e:record.update(state='FAIL-preserved-no-result',error=repr(e));raise
    finally:
        (out/'session.json').write_text(json.dumps(record,indent=2)+'\n');print(out/'session.json',record['state'])

if __name__=='__main__':main()
