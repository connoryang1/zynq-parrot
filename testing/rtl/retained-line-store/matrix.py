#!/usr/bin/env python3
"""Sequential disjoint traced unit configurations; no board or full-core run."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CASES = [(0,0),(64,0),(0,64),(64,64),(128,128),(256,256),(512,512),
         (1024,1024),(1280,1280),(1320,1320),(1536,1536)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result=dict(state='running',scope='Configured full-line capacity and protocol correctness only; no routed fit or useful-capacity/performance claim.',
                matrix_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cases=[])
    try:
        for i,d in CASES:
            directory=out/f'i{i}-d{d}'
            command=[sys.executable,'-B',str(HERE/'run.py'),'--i-lines',str(i),'--d-lines',str(d),'--output',str(directory)]
            process=subprocess.run(command,check=False)
            manifest=directory/'manifest.json'
            row=dict(i_lines=i,d_lines=d,argv=command,returncode=process.returncode)
            if manifest.exists():
                data=json.loads(manifest.read_text());row.update(state=data['state'],manifest=str(manifest),manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
            result['cases'].append(row)
            if process.returncode:raise RuntimeError('matrix stops at first failure, no result from failed case')
        result['state']='PASS-all-directed-capacity-configurations'
    except BaseException as error:
        result.update(state='FAIL-preserved-no-matrix-result',error=repr(error));raise
    finally:
        (out/'matrix.json').write_text(json.dumps(result,indent=2)+'\n')
        print(out,result['state'])


if __name__=='__main__':main()
