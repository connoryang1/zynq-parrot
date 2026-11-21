#!/usr/bin/env python3
"""Bounded read-only progress recovery from the capped, UNFINALIZED mode0 FST.
Never accepts performance/access coverage or starts a model.
"""
import collections
import gzip
import json
from pathlib import Path
import subprocess
import threading
import time
from prepare import bind,ROOT,HERE


def main():
 out=HERE/'failed-progress01';out.mkdir(exist_ok=False)
 cohort=HERE/'cohort01/cohort.json';m=json.loads(cohort.read_text());run=m['runs'][0]
 if m['state']!='STOPPED-failure-preserved-no-retry' or len(m['runs'])!=1 or run['returncode']!=-25:raise ValueError('not exact capped mode0 failure')
 fst=run['trace'];before=bind(fst['path'])
 if before!=fst or before['bytes']!=200*1024*1024:raise ValueError('failed FST changed')
 prep=json.loads((HERE/'prepared01/manifest.json').read_text());symbols=prep['symbols'];labels={v['address']:k for k,v in symbols.items() if k.startswith('retained_resume_')}
 spec=json.loads((HERE/'retention-selection.json').read_text());keys=['be_clock','be_reset','global_cycle','retire_slot','context0','context1','instret','pc']
 selection=out/'selection.tsv';selection.write_text(''.join(k+'\t'+spec['fields'][k]['path']+'\n' for k in keys))
 reader=ROOT/'research/retained-system-geometry-20261121/reader/fst_events';cmd=[str(reader),fst['path'],str(selection.resolve())]
 record=dict(state='PARTIAL-UNFINALIZED-progress-diagnostic-only',trace=before,cohort=bind(cohort),elf=prep['elf'],source=bind(__file__),reader=bind(reader),selection=bind(selection),command=cmd,bound_seconds=120,
 limitations=['SIGXFSZ interrupted the writer at200MiB; finalized trace/last actual target cycle/complete coverage are NOT established.','Only available selected retirement events are examined. Counts are observations in the recoverable prefix, never accepted request/whole/ring metrics.','Clean reader EOF would describe only recoverable container data, not completion of the interrupted program.','No hardware-stall, capacity or performance conclusion.'])
 mapping={};values={};changes={};stamp=None;seen_reset=False;reset_active=False;first_cycle=None;last_cycle=None;retired=0;stage='before-main';first_ret=None
 counts={str(a):dict(begin=0,end=0) for a in range(4)};hits=collections.Counter();tail=collections.deque(maxlen=24);per_actor={str(a):collections.deque(maxlen=6) for a in range(4)};points=[];last_point=-10000;groups=0;err=None;metadata=None
 stages={'retained_resume_whole_begin':'capability/control','retained_resume_control_begin':'initial-control/poll-or-allocation/seed','retained_resume_warm_begin':'warm-ring','retained_resume_timed_begin':'timed-ring','retained_resume_timed_end':'independent-checks','retained_resume_checks_done':'geometry/free/check','retained_resume_teardown_begin':'control-off/poll','retained_resume_whole_end':'post-WHOLE-printing'}
 def val(name):
  raw=values.get(name,'x')
  if any(c in raw.lower() for c in 'xz'):raise ValueError('qualified unknown: '+name)
  return int(raw,2)
 def group():
  nonlocal seen_reset,reset_active,first_cycle,last_cycle,retired,stage,last_point,groups,first_ret
  if stamp is None:return
  new=dict(values);new.update(changes)
  if 'be_clock' in values and values['be_clock']=='0' and new.get('be_clock')=='1':
   if val('be_reset'):
    seen_reset=True;reset_active=True
   elif seen_reset:
    cycle=val('global_cycle')
    if first_cycle is None:first_cycle=cycle
    if last_cycle is not None and cycle<last_cycle:raise ValueError('cycle reversal without accepted reset')
    last_cycle=cycle;reset_active=False
    if val('instret'):
     pc=val('pc');slot=val('retire_slot');actor=val('context'+str(slot))
     if actor not in range(4):raise ValueError('invalid retired logical context')
     retired+=1;label=labels.get(pc)
     if label:
      hits[label]+=1
      if label in stages:stage=stages[label]
      if label=='retained_resume_request_begin':counts[str(actor)]['begin']+=1
      if label=='retained_resume_request_end':counts[str(actor)]['end']+=1
     event=dict(tick=stamp,cycle=cycle,pc=hex(pc),slot=slot,actor=actor,stage=stage)
     tail.append(event);per_actor[str(actor)].append(event)
     if first_ret is None:first_ret=event
     if cycle-last_point>=10000:
      points.append(dict(event,counts=json.loads(json.dumps(counts))));last_point=cycle
  values.update(changes);changes.clear();groups+=1
 start=time.monotonic()
 with (out/'reader.stderr').open('w') as error,gzip.open(out/'selected-events.tsv.gz','wt') as saved:
  proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=error,text=True);timer=threading.Timer(120,proc.kill);timer.daemon=True;timer.start();end=False
  try:
   for line in proc.stdout:
    saved.write(line);f=line.rstrip('\n').split('\t')
    if f[0]=='#FST':metadata=f[1:]
    elif f[0]=='#SIGNAL':mapping.setdefault(int(f[3]),[]).append(f[1])
    elif f[0]=='#END':group();end=True
    elif f[0].isdigit():
     t=int(f[0])
     if stamp is not None and t!=stamp:group()
     stamp=t
     for key in mapping[int(f[1])]:changes[key]=f[2]
   if changes:group()
  except BaseException as e:err=repr(e);proc.kill()
  finally:rc=proc.wait();timer.cancel()
 record.update(reader_returncode=rc,reader_end_marker=end,reader_error=err,elapsed_seconds=time.monotonic()-start,declared_fst_metadata=metadata,seen_actual_reset=seen_reset,
               first_visible_postreset_cycle=first_cycle,last_visible_cycle=last_cycle,first_retired=first_ret,visible_retired=retired,stage_last_visible=stage,label_occurrences=dict(hits),request_counts=counts,last_retired=list(tail),per_actor_tail={k:list(v) for k,v in per_actor.items()},progress_samples=points,selected_timestamp_groups=groups,
               selected_events=bind(out/'selected-events.tsv.gz'),stderr=bind(out/'reader.stderr'),trace_unchanged_after=bind(fst['path'])==before)
 functions=[]
 for e in record['last_retired']:
  pc=int(e['pc'],16);candidates=[(n,s) for n,s in symbols.items() if s['type'] in ('T','t') and s['size'] and s['address']<=pc<s['address']+s['size']]
  e['function']=min(candidates,key=lambda x:x[1]['size'])[0] if candidates else None
 (out/'progress.json').write_text(json.dumps(record,indent=2)+'\n')
 print('PARTIAL diagnostic:',rc,'end',end,'cycles',first_cycle,last_cycle,'stage',stage,'counts',counts,'last',list(tail)[-1:] if tail else [])

if __name__=='__main__':main()
