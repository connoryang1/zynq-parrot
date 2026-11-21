#!/usr/bin/env python3
"""Postprocess the already-audited105signal stream; no cache-model changes."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import time
from hp0_closed_pair import bind,verify,NATURAL,HERE,ROOT

REQUIRED={'cache_clock','reset','global_cycle','data_v','data_yumi','data_opcode',
          'data_address','data_mask','critical','complete'}


def normal_records(lines,phases):
 references=[];misses=[];pending=None;target_index=whole_index=0
 for line in lines:
  e=json.loads(line)
  if e['event']=='reference':
   ref={k:e[k] for k in ('global_cycle','context','thread','address','line','operation','outcome','target','epoch','phase')}
   ref['ordinal']=len(references);ref['whole_index']=None;ref['target_index']=None
   if phases['whole_begin']<=e['global_cycle']<phases['whole_end']:ref['whole_index']=whole_index;whole_index+=1
   if e['target'] and e['epoch'] is not None and e['operation']=='load':ref['target_index']=target_index;target_index+=1
   references.append(ref)
   if e['outcome']=='miss':
    if pending is not None:raise ValueError('overlapping ordinary misses')
    pending=dict(reference=ref,beats=[])
  elif e['event']=='fill_beat':
   if pending is None or pending['reference']['line']!=e['line']:raise ValueError('unmatched normal fill')
   pending['beats'].append(dict(global_cycle=e['global_cycle'],line=e['line'],mask=e['mask']))
  elif e['event']=='fill_complete':
   if pending is None or pending['reference']['line']!=e['line'] or len(pending['beats'])!=8:raise ValueError('unmatched/incomplete normal full write')
   if pending['beats'][-1]['global_cycle']!=e['global_cycle'] or sum(b['mask'] for b in pending['beats'])!=255:raise ValueError('normal full-write chronology/masks differ')
   pending['full_write_cycle']=e['global_cycle'];pending['miss_index']=len(misses);misses.append(pending);pending=None
 if pending is not None:raise ValueError('ordinary miss undrained')
 return references,misses


def accepted_packets(lines,expected_paths,guard_cycle,timeout=600):
 mapping={};widths={};declared={};values={};changes={};stamp=None;ended=False;reset_seen=False
 first_edge=previous=None;period=offset=None;packets=[];groups=0;deadline=time.monotonic()+timeout
 def group():
  nonlocal first_edge,previous,period,offset,reset_seen,groups
  new=dict(values);new.update(changes)
  if values.get('cache_clock')==0 and new.get('cache_clock')==1:
   if values.get('reset')==1:
    if previous is not None:raise ValueError('reset after guarded data stream')
    reset_seen=True
   elif reset_seen and values.get('global_cycle') is not None and values['global_cycle']>=guard_cycle:
    cycle=values['global_cycle']
    if previous is not None:
     if cycle!=previous[0]+1:raise ValueError('global cycle did not increment per Dclock edge')
     delta=stamp-previous[1]
     if period is None:
      period=delta;offset=first_edge[1]-first_edge[0]*period
     if delta!=period or delta<=0 or stamp-cycle*period!=offset:raise ValueError('Dclock/global-cycle timebase changed')
    else:first_edge=(cycle,stamp)
    previous=(cycle,stamp)
    if values.get('data_v') and values.get('data_yumi') and values.get('data_opcode')==0:
     if any(values.get(k) is None for k in REQUIRED):raise ValueError('unknown accepted fill signal')
     packets.append(dict(global_cycle=cycle,tick=stamp,line=hex(values['data_address']&~63),mask=values['data_mask'],critical_receive_flag=bool(values['critical']),complete_receive_flag=bool(values['complete'])))
  values.update(changes);changes.clear();groups+=1
  if groups%2048==0 and time.monotonic()>deadline:raise TimeoutError('bounded postprocess deadline')
 for line in lines:
  p=line.rstrip('\n').split('\t')
  if p[0]=='#FST':continue
  if p[0]=='#SIGNAL':
   if stamp is not None or p[1] in declared or p[1] not in expected_paths or p[4]!=expected_paths[p[1]]:raise ValueError('wrong/duplicate/late saved declaration')
   declared[p[1]]=p[4]
   if p[1] in REQUIRED:mapping.setdefault(int(p[3]),[]).append(p[1]);widths[p[1]]=int(p[2])
  elif p[0]=='#END':
   if ended:raise ValueError('duplicate saved EOF')
   group();ended=True
  else:
   if ended or len(p)!=3 or declared!=expected_paths:raise ValueError('incomplete saved event stream')
   tick,handle=int(p[0]),int(p[1])
   if stamp is not None and tick<stamp:raise ValueError('saved time reversal')
   if stamp is not None and tick!=stamp:group()
   stamp=tick
   if handle in mapping:
    for key in mapping[handle]:
     if key in changes or len(p[2])!=widths[key] or set(p[2])-set('01xz'):raise ValueError('bad saved width/duplicate/encoding')
     changes[key]=None if set(p[2])&set('xz') else int(p[2],2)
 if not ended or period is None:raise ValueError('missing complete saved EOF/timebase')
 return packets,dict(period_FST_ticks=period,global_cycle_to_Dposedge_tick_offset=offset,first_guarded_edge=first_edge,last_guarded_edge=previous,groups=groups)


def match_packets(misses,packets):
 expected=[b for m in misses for b in m['beats']]
 projected=[{k:p[k] for k in ('global_cycle','line','mask')} for p in packets]
 if projected!=expected:raise ValueError('accepted-fill sequence differs from fully audited normal event stream')
 for n,miss in enumerate(misses):
  beats=packets[n*8:n*8+8];critical=[b for b in beats if b['critical_receive_flag']]
  if len(critical)!=1 or [b['complete_receive_flag'] for b in beats]!=[False]*7+[True]:raise ValueError('critical/full receive flags not bijective with one normal refill')
  miss['accepted_beats']=beats;start=miss['reference']['global_cycle']
  miss['first_write_cycle']=beats[0]['global_cycle'];miss['critical_receive_cycle']=critical[0]['global_cycle']
  miss['durations']=dict(miss_to_first_Dcache_write=beats[0]['global_cycle']-start,
                         miss_to_critical_receive_flag=critical[0]['global_cycle']-start,
                         miss_to_full_L1_write=beats[-1]['global_cycle']-start)
  if min(miss['durations'].values())<0:raise ValueError('fill precedes accepted miss')


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',type=int,choices=(0,15),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 comparison_path=NATURAL/'comparison-v3-01/comparison.json';comparison_binding=bind(comparison_path)
 if comparison_binding['sha256']!='ada9f5d99311e80d091abeeae35bb1a6ef92a66f3b0487900ee0694e941d1634':raise ValueError('wrong closed pair')
 comparison=json.loads(comparison_path.read_text());records=comparison['bindings'][str(a.mode)]
 verify(records['normal']);verify(records['events']);verify(records['guest'])
 normal=json.loads(Path(records['normal']['path']).read_text());proof=json.loads(Path(normal['normal_dcache_report']['path']).read_text());verify(normal['normal_dcache_report'])
 if normal['state']!='PASS-complete-normal-D-audit':raise ValueError('normal complete proof required')
 guest=json.loads(Path(records['guest']['path']).read_text());phases=guest['phases']
 raw=Path(normal['normal_dcache_report']['path']).with_name('selected-events.tsv.gz')
 archive=json.loads((NATURAL/'compact-evidence/manifest.json').read_text())
 selected=next(r for r in archive['external_raw_or_selected_artifacts'] if r['path']==str(raw));verify(selected)
 with gzip.open(records['events']['path'],'rt') as f:references,misses=normal_records(f,phases)
 with gzip.open(raw,'rt') as f:packets,clock=accepted_packets(f,proof['report']['signals'],references[0]['global_cycle'])
 match_packets(misses,packets)
 whole=[[r['context'],r['operation'],r['address'],r['epoch'],r['phase'],r['target']] for r in references if r['whole_index'] is not None]
 if len(whole)!=43926 or hashlib.sha256(json.dumps(whole,separators=(',',':')).encode()).hexdigest()!='0d4fa29c89b90804e3c38bc2305ba55a3b3b75ec0724f26605380c1479a8e99a':raise ValueError('whole cached-reference sequence differs')
 verify(selected);verify(records['events']);verify(comparison_binding)
 a.output.mkdir(parents=True,exist_ok=False)
 for name,data in (('references.jsonl.gz',references),('misses.jsonl.gz',misses)):
  with gzip.open(a.output/name,'wt') as f:
   for row in data:f.write(json.dumps(row,separators=(',',':'))+'\n')
 report=dict(state='PASS-closed-Dcache-service-intervals',mode=a.mode,comparison=comparison_binding,normal_proof=records['normal'],normal_events=records['events'],saved105_stream=selected,source=bind(__file__),clock=clock,
             references=bind(a.output/'references.jsonl.gz'),misses=bind(a.output/'misses.jsonl.gz'),reference_count=len(references),ordinary_misses=len(misses),matched_fill_beats=len(packets),
             WHOLE_identical_reference_count=len(whole),WHOLE_normalized_SHA256='0d4fa29c89b90804e3c38bc2305ba55a3b3b75ec0724f26605380c1479a8e99a',
             limits=['Postprocessing of already-audited complete streams, not a replacement cache validator.',
                     'critical_receive_flag and first accepted Dcache write are not requested-word delivery or architectural load readiness.',
                     'Intervals include lookup/queue/memory/transport/L1-service dependencies; unions are not exclusive critical-path stalls or a causal partition. No FPGA/Linux projection.'])
 (a.output/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(state=report['state'],mode=a.mode,references=len(references),misses=len(misses),fill_beats=len(packets),clock=clock),indent=2))


if __name__=='__main__':main()
