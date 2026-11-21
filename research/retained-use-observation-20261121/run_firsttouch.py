#!/usr/bin/env python3
"""Execute only a closed clean observer model with the exact accepted cold08 input."""
import argparse
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import subprocess

from build_full import ROOT,binding,write


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    build=args.build.resolve();accepted=build/'build-accepted.json'
    status=json.loads((accepted if accepted.exists() else build/'status.json').read_text())
    if status['state']!='PASS clean actual-fulltop build; runtime pending':raise ValueError('clean completed model required')
    model=Path(status['model']['path'])
    if binding(model)!=status['model']:raise ValueError('model changed')
    source_list=json.loads((build/'actual-source-list.json').read_text())
    for path,record in source_list['sources'].items():
        if binding(path)!=record:raise ValueError('compiled source changed: '+path)
    output=args.out.resolve();output.mkdir(parents=True,exist_ok=False)
    archived=ROOT/'research/large-retained-capacity-20261121/advisory-full-system08'
    old=json.loads(gzip.decompress((archived/'admission.json.gz').read_bytes()))
    for name in ('prog.riscv','prog.nbf'):(output/name).write_bytes(gzip.decompress((archived/(name+'.gz')).read_bytes()))
    if binding(output/'prog.riscv')['sha256']!=old['elf_sha256'] or binding(output/'prog.nbf')['sha256']!=old['nbf_sha256']:
        raise ValueError('accepted cold08 archive identity')
    command=[str(model),'+c_args=prog.nbf 180000','+bsg_trace='+str(output/'trace.fst')]
    write(output/'admission.json',dict(model=status['model'],compiled_sources=binding(build/'actual-source-list.json'),
        elf=binding(output/'prog.riscv'),nbf=binding(output/'prog.nbf'),command=command,
        native_host_runtime_ms=180000,outer_timeout_s=240,fst_limit_bytes=256*1024*1024,
        expected_counter_words=dict(i_hits=1,d_hits=1,i_published=1,d_published=1,i_write_beats=8,d_write_beats=8),
        scope='Scoped wholecore connection/GP0 observation correctness only, no FPGA/fit/capacity/performance claim'))
    env=os.environ.copy();env['LD_LIBRARY_PATH']='/home/coyang/zynq-parrot-linux-research/install/lib'+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024*1024,256*1024*1024))
    with (output/'run.log').open('w') as log:
        result=subprocess.run(command,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240,preexec_fn=limits)
    write(output/'process.json',dict(returncode=result.returncode))
    text=(output/'run.log').read_text(errors='replace')
    spec=importlib.util.spec_from_file_location('checker',ROOT/'testing/check_run.py');checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    checker.check_transcript(text,result.returncode)
    marker='[BSG-PASS] retained advisory full-line I/D checked all words completed'
    if text.count(marker)!=1 or text.index(marker)>checker.CORE_PASS.search(text).start():raise ValueError('missing completed exact fixture')
    rows=re.findall(r'RETAINED_USE_COUNTERS version=1 i_hits=(\d+) d_hits=(\d+) i_published=(\d+) d_published=(\d+) i_write_beats=(\d+) d_write_beats=(\d+) saturating_bits=16 reset=axi_only',text)
    if len(rows)!=1 or tuple(map(int,rows[0]))!=(1,1,1,1,8,8):raise ValueError('actual GP0 observer counts: '+repr(rows))
    if binding(model)!=status['model']:raise ValueError('model changed during runtime')
    write(output/'verification.json',dict(state='PASS complete scoped wholecore and actual GP0 1hit/1publish/8writes per lane; strict closed trace audit pending',
        actual_returncode=result.returncode,known_postPASS_GPIO_exception=result.returncode!=0,
        counter_values=rows[0],sources=binding(build/'actual-source-list.json'),
        files=[binding(output/name) for name in ('admission.json','process.json','run.log','prog.riscv','prog.nbf','trace.fst')],
        limits='No board/route/area/timing/useful-capacity/performance result. Same retained64/64 payload and original cache geometry; model includes observed fulltop.'))
    print(output/'verification.json')


if __name__=='__main__':main()
