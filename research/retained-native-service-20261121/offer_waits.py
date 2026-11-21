#!/usr/bin/env python3
"""Actual lookup/cache-request offer waits and sampled gating conditions.
Waiting conditions are observations, not mutually exclusive causal stall costs.
"""
import argparse
import bisect
import collections
import gzip
import json
from pathlib import Path
import sys
import time
from hp0_closed_pair import HERE,NATURAL,ROOT,bind,verify
sys.path.insert(0,str(NATURAL))
from audit_retained_case import selections as retained_fields


def edges(lines,paths,keep,clocks,timeout=600):
 mapping={};widths={};declared={};values={};changes={};stamp=None;ended=False;groups=0;deadline=time.monotonic()+timeout
 def bit(value,index):return None if value is None else (value if index is None else (value>>index)&1)
 def group():
  nonlocal groups
  new=dict(values);new.update(changes)
  for label,key,index in clocks:
   if bit(values.get(key),index)==0 and bit(new.get(key),index)==1:yield stamp,label,dict(values)
  values.update(changes);changes.clear();groups+=1
  if groups%2048==0 and time.monotonic()>deadline:raise TimeoutError('bounded saved-stream offer audit')
 for line in lines:
  p=line.rstrip('\n').split('\t')
  if p[0]=='#FST':continue
  if p[0]=='#SIGNAL':
   if stamp is not None or p[1] in declared or p[1] not in paths or p[4]!=paths[p[1]]:raise ValueError('wrong saved declaration')
   declared[p[1]]=p[4]
   if p[1] in keep:mapping.setdefault(int(p[3]),[]).append(p[1]);widths[p[1]]=int(p[2])
  elif p[0]=='#END':
   if ended:raise ValueError('duplicate saved EOF')
   yield from group();ended=True
  else:
   if ended or len(p)!=3 or declared!=paths:raise ValueError('incomplete saved stream')
   tick,handle=int(p[0]),int(p[1])
   if stamp is not None and tick<stamp:raise ValueError('time reversal')
   if stamp is not None and tick!=stamp:yield from group()
   stamp=tick
   for key in mapping.get(handle,[]):
    if key in changes or len(p[2])!=widths[key] or set(p[2])-set('01xz'):raise ValueError('bad saved field encoding')
    changes[key]=None if set(p[2])&set('xz') else int(p[2],2)
 if not ended:raise ValueError('missing complete saved EOF')


class Offers:
 def __init__(self):self.pending=None;self.accepted=[];self.unaccepted=[];self.blocked=[]
 def step(self,tick,cycle,edge,valid,accept,key,flags):
  if self.pending is not None and (not valid or key!=self.pending['key']):
   self.pending.update(end_tick=tick,termination='withdrawn' if not valid else 'superseded_before_accept');self.unaccepted.append(self.pending);self.pending=None
  if not valid:return
  if self.pending is None:self.pending=dict(key=key,offer_tick=tick,offer_cycle=cycle,offer_edge=edge,blocked_cycles=0)
  if accept:
   row=dict(self.pending,accept_tick=tick,accept_cycle=cycle,accept_edge=edge,offer_to_accept_lane_cycles=edge-self.pending['offer_edge'])
   if row['offer_to_accept_lane_cycles']!=row['blocked_cycles']:raise ValueError('offer wait differs from observed unaccepted valid cycles')
   self.accepted.append(row);self.pending=None
  else:
   self.pending['blocked_cycles']+=1;self.blocked.append(dict(tick=tick,cycle=cycle,edge=edge,key=key,**flags))
 def finish(self):
  if self.pending is not None:self.pending['termination']='unaccepted_at_closed_EOF';self.unaccepted.append(self.pending);self.pending=None


def selection_paths(path):
 return dict(line.rstrip('\n').split('\t') for line in Path(path).read_text().splitlines())


