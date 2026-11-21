#!/usr/bin/env python3
"""Build the actual counter module in a new isolated output, with edge checks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def bind(path):
    path=Path(path).resolve();data=path.read_bytes()
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parents[3];here=Path(__file__).resolve().parent
    output=args.out.resolve();output.mkdir(parents=True,exist_ok=False)
    sources=[root/'cosim/v/bp_retained_use_counters.sv',here/'driver.cpp',Path(__file__).resolve()]
    before=[bind(path) for path in sources]
    command=['/home/coyang/zynq-parrot-linux-research/install/bin/verilator','--cc','--exe','--build','--assert','--trace-fst',
             '--top-module','bp_retained_use_counters','--prefix','VRetainedUse','--Mdir',str(output/'obj'),'-j','2',
             str(sources[0]),str(sources[1])]
    (output/'command.json').write_text(json.dumps(command,indent=2)+'\n')
    with (output/'build.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    with (output/'run.log').open('w') as log:subprocess.run([str(output/'obj/VRetainedUse')],cwd=output,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=30)
    if before!=[bind(path) for path in sources]:raise ValueError('unit source changed')
    if 'RETAINED_USE_UNIT_PASS' not in (output/'run.log').read_text():raise ValueError('missing marker')
    (output/'verification.json').write_text(json.dumps(dict(state='PASS standalone counters; no hierarchy/core/FPGA proof',
        sources=before,outputs=[bind(output/name) for name in ('command.json','build.log','run.log','unit.fst','obj/VRetainedUse')]),indent=2)+'\n')
    print((output/'run.log').read_text(),end='')


if __name__=='__main__':main()
