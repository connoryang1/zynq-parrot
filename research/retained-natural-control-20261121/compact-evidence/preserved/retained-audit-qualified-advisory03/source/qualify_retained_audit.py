#!/usr/bin/env python3
"""Read ONLY the closed accepted scaled-advisory trace to qualify the auditor."""
import argparse
import gzip
import json
import subprocess
import threading
import time
from prepare import ROOT,HERE,bind
from audit_retained_case import selections,consume


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args()
 prior=ROOT/'research/retained-system-geometry-20261121/scaled-advisory-trace-audit01/verification.json'
 proof=json.loads(prior.read_text())
 if not proof['accepted']:raise ValueError('closed qualification proof required')
 fst=ROOT/'research/retained-system-geometry-20261121/full-system1280-cold08-native0-01/retained1280-cold08-native0.fst'
 before=bind(fst);source=bind(HERE/'audit_retained_case.py')
 if before!=proof['provenance']['fst'] if 'provenance' in proof and 'fst' in proof['provenance'] else False:
  raise ValueError('qualification trace changed')
 out=HERE/a.output;out.mkdir(exist_ok=False)
 fields=selections();sel=out/'selection.tsv';sel.write_text(''.join(k+'\t'+v['path']+'\n' for k,v in fields.items()))
 reader=ROOT/'research/retained-system-geometry-20261121/reader/fst_events';cmd=[str(reader),str(fst),str(sel)]
 start=time.monotonic();error=None;result=None
 with gzip.open(out/'selected-events.tsv.gz','wt') as saved,(out/'reader.stderr').open('w') as stderr:
  proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=stderr,text=True);timer=threading.Timer(120,proc.kill);timer.daemon=True;timer.start()
  def lines():
   for line in proc.stdout:saved.write(line);yield line
  try:
   result=consume(lines(),fields,dict(whole_begin=0,whole_end=2**64,timed_begin=0,timed_end=2**64),15)
   if proc.wait()!=0:raise ValueError('reader failed/timed out')
   for lane in ('i','d'):
    counts=result['counts']['program'][lane]
    if (counts.get('insert_publication'),counts.get('lookup_hit'))!=(1,1):raise ValueError('closed known publication/hit not reproduced')
  except BaseException as e:error=repr(e);proc.kill();proc.wait()
  finally:timer.cancel()
 if before!=bind(fst) or source!=bind(HERE/'audit_retained_case.py'):raise ValueError('qualification input/source changed')
 record=dict(state='PASS-closed-model-qualification-only' if error is None else 'FAIL-qualification',error=error,
 scope='Closed accepted synthetic advisory trace only, not active natural cohort. All-time synthetic windows, no natural timing or useful-capacity inference.',
 closed_prior_proof=bind(prior),trace=before,source=source,qualification_source=bind(__file__),reader=bind(reader),selection=bind(sel),command=cmd,result=result,elapsed_seconds=time.monotonic()-start)
 (out/'analysis.json').write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps(record,indent=2))
 if error:raise ValueError(error)


if __name__=='__main__':main()