def backend_analysis(lines,phases):
 fields=retained_fields();paths={k:v['path'] for k,v in fields.items()}
 keep={'store_clk_i','store_reset_i','store_clear_i','store_epoch_wrap_o','store_lookup_v_i','store_lookup_ready_o','store_resp_v_o','store_busy_o','global_cycle','store_state_0','store_state_1','store_lookup_addr_i_0','store_lookup_addr_i_1'}
 trackers=[Offers(),Offers()];edge=[0,0];seen=[False,False];origins=['reset','reset'];runs=[[],[]];episodes=[[],[]];active=[None,None]
 for tick,lane,s in edges(lines,paths,keep,[('i','store_clk_i',0),('d','store_clk_i',1)]):
  n=('i','d').index(lane);edge[n]+=1;b=lambda k:(s['store_'+k]>>n)&1
  if b('reset_i'):
   seen[n]=True;origins[n]='reset'
   if active[n] is not None:active[n]['termination']='restarted_by_actual_reset';episodes[n].append(active[n]);active[n]=None
   if trackers[n].pending is not None:raise ValueError('reset revoked a live lookup offer')
   continue
  if not seen[n]:continue
  state=s[f'store_state_{n}'];cycle=s['global_cycle'];clear=b('clear_i');wrap=b('epoch_wrap_o');ready=b('lookup_ready_o')
  if state not in range(10):raise ValueError('not the frozen06df backend FSM')
  if clear or wrap:
   origin='explicit_clear' if clear else 'observed_epoch_wrap_pulse'
   if active[n] is None:active[n]=dict(origin=origin,request_tick=tick,request_cycle=cycle,request_edge=edge[n],clear_state_samples=0)
   origins[n]=origin
  if state==0:
   if active[n] is None:active[n]=dict(origin=origins[n],request_tick=tick,request_cycle=cycle,request_edge=edge[n],clear_state_samples=0,request_not_observed=True)
   active[n]['clear_state_samples']+=1
  if active[n] is not None and ready:
   active[n].update(ready_tick=tick,ready_cycle=cycle,request_to_lookup_ready_lane_cycles=edge[n]-active[n]['request_edge'])
   episodes[n].append(active[n]);active[n]=None
  reason='clear_or_sweep' if clear or state==0 else 'backend_insert' if state in (6,7,8,9) else 'held_response' if b('resp_v_o') else 'backend_lookup' if state in (2,3,4,5) else 'other_ready_gating'
  signature=(state,clear,wrap,b('resp_v_o'),b('busy_o'),origins[n] if state==0 or clear else 'none')
  if not runs[n] or runs[n][-1][2]!=signature:runs[n].append([tick,tick+50000,signature])
  else:runs[n][-1][1]=tick+50000
  trackers[n].step(tick,cycle,edge[n],b('lookup_v_i'),b('lookup_v_i') and ready,(s[f'store_lookup_addr_i_{n}'],),dict(reason=reason,backend_state=state,clear_pin=clear,wrap_pulse=wrap,clear_origin=signature[-1]))
 for tracker in trackers:tracker.finish()
 return trackers,runs,episodes


def run_at(runs,starts,tick):
 n=bisect.bisect_right(starts,tick)-1
 if n<0 or not runs[n][0]<=tick<runs[n][1] or (tick-runs[n][0])%50000:raise ValueError('UCE/backend lane edge provenance mismatch')
 return runs[n][2]


