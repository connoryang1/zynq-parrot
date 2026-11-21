#!/usr/bin/env python3
"""Capture source-only reasoning and compact endpoint/lint proofs, not models."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'testing/rtl/uce-maintenance'))
from run_endpoint import bind


def main():
    out=HERE/'source-gate001';out.mkdir(exist_ok=False)
    bp=ROOT/'import/black-parrot';uce=bp/'bp_me/src/v/cce/bp_uce.sv'
    old=subprocess.check_output(['git','-C',str(bp),'show','e10992a3eea3ba2ef6ae3ccb42ff5e8c658286a8:bp_me/src/v/cce/bp_uce.sv'],text=True)
    def fsm(text):
        first=text.index('  logic blocking_req_v_lo;')
        last=text.index('  always_ff @(posedge clk_i) begin\n    if (reset_i) begin\n      prefetch_install_state_r',first)
        return text[first:last]
    if fsm(old)!=fsm(uce.read_text()):raise ValueError('common final-yumi FSM changed')
    external=Path('/home/coyang/fpga-artifacts/context-resume/retained-maintenance-acyclic-20261121')
    endpoint=json.loads((external/'endpoint02/verification.json').read_text())
    lint=json.loads((external/'fulltop-lint02/verification.json').read_text())
    if not endpoint['state'].startswith('PASS') or not lint['state'].startswith('PASS'):raise ValueError('source gates incomplete')
    paths=[uce,HERE/'README.md',Path(__file__).resolve()]
    paths+=list((ROOT/'testing/rtl/uce-maintenance').glob('*.py'))+list((ROOT/'testing/rtl/uce-maintenance').glob('*.sv'))+list((ROOT/'testing/rtl/uce-maintenance').glob('*.cpp'))
    originals=[]
    for directory,names in {'endpoint01':['command.json','build.log','run.log'],
        'endpoint02':['command.json','build.log','run.log','verification.json'],
        'fulltop-lint01':['command.json','lint.log'],
        'fulltop-lint02':['command.json','lint.log','verification.json']}.items():
        for name in names:paths.append(external/directory/name)
    for path in paths:
        relative='sources/'+str(path.relative_to(ROOT)) if str(path).startswith(str(ROOT)+'/') else str(path.relative_to(external))
        target=out/(relative+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(gzip.compress(path.read_bytes(),mtime=0));originals.append(dict(original=bind(path),snapshot=bind(target)))
    console=Path('/home/coyang/fpga-logs-linux-retained-native1280-r2/20261121T102215Z-15288321b/console.log')
    rows=console.read_text().splitlines(keepends=True);excerpts=[]
    for name,first,last in [('preliminary-RAM',6400,6410),('timing-loop',6604,6645)]:
        target=out/(name+'.log.gz');raw=''.join(rows[first-1:last]).encode();target.write_bytes(gzip.compress(raw,mtime=0))
        excerpts.append(dict(source_path=str(console),first_line=first,last_line=last,uncompressed_sha256=hashlib.sha256(raw).hexdigest(),snapshot=bind(target)))
    result=dict(state='PASS M-only source equivalence/exhaustive endpoint/fulltop-lint checkpoint; fullcore pending',
                source=bind(uce),baseline_bp='e10992a3eea3ba2ef6ae3ccb42ff5e8c658286a8',
                common_final_yumi_fsm_sha256=hashlib.sha256(fsm(old).encode()).hexdigest(),
                source_before_after_fsm_identical=True,compact_evidence=originals,actual_synthesis_diagnostic_excerpts=excerpts,
                scope='No Vivado/board/fit run here. Original r2 canceled by root; excerpts are diagnostic, not final resource/timing acceptance. Code fix preserves same-cycle pulse; no delay/waiver. Packing changes separate.')
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'manifest.json')


if __name__=='__main__':main()
