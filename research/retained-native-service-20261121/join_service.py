#!/usr/bin/env python3
"""Join exact same cached work to actual D service and HP0 burst ownership."""
import argparse
import bisect
import collections
import gzip
import json
from pathlib import Path
from hp0_closed_pair import HERE,NATURAL,bind,verify


def read_jsonl(path):
 with gzip.open(path,'rt') as f:return [json.loads(line) for line in f]


def distribution(values):
 counts=collections.Counter(values);n=sum(counts.values());seen=0;median=None
 for value,count in sorted(counts.items()):
  seen+=count
  if median is None and seen>(n-1)//2:median=value
 return dict(count=n,minimum=min(counts) if counts else None,lower_median=median,
             maximum=max(counts) if counts else None,histogram=dict(sorted(counts.items())))


def read_line(request):
 if request['len']!=7 or request['size']!=3:raise ValueError('matched request is not eight64bit beats')
 pa=request['BP_PA']
 if request['burst']==1 and pa&63:raise ValueError('INCR64B request crosses a physical line')
 if request['burst'] not in (1,2) or pa&7:raise ValueError('unsupported matched line burst')
 return pa&~63


def matching_reads(miss,reads_by_line,clock):
 line=int(miss['reference']['line'],16);period=clock['period_FST_ticks'];offset=clock['global_cycle_to_Dposedge_tick_offset']
 begin=miss['reference']['global_cycle']*period+offset;end=miss['accepted_beats'][-1]['tick']
 found=[r for r in reads_by_line.get(line,[]) if begin<=r['request_time']<=end]
 if len(found)>1:raise ValueError('ambiguous same-line HP0 reads in one owned D miss interval')
 if found and found[0]['beats'][-1]['time']>end:raise ValueError('matching HP0 read not complete before full L1 write')
 return found


def union_length(intervals,bounds):
 clipped=sorted((max(a,bounds[0]),min(b,bounds[1])) for a,b in intervals if max(a,bounds[0])<min(b,bounds[1]))
 total=0;end=None
 for a,b in clipped:
  if end is None or a>=end:total+=b-a;end=b
  elif b>end:total+=b-end;end=b
 return total


