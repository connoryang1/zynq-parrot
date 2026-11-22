#!/usr/bin/env python3
"""Separate ROOT observation continuation. No launch, cancellation or signals."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import argparse,fcntl,gzip,hashlib,importlib.util,json,os,subprocess,time
from ownership_ledger import Ledger,need
HERE=Path(__file__).resolve().parent;RECOVERY=HERE.parent
OLD=Path('/home/coyang/zynq-parrot-linux-host-observer/research/borrow-fpga-cad-preparation-20261122')
sys.path.insert(0,str(OLD))
import monitor_local as old
JOB='20261122T062351Z-3daedee66';HISTORY=OLD/('run-'+JOB)
ADMISSION=Path('/home/coyang/fpga-artifacts/context-resume/native1792-borrow-trace0-cad-20261122/admission02.json')
ADMISSION_SHA='10bf45af53ec9a14813082d93f93c5682dbc5b1f3030f86cf594b1ea20870a96'
ASSESS_SHA='80c9b694eb9987295f636309f14de0916a9e212f53fb7167fd77eda0507e1e89'
WORKER=(1113832,94444185);CAP=16*1024**2

def bind(p):return old.bind(Path(p))
def save(p,v):old.write(p,v)
def allocation(p):return int(subprocess.check_output(['du','-s','-B1',str(p)],text=True).split()[0])
def sources():return [bind(HERE/n) for n in ('ownership_ledger.py','continuation.py','test_ledger.py','README.md')]
def seed():
 need(bind(ADMISSION)['sha256']==ADMISSION_SHA,'original source/resource admission unchanged')
 assessment=RECOVERY/'assessment01.json';need(bind(assessment)['sha256']==ASSESS_SHA,'ROOT readonly assessment anchor')
 a=json.loads(ADMISSION.read_text());old.check_bindings(a)
 identity=json.loads((HISTORY/'monitor-identity.json').read_text());worker=identity['worker'];need((worker['pid'],worker['startticks'])==WORKER,'historical exact worker')
 ledger=Ledger(worker);history=[]
 polls=sorted(HISTORY.glob('poll-*.json'));need(len(polls)==46 and polls[0].name=='poll-001.json' and polls[-1].name=='poll-046.json','all46 immutable original polls')
 for path in polls:
  b=bind(path);s=json.loads(path.read_text());need(s['job']==JOB,'same historic job');ledger.snapshot(s,b);history.append(b)
 return a,identity,ledger,history

def config(a):return dict(a['configuration'],job=JOB,resources=a['resources'],evidence_root=str(OLD))
def apply(s,ledger,evidence):
 proof=ledger.snapshot(s,evidence)
 s['foreign_vendor_tools_original']=s['foreign_vendor_tools'];s['foreign_vendor_tools']=proof['foreign_vendor_tools'];s['continuation_ownership']=proof
 used=allocation(RECOVERY);need(used<=CAP,'16MiB recovery family subcap including initial assessment/probe')
 s['resources']['evidence_allocated_bytes']+=used
 reasons=old.violations(s,config(json.loads(ADMISSION.read_text())))
 if proof['unknown_worker_group']:reasons.append(dict(kind='unproven_or_reused_worker_group_identity',processes=proof['unknown_worker_group']))
 return reasons

def append_ledger(path,ledger,previous):
 with path.open('a') as f:
  for event in ledger.events[previous:]:f.write(json.dumps(event,sort_keys=True)+'\n')
  f.flush();os.fsync(f.fileno())
 return len(ledger.events)

def prepare():
 need(not (HERE/'admission.json').exists(),'fresh continuation admission')
 a,identity,ledger,history=seed()
 data=dict(schema='borrow1792-known-descendant-monitor-continuation-v1',state='PREPARED ROOT review required; read-only monitoring only',original_admission=bind(ADMISSION),assessment=bind(RECOVERY/'assessment01.json'),original_monitor_identity=bind(HISTORY/'monitor-identity.json'),worker_identity=identity['worker'],history=history,original_resources=a['resources'],recovery_subcap_bytes=CAP,sources=sources(),seed_events=ledger.events,action='probe/observe only; no launch or signal implementation')
 save(HERE/'admission.json',data);print(json.dumps(bind(HERE/'admission.json')))

def validate(sha):
 p=HERE/'admission.json';need(bind(p)['sha256']==sha,'ROOT reviewed exact continuation admission');v=json.loads(p.read_text());need(v['sources']==sources(),'continuation source frozen')
 for row in [v['original_admission'],v['assessment'],v['original_monitor_identity']]+v['history']:need(bind(row['path'])==row,'all original proof/history inputs unchanged')
 a,identity,ledger,history=seed();need(v['seed_events']==ledger.events and v['history']==history and v['original_resources']==a['resources'] and v['recovery_subcap_bytes']==CAP,'validated ownership chain and unchanged limits')
 need(allocation(RECOVERY)<=CAP,'recovery family fixed subcap');return a,identity,ledger

def observe(sha,loop):
 a,identity,ledger=validate(sha);cfg=config(a)
 prior_probe=None
 if loop:
  probe=HERE/'probe01';record=json.loads((probe/'live-status.json').read_text())
  need(record['state']=='PASS read-only exact ownership/limits' and record['continuation']==bind(HERE/'admission.json'),'exact passed read-only probe required before observation')
  prior_probe=bind(probe/'live-status.json')
  pp=Path(record['poll']['path']);need(bind(pp)==record['poll'],'passed probe poll bytes unchanged')
  ledger.snapshot(json.loads(gzip.decompress(pp.read_bytes())),record['poll'])
  logged=[json.loads(line) for line in (probe/'ownership-ledger.jsonl').read_text().splitlines()]
  need(logged==ledger.events,'probe append-only chain exactly reconstructed')
 with (HERE/'continuation.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  out=HERE/('observe01' if loop else 'probe01');need(not out.exists(),'fresh one-shot observation output');out.mkdir()
  count=append_ledger(out/'ownership-ledger.jsonl',ledger,0);index=0
  while True:
   old.check_bindings(a);s,raw=old.poll(cfg);index+=1
   rawpath=out/f'poll-{index:03d}.json.gz';rawpath.write_bytes(gzip.compress(raw,mtime=0));evidence=bind(rawpath)
   reasons=apply(s,ledger,evidence);count=append_ledger(out/'ownership-ledger.jsonl',ledger,count)
   status=dict(state='PASS read-only exact ownership/limits' if not reasons else 'REFUSED read-only; ROOT intervention required, no signal sent',status=s['status'],worker_elapsed_seconds=s['worker_elapsed_seconds'],poll=evidence,feature_state=s['feature_state'],ownership=s['continuation_ownership'],resources=s['resources'],violations=reasons,original_admission=bind(ADMISSION),continuation=bind(HERE/'admission.json'),inherited_probe=prior_probe,signals_sent=0,vendor_or_launcher_calls=0)
   save(out/'live-status.json',status);print(json.dumps(status),flush=True)
   need(allocation(RECOVERY)<=CAP,'16MiB complete recovery subcap')
   if reasons:raise RuntimeError('original identity/resource/deadline/foreign guard failed; no signal sent')
   if s['status']!='RUNNING' and not s['worker'] and not s['global_vendor_tools']:
    if s['status']=='PASS':need(s['feature_state']=='PASS actual seven defines/three contexts/20MHz-8MHz/source','full original feature/source gate')
    save(out/'terminal-status.json',status);return
   if not loop:return
   time.sleep(90)

def main():
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--probe',action='store_true');g.add_argument('--observe',action='store_true');p.add_argument('--admission-sha256');a=p.parse_args()
 if a.prepare:prepare()
 else:need(a.admission_sha256 is not None,'exact continuation SHA required');observe(a.admission_sha256,a.observe)
if __name__=='__main__':main()
