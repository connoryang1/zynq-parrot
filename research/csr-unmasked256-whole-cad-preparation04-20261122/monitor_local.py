#!/usr/bin/env python3
"""Observe one ROOT-admitted local bp1 job; no launch or SSH exists here."""
from pathlib import Path
import argparse,fcntl,gzip,hashlib,json,os,re,subprocess,time
from ownership_ledger import Ledger
from budget import violations as budget_violations
from cad_checks import check_bindings
from contracts import ART,FAMILY_ART
HERE=Path(__file__).resolve().parent
LOCAL=['python3','-B','-']

def bind(p):
 raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def write(p,v):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2)+'\n');tmp.replace(p)
def poll(config):
 # repr generates a Python literal; it is sent on stdin, never interpolated in a shell.
 script=('CONFIG='+repr(config)+'\n').encode()+(HERE/'identity.py').read_bytes()+b'\n'+(HERE/'remote_probe.py').read_bytes()
 r=subprocess.run(LOCAL,input=script,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40)
 if r.returncode:raise RuntimeError('read-only local poll failed; no signal sent: '+r.stderr.decode(errors='replace')[-2048:])
 return json.loads(r.stdout),r.stdout

def violations(s,config):
 return list(s['identity_violations'])+([dict(kind='foreign_vendor_or_launcher',processes=s['foreign_vendor_tools'])] if s['foreign_vendor_tools'] else [])+budget_violations(s['resources'],s['worker_elapsed_seconds'],config['resources'])
def ownership(s,config,pid,startticks):
 w=s.get('worker');proof=s.get('proven_ownership',{});known={tuple(k) for k in proof.get('owned_current',[])}
 return bool(w and w['pid']==pid and w['startticks']==startticks and w['pgrp']==w['sid']==pid and ('worker '+config['job']+' '+config['top']) in w['argv'] and not proof.get('foreign_vendor_tools') and not proof.get('unknown_worker_group') and all((p['pid'],p['startticks']) in known for p in s['worker_group']+s['all_vivado']))