def summarize(tracker,bounds):
 accepted=[r for r in tracker.accepted if bounds[0]<=r['accept_cycle']<bounds[1]];blocked=[r for r in tracker.blocked if bounds[0]<=r['cycle']<bounds[1]]
 return dict(accepted=len(accepted),accepted_offer_to_accept_histogram=dict(sorted(collections.Counter(r['offer_to_accept_lane_cycles'] for r in accepted).items())),blocked_valid_sample_cycles=len(blocked),
             blocked_conditions={key:dict(collections.Counter(str(r.get(key)) for r in blocked)) for key in ('reason','backend_state','clear_pin','wrap_pulse','clear_origin','UCE_insert_owned','UCE_state')},
             unaccepted_offers=len([r for r in tracker.unaccepted if bounds[0]<=r['offer_cycle']<bounds[1]]))


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',type=int,choices=(0,15),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 comparison_path=NATURAL/'comparison-v3-01/comparison.json';comparison=json.loads(comparison_path.read_text());comparison_binding=bind(comparison_path)
 code_before=bind(__file__)
 state_sources={}
 for name,relative,expected_sha in (
  ('backend','bp_common/src/v/bp_retained_line_store.sv','06dfafa133e612f214ea3cb5c5755505602984ed47ff6dac1a1af06afc4d7a4e'),
  ('UCE','bp_me/src/v/cce/bp_uce.sv','f7fc772129f9560bc25287ad780b352fa909219ee08f686a9bb4f5ab0fe1bbc9')):
  source=ROOT/'import/black-parrot'/relative;record=bind(source)
  if record['sha256']!=expected_sha:raise ValueError('frozen FSM source changed')
  target=HERE/'source'/source.name;target.parent.mkdir(exist_ok=True)
  if target.exists() and target.read_bytes()!=source.read_bytes():raise ValueError('preserve exact old FSM snapshot')
  if not target.exists():target.write_bytes(source.read_bytes())
  state_sources[name]=dict(compiled=record,snapshot=bind(target))
 rb=comparison['bindings'][str(a.mode)]['retained'];verify(rb);retained=json.loads(Path(rb['path']).read_text())
 guest=json.loads(Path(comparison['bindings'][str(a.mode)]['guest']['path']).read_text());phases=guest['phases']
 saved=Path(rb['path']).with_name('selected-events.tsv.gz');archive=json.loads((NATURAL/'compact-evidence/manifest.json').read_text());saved_binding=next(b for b in archive['external_raw_or_selected_artifacts'] if b['path']==str(saved));verify(saved_binding)
 with gzip.open(saved,'rt') as f:lookup,runs,episodes=backend_analysis(f,phases)
 hp=HERE/f'mode{a.mode}-hp0/analysis.json';h=json.loads(hp.read_text())
 if h['state']!='PASS-closed-native-HP0-audit':raise ValueError('complete HP0/UCE proof required')
 verify(h['selected_events']);paths=selection_paths(h['selection']['path'])
 keep={'be.global'}
 for lane in ('i','d'):
  keep|={lane+'.'+k for k in ('clk','reset','reqv','reqy','reqtype','reqaddr','owned','state')}
 waiting_points={(r['tick'],lane):r for n,lane in enumerate(('i','d')) for r in lookup[n].blocked};sampled=set();req=[Offers(),Offers()];edge=[0,0];reset_seen=[False,False];starts=[[r[0] for r in rows] for rows in runs]
 with gzip.open(h['selected_events']['path'],'rt') as f:
  for tick,lane,s in edges(f,paths,keep,[('i','i.clk',None),('d','d.clk',None)]):
   n=('i','d').index(lane);edge[n]+=1;g=lambda k:s[lane+'.'+k]
   if g('reset'):reset_seen[n]=True;continue
   if not reset_seen[n]:continue
   if (tick,lane) in waiting_points:
    waiting_points[tick,lane].update(UCE_insert_owned=g('owned'),UCE_state=g('state'));sampled.add((tick,lane))
   valid=g('reqv') and g('reqtype') in (0,1)
   if valid:
    state,clear,wrap,resp,busy,origin=run_at(runs[n],starts[n],tick)
    flags=dict(reason='observed_cache_request_backpressure',backend_state=state,clear_pin=clear,wrap_pulse=wrap,clear_origin=origin,UCE_insert_owned=g('owned'),UCE_state=g('state'))
   else:flags={}
   req[n].step(tick,s['be.global'],edge[n],valid,valid and g('reqy'),(g('reqaddr'),g('reqtype')),flags)
 if sampled!=set(waiting_points):raise ValueError('lookup-wait raw UCE ownership not observed')
 for tracker in req:tracker.finish()
 for n,lane in enumerate(('i','d')):
  if len(req[n].accepted)!=h['report']['UCE_endpoints'][lane]['completed_requests']:raise ValueError('ordinary request offer accepts differ from audited UCE completion ownership')
 results={};whole=(phases['whole_begin'],phases['whole_end']);timed=(phases['timed_begin'],phases['timed_end'])
 for window,bounds in (('program',(-1,2**64)),('whole',whole),('timed_ring',timed)):
  results[window]={}
  for n,lane in enumerate(('i','d')):
   ls=summarize(lookup[n],bounds);rs=summarize(req[n],bounds);expected=retained['report']['counts'][window][lane]
   if ls['accepted']!=expected.get('lookup_accept',0) or ls['blocked_valid_sample_cycles']!=expected.get('lookup_blocked_cycles',0):raise ValueError('lookup offers differ from completed retained audit')
   results[window][lane]=dict(lookup=ls,ordinary_cached_request=rs,clear_episodes=[e for e in episodes[n] if bounds[0]<=e['request_cycle']<bounds[1]])
 verify(saved_binding);verify(h['selected_events']);verify(comparison_binding);verify(code_before)
 a.output.mkdir(parents=True,exist_ok=False)
 for kind,trackers in (('lookup',lookup),('ordinary-request',req)):
  for n,lane in enumerate(('i','d')):
   for status,records in (('accepted',trackers[n].accepted),('blocked',trackers[n].blocked),('unaccepted',trackers[n].unaccepted)):
    with gzip.open(a.output/f'{lane}-{kind}-{status}.jsonl.gz','wt') as f:
     for record in records:f.write(json.dumps(record,separators=(',',':'))+'\n')
 report=dict(state='PASS-actual-offer-wait-and-gating-audit',mode=a.mode,comparison=comparison_binding,source=code_before,FSM_sources=state_sources,retained_proof=rb,retained_saved_stream=saved_binding,HP0_proof=bind(hp),UCE_saved_stream=h['selected_events'],results=results,
             limits=['Offer waiting is measured separately from accepted→consumed service. Canceled/superseded/unaccepted offers remain explicit.',
                     'Raw UCE insert ownership and backend/clear/wrap conditions are simultaneous observations, not mutually exclusive causal stalls.',
                     'Explicit-clear request→lookup-ready and observed-wrap-pulse→ready use different start signals. State-clear sample count is separate.',
                     'No target execution, source/model change, performance partition or FPGA projection.'])
 (a.output/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(state=report['state'],mode=a.mode,whole=results['whole'],timed_ring=results['timed_ring']),indent=2))


if __name__=='__main__':main()
