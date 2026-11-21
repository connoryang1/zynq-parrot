#!/usr/bin/env python3
"""Archive closed passing component evidence only; never runs a model."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from matrix import CASES

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BP=ROOT/'import/black-parrot'

def binding(p):
    raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--matrix',type=Path,required=True)
    ap.add_argument('--archive',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();matrix_path=args.matrix.resolve();d=json.loads(matrix_path.read_text())
    assert d['state']=='PASS-20-geometries-two-clocks-cycle-payload-coherence-miter'
    assert d['cases']==[list(c) for c in CASES] and len(d['closed'])==20
    assert all(binding(Path(s['path']))==s for s in d['sources']),'final source freeze'
    reference=HERE/'reference-d766.sv'
    original=subprocess.check_output(['git','-C',str(BP),'show','d766d42cdf04ee43ca1e915fb9da06f5cc117dde:bp_common/src/v/bp_retained_line_store.sv'])
    assert reference.read_bytes()==original
    assert shutil.disk_usage(args.archive.parent).free>=3*1024**3+256*1024**2
    archive=args.archive.resolve();archive.mkdir(exist_ok=False)
    runs=[]
    for closed in d['closed']:
        assert closed['returncode']==0
        m=closed['manifest'];assert m['state']=='PASS-metadata-cycle-payload-coherence-miter'
        assert m['sources'][:4]==d['sources'][:4]
        compiled=Path(m['compiled_reference']['path'])
        assert compiled.read_text()==original.decode().replace('module bp_retained_line_store\n','module bp_retained_line_store_reference\n')
        for run in m['runs']:
            p=Path(run['fst']['path']);assert binding(p)==run['fst']
            dest=archive/(closed['name']+'-'+run['mode']+'.fst');shutil.copyfile(p,dest)
            assert dest.read_bytes()==p.read_bytes()
            log=matrix_path.parent/closed['name']/('run-'+run['mode']+'.log')
            text=log.read_text()
            assert text.count('RETAINED_METADATA_RANDOM_PASS deterministic_ticks=80000 seed=0x71b49a23')==1
            assert text.count('RETAINED_METADATA_HAZARDS_PASS geometry_conditional=1')==1
            rows=re.findall(r'RETAINED_COUNTS lane=(\d) queries=(\d+) responses=(\d+) inserts=(\d+) terminals=(\d+) published=(\d+)',text)
            assert len(rows)==2 and {r[0] for r in rows}=={'0','1'}
            assert all(r[1]==r[2] and r[3]==r[4] for r in rows)
            assert len(re.findall(r'RETAINED_CAPACITY_CHECK lane=\d lines=\d+ full64B=1',text))==2
            runs.append(dict(geometry=closed['name'],clock=run['mode'],counts=rows,log=binding(log),original_fst=run['fst'],durable_fst=binding(dest)))
    assert len(runs)==40
    report=dict(state='PASS-closed-component-only-20-geometries-40-clock-runs',matrix=binding(matrix_path),sources=d['sources'],reference_bp='d766d42cdf04ee43ca1e915fb9da06f5cc117dde',reference=binding(reference),runs=runs,randomized_ticks_total=40*80000,free_bytes_after=shutil.disk_usage(archive).free,scope='Cycle/full-payload/coherence component equivalence; no synthesis/inference/area/full-core/application/FPGA result.')
    assert report['free_bytes_after']>=3*1024**3
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(report['state'])

if __name__=='__main__':main()