def ledger_poll(snapshot,ledger,evidence,ledger_path):
 before=len(ledger.events);proof=ledger.snapshot(snapshot,evidence)
 snapshot['foreign_vendor_tools_before_ledger']=snapshot['foreign_vendor_tools'];snapshot['foreign_vendor_tools']=proof['foreign_vendor_tools'];snapshot['proven_ownership']=proof
 if proof['unknown_worker_group']:snapshot['identity_violations'].append(dict(kind='unproved_current_worker_group',processes=proof['unknown_worker_group']))
 with ledger_path.open('a') as stream:
  for event in ledger.events[before:]:stream.write(json.dumps(event,sort_keys=True)+'\n')
  stream.flush();os.fsync(stream.fileno())
 return proof

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--admission',default=str(ART/'admission.DRAFT.json'));ap.add_argument('--admission-sha256',required=True);ap.add_argument('--job',required=True)
 mode=ap.add_mutually_exclusive_group(required=True);mode.add_argument('--preflight',action='store_true');mode.add_argument('--execute',action='store_true')
 ap.add_argument('--worker-pid',type=int);ap.add_argument('--worker-startticks',type=int)
 args=ap.parse_args();p=Path(args.admission).resolve()
 if bind(p)['sha256']!=args.admission_sha256:raise RuntimeError('admission hash mismatch')
 admission=json.loads(p.read_text());check_bindings(admission)
 if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-a44c03bb7',args.job):raise RuntimeError('unexpected job/revision identity')
 config=dict(admission['configuration'],job=args.job,resources=admission['resources'],evidence_root=str(FAMILY_ART),expected_worker_startticks=args.worker_startticks,expected_worker_pid=args.worker_pid)
 if args.preflight:
  s,_=poll(config);reasons=violations(s,config)
  if s['global_vendor_tools']:reasons.append(dict(kind='prelaunch_vendor_not_idle',processes=s['global_vendor_tools']))
  if s['resources']['work_root_exists']:reasons.append(dict(kind='prelaunch_work_root_not_fresh',path=config['work_root']))
  print(json.dumps(dict(state='PASS' if not reasons else 'REFUSED',resources=s['resources'],violations=reasons,mutations=0),indent=2))
  return 1 if reasons else 0
 if not args.worker_pid or not args.worker_startticks:raise RuntimeError('execute requires exact worker PID and startticks')
 # No build/vendor launch exists here. ROOT separately owns the pinned direct launcher and HOLD release.
 with (HERE/'monitor.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  baseline,raw=poll(config)
  worker=baseline.get('worker')
  if not worker or worker['pid']!=args.worker_pid or worker['startticks']!=args.worker_startticks:raise RuntimeError('exact initial worker identity unproven; no signal sent')
  tokens=worker.get('argv_tokens',[])
  if not tokens or tokens[0].rsplit('/',1)[-1]!='bash' or tokens[1:]!=[admission['direct_launch']['argv'][0],'worker',args.job,config['top']]:raise RuntimeError('exact maintained worker argv unproven; no signal sent')
  ledger=Ledger(worker)
  out=ART/('run-'+args.job);out.mkdir(exist_ok=False)
  first=out/'poll-001.json.gz';first.write_bytes(gzip.compress(raw,mtime=0))
  ledger_poll(baseline,ledger,bind(first),out/'ownership-ledger.jsonl')
  if not ownership(baseline,config,args.worker_pid,args.worker_startticks):raise RuntimeError('initial exact history-chain ownership unproven; no signal sent')
  index=1;prior=baseline;failures=0
  identity=dict(job=args.job,worker=baseline['worker'],admission=bind(p),bindings=admission['bindings'],poll_interval_seconds=90,configuration=config,mutations='Only maintained cancellation on admitted bounds/features after exact owner/startticks/history-chain recheck; no vendor/board launch')
  write(out/'monitor-identity.json',identity)
  while True:
   s=prior if index==1 else None
   if s is None:
    delay=max(0,90-(time.time()-prior['epoch']))
    if delay:time.sleep(delay)
    try:s,raw=poll(config);failures=0
    except Exception as e:
     failures+=1;print('MONITOR_OBSERVATION_FAILURE '+repr(e),flush=True)
     if failures>=3:raise
     time.sleep(90);continue
    if s['epoch']-prior['epoch']<60:raise RuntimeError('poll interval guard')
    poll_path=out/('poll-%03d.json.gz'%index);poll_path.write_bytes(gzip.compress(raw,mtime=0));ledger_poll(s,ledger,bind(poll_path),out/'ownership-ledger.jsonl')
   reasons=violations(s,config)
   record=dict(ownership=s.get('proven_ownership'),utc=s['utc'],status=s['status'],poll='poll-%03d.json.gz'%index,resources=s['resources'],worker_elapsed_seconds=s['worker_elapsed_seconds'],features=s['feature_state'],reports=[r['binding'] for r in s['reports']],feedback_warnings=s['feedback_warnings'],identity_violations=s['identity_violations'],bound_violations=reasons,latest_milestones=s['milestones'][-6:])
   old={p['pid']:p for p in prior['all_vivado']};record['CPU_advancement']=[]
   for proc in s['all_vivado']:
    q=old.get(proc['pid'])
    if q and q['startticks']==proc['startticks'] and '/unwrapped/' in proc['argv']:
     record['CPU_advancement'].append(dict(pid=proc['pid'],CPU_seconds=((proc['utime_ticks']+proc['stime_ticks'])-(q['utime_ticks']+q['stime_ticks']))/s['ticks_per_second']))
   write(out/'live-status.json',record)
   stage=lambda x:[(m['path'],m['line'],m['text']) for m in x['milestones'] if not any(w in m['text'] for w in ('WARNING','ERROR','posedge_clk','CONFIG','set ::env'))][-1:]
   changed=index==1 or s['status']!=prior['status'] or s['feature_state']!=prior['feature_state'] or [r['binding']['sha256'] for r in s['reports']]!=[r['binding']['sha256'] for r in prior['reports']] or bool(s['feedback_warnings'])!=bool(prior['feedback_warnings']) or bool(reasons)
   if changed or stage(s)!=stage(prior):print(json.dumps(record),flush=True)
   if s['status']!='RUNNING':
    check_bindings(admission)
    if s['status']!='PASS' or reasons:
     record.update(monitor_acceptance='FAIL terminal worker/status/identity/resource/ownership reasons',builder_release_proven=False)
     write(out/'terminal-status.json',record);print('MONITOR_TERMINAL FAIL',flush=True);return 1
    final,raw=poll(config);end=out/('final-poll-%03d.json.gz'%index);end.write_bytes(gzip.compress(raw,mtime=0));ledger_poll(final,ledger,bind(end),out/'ownership-ledger.jsonl')
    final_reasons=violations(final,config)
    if final['status']!='PASS' or final_reasons:
     write(out/'terminal-status.json',dict(record,monitor_acceptance='FAIL final source/resource/ownership/status',final_poll=bind(end),final_reasons=final_reasons,builder_release_proven=False));return 1
    if final['worker'] or final['global_vendor_tools'] or final['worker_group'] or final['all_vivado'] or final['proven_ownership']['owned_current']:
     write(out/'terminal-pending-disappearance.json',dict(record,final_poll=bind(end),builder_release_proven=False));prior=final;index+=1;continue
    if final['feature_state']!='PASS actual seven defines/three contexts/20MHz-8MHz/source':raise RuntimeError('terminal PASS lacks complete actual source/profile/clock acceptance')
    check_bindings(admission);write(out/'terminal-status.json',dict(record,monitor_acceptance='PASS zero violations/source/features and worker/vendor disappearance',final_poll=bind(end),final_reasons=[],builder_release_proven=True))
    print('MONITOR_TERMINAL PASS',flush=True);return 0
   if reasons:
    fresh,raw=poll(config);pre=out/'pre-cancel-identity.json.gz';pre.write_bytes(gzip.compress(raw,mtime=0));ledger_poll(fresh,ledger,bind(pre),out/'ownership-ledger.jsonl')
    if fresh['status']!='RUNNING':print('BOUND_TERMINAL_NO_CANCEL',flush=True);prior=s;index+=1;continue
    if not violations(fresh,config):print('BOUND_RECHECK_CLEARED_NO_CANCEL',flush=True);prior=s;index+=1;continue
    check_bindings(admission)
    if not ownership(fresh,config,args.worker_pid,args.worker_startticks):raise RuntimeError('exact ownership proof failed; no signal sent')
    argv=['bash',str(HERE/'cancel_local.sh'),args.job,config['log_root']]
    write(out/'cancellation-reason.json',dict(reasons=violations(fresh,config),worker=fresh['worker'],verified_all_vivado_history_chain=True,argv=argv))
    with (out/'maintained-cancel.log').open('wb') as log:r=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=50)
    print('MAINTAINED_CANCEL_EXIT '+str(r.returncode),flush=True)
    post,raw=poll(config);postpath=out/'post-cancel-status.json.gz';postpath.write_bytes(gzip.compress(raw,mtime=0))
    if post['global_vendor_tools'] or post['worker'] or post['status']!='CANCELLED':raise RuntimeError('terminal cancellation/process disappearance unproven')
    check_bindings(admission);write(out/'terminal-status.json',dict(status='CANCELLED',cause=violations(fresh,config),post_snapshot='post-cancel-status.json.gz'))
    print('MONITOR_TERMINAL CANCELLED_BOUND_OR_IDENTITY',flush=True);return 0
   prior=s;index+=1
if __name__=='__main__':raise SystemExit(main())
