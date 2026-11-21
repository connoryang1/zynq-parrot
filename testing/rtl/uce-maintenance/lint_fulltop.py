#!/usr/bin/env python3
"""Lint the actual r2 fulltop source command after relocating only its worktree."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from run_endpoint import ROOT,bind

MODEL=Path('/home/coyang/fpga-artifacts/context-resume/native1280-observe1-r2-20261121/full01')
OLD='/home/coyang/zynq-parrot-linux-fit1280'


def warning_blocks(text):
    return [block for block in re.split(r'(?=^%Warning-)',text,flags=re.M) if block.startswith('%Warning-UNOPTFLAT:')]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    meta=MODEL/'verilator/obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat'
    tokens=shlex.split(shlex.split(meta.read_text().splitlines()[1])[1])
    # verFiles serializes the grouped host flag argument without preserving its
    # inner quoting. HDL defines/includes have their own +define/+incdir list.
    cflags=tokens.index('-CFLAGS');hdl=next(i for i,token in enumerate(tokens) if token.startswith('+define+'))
    tokens=tokens[:cflags]+tokens[hdl:]
    command=['/home/coyang/zynq-parrot-linux-research/install/bin/verilator']
    skip=False
    for token in tokens:
        if skip:skip=False;continue
        if token in ('--build-jobs','-CFLAGS','-LDFLAGS','--Mdir'):skip=True;continue
        if token in ('--cc','--exe','--build') or token.endswith(('.cpp','.cc','.c')):continue
        command.append(token.replace(OLD,str(ROOT)).replace(str(MODEL/'verilator'),str(out)))
    command+=['--lint-only','--report-unoptflat','--Mdir',str(out/'obj')]
    copies=[]
    for name in ('bsg_blackparrot_pkg.sv','bsg_bootrom.sv'):
        source=MODEL/'verilator'/name;target=out/name;shutil.copyfile(source,target)
        if bind(source)['sha256']!=bind(target)['sha256']:raise ValueError('generated collateral copy')
        copies.append(dict(source=bind(source),copy=bind(target)))
    before=bind(ROOT/'import/black-parrot/bp_me/src/v/cce/bp_uce.sv')
    (out/'command.json').write_text(json.dumps(command,indent=2)+'\n')
    env=os.environ.copy();env['LD_LIBRARY_PATH']='/home/coyang/zynq-parrot-linux-research/install/lib'
    with (out/'lint.log').open('w') as log:subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    if before!=bind(before['path']):raise ValueError('UCE source drift')
    baseline=warning_blocks((MODEL/'build.log').read_text());current=warning_blocks((out/'lint.log').read_text())
    relevant=lambda block:'retained_maintenance' in block or 'retained_clear' in block
    old=[block for block in baseline if relevant(block)];new=[block for block in current if relevant(block)]
    if not old or new:raise ValueError('retained-maintenance structural cycle not discriminated/removed')
    result=dict(state='PASS actual1280+observe1 fulltop lint; retained-maintenance UNOPTFLAT paths removed',
                uce=before,original_model_metadata=bind(meta),baseline_build_log=bind(MODEL/'build.log'),
                baseline_relevant_unoptflat=old,current_relevant_unoptflat=new,
                other_current_unoptflat=current,generated_copies=copies,command=bind(out/'command.json'),log=bind(out/'lint.log'),
                auditor=bind(__file__),scope='Exact r2 flags/source list relocated to new source worktree; old known unrelated warnings retained. Not Vivado synthesis, implementation timing, or an all-warning waiver.')
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'verification.json')


if __name__=='__main__':main()
