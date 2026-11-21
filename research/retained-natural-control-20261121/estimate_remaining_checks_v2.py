#!/usr/bin/env python3
"""Read saved partial retirement selection; infer bounded loop position from ELF.
Not register-state verification, performance acceptance, or target execution.
"""
import collections,gzip,json
from pathlib import Path
from prepare import bind,HERE


def main():
 source=HERE/'failed-progress-v2-01/selected-events.tsv.gz';out=HERE/'remaining-check-estimate-v2.json'
 mapping={};values={};changes={};stamp=None;started=False;whole=None;timed=None;actor=None;epoch=None;query=None;tail=[];points=[];counts=collections.Counter();first_actor_start=None;last_cycle=None
 def v(k):
  bits=values.get(k,'x');return None if any(c in bits.lower() for c in 'xz') else int(bits,2)
 def group():
  nonlocal started,whole,timed,actor,epoch,query,first_actor_start,last_cycle
  new=dict(values);new.update(changes)
  if values.get('be_clock')=='0' and new.get('be_clock')=='1' and v('be_reset')==0 and v('instret'):
   pc=v('pc');c=v('global_cycle');last_cycle=c
   if pc==0x80000236:whole=c
   if pc==0x8000044a:started=True;timed=c
   if started:
    counts[hex(pc)]+=1
    if pc==0x8000049a:actor=0
    elif pc==0x80000624:actor+=1
    elif pc==0x8000051e:epoch=0
    elif pc==0x80000522:query=0
    elif pc==0x8000057c:query+=1
    elif pc==0x80000582:epoch+=1
    if pc==0x800004a0:points.append(dict(event='actor-check-start',actor=actor,cycle=c))
    if pc==0x80000624:points.append(dict(event='actor-check-completed',actor=actor-1,cycle=c))
    tail.append(dict(cycle=c,pc=hex(pc),actor=actor,epoch=epoch,query=query));del tail[:-12]
  values.update(changes);changes.clear()
 with gzip.open(source,'rt') as f:
  for line in f:
   p=line.rstrip('\n').split('\t')
   if p[0]=='#SIGNAL':mapping.setdefault(int(p[3]),[]).append(p[1])
   elif p[0]=='#END':group()
   elif p[0].isdigit():
    t=int(p[0])
    if stamp is not None and t!=stamp:group()
    stamp=t
    for key in mapping[int(p[1])]:changes[key]=p[2]
 if changes:group()
 remaining=((3-actor)*16*64+(15-epoch)*64+(64-query)) if actor is not None and epoch is not None and query is not None else None
 result=dict(scope='Unfinalized recovered prefix; source/disassembly loop-position estimate only, not completed checks/register proof/performance.',input=bind(source),source=bind(__file__),whole_begin_retire_cycle=whole,timed_end_retire_cycle=timed,last_visible_retire_cycle=last_cycle,inferred_actor=actor,inferred_epoch=epoch,inferred_query=query,
             checksum_queries_remaining_including_inflight=remaining,total_checksum_queries=4096,loop_control_retired_counts={k:counts[hex(k)] for k in (0x8000049a,0x80000624,0x8000051e,0x80000522,0x8000057c,0x80000582)},actor_progress=points,last_retired=tail,
             bounds='At most4*16*64=4096 expected-query checks; at most4*16=64 chronology rows,4free calls,4zero checks,onecontrol0 write and<=65536 finalpoll iterations remain after timed ring. Valid path finite; memory/IO service and faults have no source-only cycle bound. Logging/native feasibility estimates must remain conditional.')
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('whole_begin_retire_cycle','timed_end_retire_cycle','last_visible_retire_cycle','inferred_actor','inferred_epoch','inferred_query','checksum_queries_remaining_including_inflight','actor_progress')},indent=2))

if __name__=='__main__':main()
