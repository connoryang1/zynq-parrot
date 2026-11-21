#!/usr/bin/env python3
"""Sequential clean isolated tag-row correctness/service gates; no FPGA action."""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import time
from service import artifact

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RTL=ROOT/'import/black-parrot/bp_common/src/v/bp_retained_line_store.sv'
SOURCES=[RTL,HERE/'retained_tagrows_wrapper.sv',HERE/'driver.cpp',HERE/'service.py',Path(__file__)]
CASES=[(256,1280,1280),(256,259,517),(256,0,0),(256,0,1280),(256,1280,0),(64,1280,1280),(256,2048,2048),(256,2049,2049)]


def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))


def validate_paths(work,archive):
    work=work.resolve();archive=archive.resolve()
    if not str(work).startswith('/home/coyang/'):raise ValueError('isolated HOME output required')
    if str(archive).startswith('/dev/shm/'):raise ValueError('small closed evidence must be durable')
    if work.exists() or archive.exists():raise ValueError('new work and archive directories required; no retries')
    return work,archive


def one(sets,i,d,work,archive,verilator):
    work.mkdir(parents=True,exist_ok=False);archive.mkdir(parents=True,exist_ok=False)
    sources={p.name:artifact(p) for p in SOURCES}
    m=dict(state='running',i_lines=i,d_lines=d,retained_sets=sets,sources=sources,commands=[],clock_results=[],
           scope='Full64B backend functional capacity and own-lane accepted-edge service only; ordinary L1 unchanged. No application, unique-retention, fit, routed timing or FPGA claim.')
    (archive/'source').mkdir()
    for p in SOURCES:shutil.copyfile(p,archive/'source'/p.name)
    def run(label,argv,cwd,seconds):
        cmd=dict(label=label,argv=list(map(str,argv)),cwd=str(cwd),timeout_seconds=seconds)
        m['commands'].append(cmd);start=time.monotonic()
        with (archive/(label+'.log')).open('wb') as log:
            r=subprocess.run(cmd['argv'],cwd=cwd,stdout=log,stderr=subprocess.STDOUT,timeout=seconds,preexec_fn=limits)
        cmd.update(returncode=r.returncode,elapsed_seconds=time.monotonic()-start,log=artifact(archive/(label+'.log')))
        if r.returncode:raise RuntimeError(label+' failed')
    try:
        run('version',[verilator,'--version'],work,10)
        run('build',[verilator,'--cc','--exe','--build','--trace-fst','--assert','-Wall','--top-module','retained_tagrows_wrapper',
                     '-GI_LINES='+str(i),'-GD_LINES='+str(d),'-GRETAINED_SETS='+str(sets),'-CFLAGS','-std=c++14','-j','2',
                     '--Mdir',work/'obj',RTL,HERE/'retained_tagrows_wrapper.sv',HERE/'driver.cpp'],work,300)
        exe=work/'obj/Vretained_tagrows_wrapper';m['executable']=artifact(exe)
        for mode in ('inverted','different-periods'):
            runtime=work/mode;runtime.mkdir()
            run('run-'+mode,[exe]+(['different-periods'] if mode=='different-periods' else []),runtime,120)
            log=(archive/('run-'+mode+'.log')).read_text()
            expected=f'RETAINED_TAGROWS_PASS I={i} D={d} SETS={sets} clock={mode}'
            if log.count(expected)!=1 or log.count('RETAINED_TEST_EXIT_CLEAN')!=1:raise ValueError('missing exact completion')
            rows=re.findall(r'^RETAINED_COUNTS lane=(\d) queries=(\d+) responses=(\d+) inserts=(\d+) terminals=(\d+) published=(\d+)$',log,re.M)
            if len(rows)!=2 or {r[0] for r in rows}!={'0','1'}:raise ValueError('count schema')
            for r in rows:
                if int(r[1])!=int(r[2]) or int(r[3])!=int(r[4]):raise ValueError('ownership count')
            # Keep only small evidence on HOME; executable and objects remain in RAM.
            dst=archive/mode;dst.mkdir();shutil.copyfile(runtime/'retained-line-store.fst',dst/'retained-line-store.fst')
            m['clock_results'].append(dict(clock_mode=mode,counts=rows,fst=artifact(dst/'retained-line-store.fst')))
        for p in SOURCES:
            if artifact(p)!=sources[p.name]:raise ValueError('source changed during gate')
        m['state']='PASS-retained-tagrows'
    except BaseException as e:
        m.update(state='FAIL-preserved-no-result',error=repr(e));raise
    finally:(archive/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    run('service-audit',['python3',HERE/'service.py','--manifest',archive/'manifest.json','--sets',str(sets),'--output',archive/'service'],work,240)
    # The manifest remains immutable during its audit; bind post-audit invocation separately.
    (archive/'post-audit.json').write_text(json.dumps(dict(state='PASS',analysis=artifact(archive/'service/analysis.json'),command=m['commands'][-1]),indent=2)+'\n')
    return dict(sets=sets,i_lines=i,d_lines=d,manifest=artifact(archive/'manifest.json'),service=artifact(archive/'service/analysis.json'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True);p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--verilator',default='/home/coyang/zynq-parrot-linux-research/install/bin/verilator')
    p.add_argument('--case',choices=['all']+[f'{s}:{i}:{d}' for s,i,d in CASES],default='all')
    a=p.parse_args();work,archive=validate_paths(a.work,a.archive)
    if shutil.disk_usage(work.parent).free<512*1024*1024:raise ValueError('need512MiB output headroom')
    if shutil.disk_usage(archive.parent).free<48*1024*1024:raise ValueError('need48MiB durable headroom for closed FSTs')
    work.mkdir();archive.mkdir();results=[]
    for s,i,d in CASES:
        if a.case!='all' and a.case!=f'{s}:{i}:{d}':continue
        name=f's{s}-i{i}-d{d}'
        results.append(one(s,i,d,work/name,archive/name,a.verilator))
        (archive/'summary.json').write_text(json.dumps(dict(state='running',results=results),indent=2)+'\n')
    (archive/'summary.json').write_text(json.dumps(dict(state='PASS-tagrow-and-fallback-component-cases',results=results),indent=2)+'\n')
    print(archive/'summary.json')

if __name__=='__main__':main()