def load_case(mode):
 dp=HERE/f'mode{mode}-dcache/analysis.json';hp=HERE/f'mode{mode}-hp0/analysis.json';tp=HERE/f'mode{mode}-time-index/analysis.json'
 d=json.loads(dp.read_text());h=json.loads(hp.read_text());t=json.loads(tp.read_text())
 if d['state']!='PASS-closed-Dcache-service-intervals' or h['state']!='PASS-closed-native-HP0-audit' or t['state']!='PASS-HP0-actual-time-core-counter-index':raise ValueError('all closed service proofs required')
 for b in (d['references'],d['misses'],h['transactions'],t['index']):verify(b)
 if t['HP0_proof']!=bind(hp):raise ValueError('time index/HP0 proof mismatch')
 if t['advisory_admissions']:raise ValueError('capacity-only classification contaminated by actual advisory admissions')
 refs=read_jsonl(d['references']['path']);misses=read_jsonl(d['misses']['path'])
 with gzip.open(h['transactions']['path'],'rt') as f:transactions=json.load(f)
 with gzip.open(t['index']['path'],'rt') as f:time_counter={int(k):v for k,v in json.load(f).items()}
 whole=[r for r in refs if r['whole_index'] is not None]
 if [r['whole_index'] for r in whole]!=list(range(43926)):raise ValueError('WHOLE reference bijection missing')
 by_line=collections.defaultdict(list)
 for r in transactions['BP_reads']:by_line[read_line(r)].append(r)
 return dict(mode=mode,dp=bind(dp),hp=bind(hp),tp=bind(tp),d=d,h=h,t=t,refs=refs,whole=whole,misses=misses,
             by_ordinal={m['reference']['ordinal']:m for m in misses},by_line=by_line,transactions=transactions,time_counter=time_counter)


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 comparison_path=NATURAL/'comparison-v3-01/comparison.json';comparison_before=bind(comparison_path);comparison=json.loads(comparison_path.read_text())
 if comparison_before['sha256']!='ada9f5d99311e80d091abeeae35bb1a6ef92a66f3b0487900ee0694e941d1634':raise ValueError('wrong complete paired comparison')
 cases={m:load_case(m) for m in (0,15)}
 key=lambda r:[r[k] for k in ('context','operation','address','epoch','phase','target')]
 if [key(r) for r in cases[0]['whole']]!=[key(r) for r in cases[15]['whole']]:raise ValueError('whole cached execution differs')
 guests={m:json.loads(Path(comparison['bindings'][str(m)]['guest']['path']).read_text()) for m in (0,15)}
 responses=read_jsonl(comparison['bindings']['15']['retained_events']['path'])
 misses=cases[15]['misses'];starts=[m['reference']['global_cycle'] for m in misses];joined=[]
 for e in responses:
  if e['lane']!='d' or e['event']!='lookup_response':continue
  index=bisect.bisect_right(starts,e['global_cycle'])-1
  if index<0:raise ValueError('lookup precedes normal miss')
  joint=misses[index];r=joint['reference']
  if joint['full_write_cycle']<e['global_cycle'] or r['line']!=e['address'] or r['operation']!='load':raise ValueError('D response lacks actual normal miss ownership')
  if r['whole_index'] is None:raise ValueError('D lookup outside identical checked WHOLE stream')
  base_ref=cases[0]['whole'][r['whole_index']]
  if key(base_ref)!=key(r):raise ValueError('counterpart reference differs')
  base_miss=cases[0]['by_ordinal'].get(base_ref['ordinal'])
  base_reads=matching_reads(base_miss,cases[0]['by_line'],cases[0]['d']['clock']) if base_miss else []
  joint_reads=matching_reads(joint,cases[15]['by_line'],cases[15]['d']['clock'])
  category='baseline_L1_hit' if base_miss is None else 'baseline_matching_HP0_read' if base_reads else 'baseline_normal_miss_without_HP0_read'
  joined.append(dict(whole_index=r['whole_index'],target_index=r['target_index'],context=r['context'],epoch=r['epoch'],phase=r['phase'],address=r['address'],line=r['line'],target=r['target'],
                     response_cycle=e['global_cycle'],retained_hit=e['hit'],retained_accepted_to_consumed_lane_cycles=e['lane_edges'],category=category,
                     baseline_outcome=base_ref['outcome'],baseline_service=base_miss['durations'] if base_miss else None,joint_service=joint['durations'],
                     baseline_HP0_read_sequences=[q['sequence'] for q in base_reads],joint_HP0_read_sequences=[q['sequence'] for q in joint_reads]))
 if len(joined)!=4080 or sum(r['retained_hit'] for r in joined)!=1150:raise ValueError('actual retained response/hit count mismatch')
 summary={};normal_service={};traffic={}
 for window in ('whole','timed_ring'):
  phases=guests[15]['phases'];bounds=(phases['whole_begin'],phases['whole_end']) if window=='whole' else (phases['timed_begin'],phases['timed_end'])
  selected=[r for r in joined if bounds[0]<=r['response_cycle']<bounds[1]];summary[window]={}
  for kind,rows in (('retained_hit',[r for r in selected if r['retained_hit']]),('retained_miss',[r for r in selected if not r['retained_hit']])):
   report=dict(count=len(rows),categories=dict(collections.Counter(r['category'] for r in rows)),target_count=sum(r['target_index'] is not None for r in rows),joint_matching_HP0_reads=sum(len(r['joint_HP0_read_sequences']) for r in rows),
               accepted_to_consumed_lane_cycles=distribution([r['retained_accepted_to_consumed_lane_cycles'] for r in rows]))
   for metric in ('miss_to_first_Dcache_write','miss_to_critical_receive_flag','miss_to_full_L1_write'):
    comparable=[r for r in rows if r['baseline_service'] is not None]
    report[metric]=dict(baseline=distribution([r['baseline_service'][metric] for r in comparable]),joint=distribution([r['joint_service'][metric] for r in comparable]),joint_minus_baseline=distribution([r['joint_service'][metric]-r['baseline_service'][metric] for r in comparable]))
   summary[window][kind]=report
 for mode,case in cases.items():
  phase=guests[mode]['phases'];normal_service[str(mode)]={};traffic[str(mode)]={}
  for window,bounds in (('whole',(phase['whole_begin'],phase['whole_end'])),('timed_ring',(phase['timed_begin'],phase['timed_end']))):
   selected=[m for m in case['misses'] if bounds[0]<=m['reference']['global_cycle']<bounds[1]]
   normal_service[str(mode)][window]=dict(owned_misses=len(selected),pending_D_interval_union_cycles=union_length([(m['reference']['global_cycle'],m['full_write_cycle']) for m in case['misses']],bounds),
           **{metric:distribution([m['durations'][metric] for m in selected]) for metric in ('miss_to_first_Dcache_write','miss_to_critical_receive_flag','miss_to_full_L1_write')})
   clock=case['h']['report']['clock_period_FST_ticks'];axi_zero=case['t']['AXI_cycle_zero_tick'];counter=case['time_counter'];tx=case['transactions']
   inside=lambda tick:bounds[0]<=counter[tick]<bounds[1]
   traffic[str(mode)][window]=dict(AR=sum(inside(r['request_time']) for r in tx['BP_reads']),AW=sum(inside(r['request_time']) for r in tx['BP_writes']),
       R_beats=sum(inside(b['time']) for r in tx['BP_reads'] for b in r['beats']),B=sum(inside(axi_zero+r['complete']*clock) for r in tx['BP_writes']))
 verify(comparison_before)
 a.output.mkdir(parents=True,exist_ok=False)
 with gzip.open(a.output/'counterpart-joins.jsonl.gz','wt') as f:
  for row in joined:f.write(json.dumps(row,separators=(',',':'))+'\n')
 report=dict(state='PASS-closed-matched-service-and-HP0-join',comparison=comparison_before,source=bind(__file__),inputs={str(m):{k:c[k] for k in ('dp','hp','tp')} for m,c in cases.items()},
             WHOLE_identical_cached_references=43926,matched_D_lookups=4080,matched_D_retained_hits=1150,summary=summary,normal_D_service=normal_service,actual_HP0_traffic_by_observed_core_counter=traffic,joins=bind(a.output/'counterpart-joins.jsonl.gz'),
             limits=['Exact same cached-reference sequence; unique physical-line/owned-time-window association, not RID0 source inference.',
                     'No matching HP0 AR is service without observed external read, not automatically an L2 hit. No actual advisory admissions in either complete stream.',
                     'First/critical-receive/full-write intervals are not architectural load readiness. Pending-interval union and per-event deltas do not partition critical-path stalls or WHOLE time.',
                     'Native HP0 first/full is measured1/8AXIcycles for full64B bursts, not calibrated DRAM or FPGA/Linux timing. No projection or new execution.'])
 (a.output/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(state=report['state'],summary={w:{k:{f:r[f] for f in ('count','categories','target_count','joint_matching_HP0_reads')} for k,r in kinds.items()} for w,kinds in summary.items()},traffic=traffic),indent=2))


if __name__=='__main__':main()
