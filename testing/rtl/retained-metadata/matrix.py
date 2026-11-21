#!/usr/bin/env python3
"""One sequential component sweep; failures preserved, no automatic retry."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CASES=[(64,n,n,2) for n in (0,64,128,256,512,1024,1280,1320,1344,1408,1536)]+[
    (64,93,131,2),(64,0,64,2),(64,64,0,2),(256,1280,1280,8),
    (256,259,517,2),(256,93,131,2),(1,1,1,2),(1,0,3,8),(2,2,3,2)]

def binding(p):
    data=p.read_bytes();return dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-root',type=Path,required=True)
    ap.add_argument('--evidence',type=Path,required=True)
    args=ap.parse_args();build=args.build_root.resolve();evidence=args.evidence.resolve()
    assert not build.exists() and not evidence.exists(),'fresh output directories only'
    assert shutil.disk_usage(build.parent).free>=3*1024**3+512*1024**2,'3GiB reserve plus512MiB bounded sweep'
    build.mkdir();evidence.mkdir(parents=True)
    sources=[ROOT/'import/black-parrot/bp_common/src/v/bp_retained_line_store.sv']+[HERE/n for n in ('reference-d766.sv','retained_metadata_wrapper.sv','driver.cpp','run.py','matrix.py')]
    freeze=[binding(p) for p in sources]
    record=dict(state='running',cases=CASES,sources=freeze,closed=[])
    (evidence/'source').mkdir()
    for p in sources:shutil.copyfile(p,evidence/'source'/p.name)
    try:
        for sets,il,dl,epoch in CASES:
            name=f's{sets}-i{il}-d{dl}-e{epoch}'
            command=[sys.executable,str(HERE/'run.py'),'--output',str(build/name),'--sets',str(sets),'--i-lines',str(il),'--d-lines',str(dl),'--epoch-width',str(epoch)]
            with (evidence/(name+'.log')).open('wb') as f:
                result=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=600)
            closed=evidence/name;closed.mkdir()
            if (build/name/'manifest.json').exists():
                manifest=json.loads((build/name/'manifest.json').read_text())
                shutil.copyfile(build/name/'manifest.json',closed/'manifest.json')
                for log in ('build.log','version.log','run-inverted.log','run-different-periods.log'):
                    if (build/name/log).exists():shutil.copyfile(build/name/log,closed/log)
            else:manifest=dict(state='FAIL-no-manifest')
            record['closed'].append(dict(name=name,returncode=result.returncode,manifest=manifest))
            (evidence/'matrix.json').write_text(json.dumps(record,indent=2)+'\n')
            assert result.returncode==0 and manifest['state']=='PASS-metadata-cycle-payload-coherence-miter',name+' failed'
            assert freeze==[binding(p) for p in sources],'source changed'
        record['state']='PASS-20-geometries-two-clocks-cycle-payload-coherence-miter'
    except BaseException as e:
        record.update(state='FAIL-preserved-no-automatic-retry',error=repr(e));raise
    finally:
        (evidence/'matrix.json').write_text(json.dumps(record,indent=2)+'\n')
        print(evidence,record['state'])

if __name__=='__main__':main()
