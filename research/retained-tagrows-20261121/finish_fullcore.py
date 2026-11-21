#!/usr/bin/env python3
"""Audit the two closed synthetic traces and archive their exact proof; no run."""
import argparse
import json
from pathlib import Path
import subprocess
from run_fullcore import ROOT,READER,bind,write


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);args=parser.parse_args();run=args.run.resolve()
    m=json.loads((run/'session.json').read_text())
    if m['state']!='PASS clean1280+observe1 tagrow integrity/advisory execution; closed trace audits pending':
        raise ValueError('both complete checked model executions required first')
    log=run/'audit-commands.json'
    if log.exists():raise ValueError('fresh audit outputs required; preserve earlier failed attempts')
    commands=[]
    def call(label,argv):
        record=dict(label=label,argv=list(map(str,argv)));commands.append(record);write(log,commands)
        with (run/(label+'.log')).open('wb') as stream:
            result=subprocess.run(record['argv'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=900)
        record.update(returncode=result.returncode,log=bind(run/(label+'.log')));write(log,commands)
        if result.returncode:raise ValueError(label+' failed; preserved output, no acceptance')
    call('integrity-geometry',['python3','-B',Path(__file__).with_name('audit_geometry.py'),
        '--session',run/'integrity/verification.json','--reader',READER,'--output',run/'integrity-geometry01'])
    actual=json.loads((run/'advisory/process.json').read_text())['returncode']
    call('strict-advisory',['python3','-B',ROOT/'testing/rtl/retained-advisory-trace/validate.py',
        '--fst',run/'advisory/trace.fst','--reader',READER,'--model-source-list',run/'actual-source-list.json',
        '--fixture-manifest',ROOT/'research/retained-control-abi-20261121/advisory-fixture-cold08/manifest.json',
        '--log',run/'advisory/run.log','--exit-code',str(actual),'--out',run/'strict-advisory01'])
    call('counter-audit',['python3','-B',ROOT/'research/retained-use-observation-20261121/verify_counters.py',
        '--fst',run/'advisory/trace.fst','--reader',READER,'--strict-proof',run/'strict-advisory01/verification.json',
        '--run-proof',run/'advisory/verification.json','--out',run/'counter-audit01'])
    call('archive',['python3','-B',Path(__file__).with_name('close_fullcore.py'),'--run',run])
    print('PASS closed tagrow1280 integrity, I/D full-line restoration and actual observer 1/1/8; no FPGA/performance evidence')


if __name__=='__main__':main()
