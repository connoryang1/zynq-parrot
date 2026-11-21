#!/usr/bin/env python3
"""Elaborate the exact actual-fulltop source list with observation off; no model run."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess

from build_full import binding,write


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path);a=parser.parse_args()
    build=a.build.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    status=json.loads((build/'build-accepted.json').read_text());model=Path(status['model']['path'])
    before={str(p):binding(p) for p in [model,*list((build/'verilator/obj_dir').glob('.build_config-*')),
        build/'verilator/obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat']}
    prefix=json.loads((build/'source-before.json').read_text())['command_prefix']
    prefix=['BP_RETAINED_OBSERVE=0' if arg.startswith('BP_RETAINED_OBSERVE=') else arg for arg in prefix]
    planned=subprocess.run(prefix+['-n','build'],cwd=build/'verilator',capture_output=True,text=True,check=True,timeout=60)
    (out/'make-dryrun.log').write_text(planned.stdout+planned.stderr)
    lines=[line for line in planned.stdout.splitlines() if '/install/bin/verilator --assert ' in line and ' --cc ' in line]
    if len(lines)!=1:raise ValueError('one actual compiler command required')
    tokens=shlex.split(lines[0]);tokens=tokens[:tokens.index('2>&1')]
    command=[];skip=False
    for token in tokens:
        if skip:skip=False;continue
        if token in ('--build-jobs','-CFLAGS','-LDFLAGS'):skip=True;continue
        if token in ('--cc','--exe','--build') or token.endswith(('.cpp','.cc','.c')):continue
        command.append(token)
    command+=['--lint-only','--Mdir',str(out/'obj')]
    write(out/'command.json',command)
    env=os.environ.copy();env['LD_LIBRARY_PATH']='/home/coyang/zynq-parrot-linux-research/install/lib'
    with (out/'lint.log').open('w') as log:subprocess.run(command,cwd=build/'verilator',env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    if before!={p:binding(p) for p in before}:raise ValueError('dry-run/lint modified accepted model or stamp')
    write(out/'verification.json',dict(state='PASS exact actual-fulltop observation0 lint-only; no second model or execution',
        protected_before_after=before,command=binding(out/'command.json'),log=binding(out/'lint.log'),script=binding(__file__)))
    print(out/'verification.json')


if __name__=='__main__':main()
