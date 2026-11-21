#!/usr/bin/env python3
"""Run only the reviewed three-arm RAM synthesis fixture, never a board program."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
HOST='coyang@haight.chillysky.com'
REMOTE='/tmp/linux-retained-ram-inference-20261121-01'
WRAPPER='/home/coyang/zynq-parrot/codex-skills/bp-fpga-synthesis/scripts/run_vivado_2024_2.sh'

def bind(p):
    p=Path(p);raw=p.read_bytes()
    return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    files=['retained_probe.sv','probe.tcl','run_probe.py']
    if not args.execute:
        print(json.dumps(dict(state='PREPARED no Vivado or board action',inputs=[bind(HERE/n) for n in files]),indent=2));return
    out=HERE/'run01';out.mkdir()
    state=dict(state='STARTED isolated RAM synthesis only',started_utc=datetime.now(timezone.utc).isoformat(),
               inputs=[bind(HERE/n) for n in files],remote=REMOTE,physical_operations=0,commands=[])
    def save():(out/'session.json').write_text(json.dumps(state,indent=2)+'\n')
    def run(name,argv,seconds=30,required=True):
        row=dict(name=name,argv=argv,timeout_seconds=seconds);state['commands'].append(row);save()
        with (out/(name+'.log')).open('wb') as log:
            r=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=seconds)
        row.update(returncode=r.returncode,log=bind(out/(name+'.log')));save()
        if required and r.returncode:raise RuntimeError(name+' failed; evidence retained')
        return r.returncode
    ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-p','30041',HOST]
    try:
        run('admission',ssh+['test -x '+shlex.quote(WRAPPER)+' && ! pgrep -x vivado && test ! -e '+shlex.quote(REMOTE)+' && mkdir '+shlex.quote(REMOTE)])
        run('upload',['scp','-q','-P','30041',str(HERE/'retained_probe.sv'),str(HERE/'probe.tcl'),HOST+':'+REMOTE+'/'])
        # A remote timeout terminates the full process group before the SSH bound.
        cmd='cd '+shlex.quote(REMOTE)+' && timeout --kill-after=15s 580s '+shlex.quote(WRAPPER)+' -mode batch -source probe.tcl -log vivado.log -journal vivado.jou'
        rc=run('synthesis',ssh+[cmd],620,False)
        run('collect',['scp','-q','-r','-P','30041',HOST+':'+REMOTE,str(out/'remote')],40,False)
        run('no-orphans',ssh+['! pgrep -x vivado'],20)
        if rc:raise RuntimeError('RAM probe synthesis failed; collected partial evidence')
        primitive_counts={}
        for label in ('native','area','banked'):
            folder=out/'remote';rows=(folder/(label+'-primitives.tsv')).read_text().splitlines()
            if rows[0]!='cell\tprimitive\tram_mode\tread_a\twrite_a\tread_b\twrite_b':raise ValueError('primitive schema')
            counts={}
            for row in rows[1:]:
                cell,primitive,mode,ra,wa,rb,wb=row.split('\t')
                if primitive not in ('RAMB36E1','RAMB18E1') or mode!='TDP':raise ValueError('unexpected primitive/mode')
                side='payload' if cell.startswith('payload/') else 'tags' if cell.startswith('tags/') else None
                if side is None:raise ValueError('unexpected RAM owner')
                key=side+'/'+primitive;counts[key]=counts.get(key,0)+1
            if not counts:raise ValueError('empty RAM inference')
            for suffix in ('-utilization.rpt','.dcp'):
                if not (folder/(label+suffix)).is_file():raise ValueError('missing actual synth result')
            primitive_counts[label]=counts
        state.update(state='PASS three RAM inference arms; no correctness/route/fit claim',primitive_counts=primitive_counts)
    except BaseException as e:
        state.update(state='FAIL preserved RAM inference only',error=repr(e));raise
    finally:
        state['closed_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps(state['primitive_counts'],indent=2))

if __name__=='__main__':main()
