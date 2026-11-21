#!/usr/bin/env python3
"""Index accepted HP0 event times by actual sampled core counter; no target."""
import argparse
import gzip
import json
from pathlib import Path
import time
from hp0_closed_pair import HERE,HP0,hp0,bind,verify,expected_signals


def transaction_times(document,period):
 reads=document['BP_reads'];writes=document['BP_writes']
 if not reads:raise ValueError('no actual AR epoch')
 offset=reads[0]['request_time']-reads[0]['request_cycle']*period;points=set()
 for request in reads+writes:
  if request['request_time']-request['request_cycle']*period!=offset:raise ValueError('AXI timestamp/cycle offset changed')
  points.add(request['request_time']);points.add(offset+request['complete']*period)
  for beat in request['beats']+request['wbeats']:
   if beat['time']-beat['cycle']*period!=offset:raise ValueError('AXI beat timestamp/cycle mismatch')
   points.add(beat['time'])
 return points,offset


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',type=int,choices=(0,15),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 proof_path=HERE/f'mode{a.mode}-hp0/analysis.json';before=bind(proof_path);proof=json.loads(proof_path.read_text())
 if proof['state']!='PASS-closed-native-HP0-audit':raise ValueError('closed complete HP0 proof required')
 for record in proof['sources'].values():verify(record)
 verify(proof['selected_events']);verify(proof['transactions'])
 with gzip.open(proof['transactions']['path'],'rt') as f:transactions=json.load(f)
 period=proof['report']['clock_period_FST_ticks'];points,axi_offset=transaction_times(transactions,period)
 counter={};advisories=[];reset_seen={'i':False,'d':False};deadline=time.monotonic()+600;count=0
 with gzip.open(proof['selected_events']['path'],'rt') as f:
  for tick,clocks,s in hp0.edge_samples(f,expected_signals()):
   count+=1
   if count%2048==0 and time.monotonic()>deadline:raise TimeoutError('bounded saved-HP0 indexing')
   if 'clk' in clocks and tick in points:
    if s['be.global'] is None or not s['resetn']:raise ValueError('accepted packet lacks known live core counter')
    counter[tick]=s['be.global']
   for lane in ('i','d'):
    if lane+'.clk' not in clocks:continue
    g=lambda k:s[lane+'.'+k]
    if g('reset'):reset_seen[lane]=True;continue
    if not reset_seen[lane]:continue
    if g('reqv') and g('reqy') and g('reqtype')==9:advisories.append(dict(time=tick,core_cycle=s['be.global'],lane=lane,kind='cache-prefetch',address=g('reqaddr')))
    for kind in ('detached','preview'):
     if g(kind+'v') and g(kind+'ready'):advisories.append(dict(time=tick,core_cycle=s['be.global'],lane=lane,kind=kind,address=g(kind+'addr')))
 if set(counter)!=points or not all(reset_seen.values()):raise ValueError('accepted packet timestamps or resets missing')
 be=proof['report']['first_architectural_start'];be_period=proof['report']['BE_clock_period_ticks']
 be_offset=be['tick']-be['global_cycle']*be_period
 affine=all(t-c*be_period==be_offset for t,c in counter.items())
 verify(proof['selected_events']);verify(before)
 a.output.mkdir(parents=True,exist_ok=False)
 with gzip.open(a.output/'time-counter.json.gz','wt') as f:json.dump(counter,f,separators=(',',':'),sort_keys=True)
 report=dict(state='PASS-HP0-actual-time-core-counter-index',mode=a.mode,HP0_proof=before,source=bind(__file__),
             selected_events=proof['selected_events'],transactions=proof['transactions'],index=bind(a.output/'time-counter.json.gz'),
             points=len(points),AXI_period_ticks=period,AXI_cycle_zero_tick=axi_offset,BE_period_ticks=be_period,BE_counter_offset_tick=be_offset,
             observed_transaction_points_follow_BE_affinity=affine,advisory_admissions=advisories,
             scope='Actual before-edge core counter at every accepted AR/AW/R/W/B packet timestamp; no guessed AXI:BE ratio. Advisory admissions sampled separately on each UCE clock; all program/reporting traffic included here.')
 (a.output/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report[k] for k in ('state','mode','points','AXI_period_ticks','BE_period_ticks','BE_counter_offset_tick','observed_transaction_points_follow_BE_affinity','advisory_admissions')},indent=2))


if __name__=='__main__':main()
