#!/usr/bin/env python3
"""Audit full-burst AXI service in an exact complete recorded CSR window."""
import argparse
from collections import Counter, deque
import json
from pathlib import Path
import sys
from cache_overlap_vcd import rising_edges

WATCH={
 'clock':'.be.clk_i','axi_clock':'.axi_mem.clk_i','reset':'.be.reset_i',
 'commit_pc':'.be.calculator.commit_pkt_cast_o.pc',
 'commit_v':'.be.calculator.commit_pkt_cast_o.instret',
 'arvalid':'.axi_mem.axi_arvalid_i','arready':'.axi_mem.axi_arready_o',
 'araddr':'.axi_mem.axi_araddr_i','arlen':'.axi_mem.axi_arlen_i',
 'arsize':'.axi_mem.axi_arsize_i','arid':'.axi_mem.axi_arid_i',
 'rvalid':'.axi_mem.axi_rvalid_o','rready':'.axi_mem.axi_rready_i',
 'rlast':'.axi_mem.axi_rlast_o','rid':'.axi_mem.axi_rid_o',
 'latency':'.axi_mem.read_latency_p',
 'queue_depth':'.axi_mem.read_queue_els_p', 'arburst':'.axi_mem.axi_arburst_i'}


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 args=p.parse_args();scopes=[];found={}
 for line in sys.stdin:
  w=line.split()
  if w[:1]==['$scope']:scopes.append(w[2])
  elif w[:1]==['$upscope']:scopes.pop()
  elif w[:1]==['$var']:
   full='.'.join(scopes+[w[4]])
   for name,suffix in WATCH.items():
    if full.endswith(suffix):found.setdefault(name,[]).append((w[3],full))
  elif w[:1]==['$enddefinitions']:break
 for key in WATCH:
  if len(found.get(key,[]))!=1:raise ValueError('missing/ambiguous '+key)
 selected={k:v[0] for k,v in found.items()}
 if selected['clock'][0]!=selected['axi_clock'][0]:
  raise ValueError('this narrow audit requires verified identical BE and AXI clocks')
 active=False;bounds=[];arlen=Counter();arsize=Counter();pending=deque();maxpending=0
 total_ar=0;timed_ar=[];complete=[];latencies=set();depths=set();issues=[];timed_backpressure=0
 for cycle,timestamp,v in rising_edges(sys.stdin,selected):
  if v.get('reset')!=0:continue
  latencies.add(v['latency']);depths.add(v['queue_depth'])
  if v['commit_v']==1 and v['commit_pc']==0x8000040c:
   if active:raise ValueError('overlapping window')
   active=True;bounds.append({'kind':'begin','cycle':cycle,'timestamp':timestamp})
  if v['commit_v']==1 and v['commit_pc']==0x80000414:
   if not active:raise ValueError('end without begin')
   active=False;bounds.append({'kind':'end','cycle':cycle,'timestamp':timestamp})
  if active and v['rvalid']==1 and v['rready']==0:timed_backpressure+=1
  if v['rvalid']==1:
   if not pending:issues.append({'cycle':cycle,'reason':'response without accepted AR'})
   else:
    tx=pending[0]
    if tx['first_offer_cycle'] is None:tx['first_offer_cycle']=cycle
    if tx['id']!=v['rid']:issues.append({'cycle':cycle,'reason':'response id mismatch'})
    if v['rready']==1:
     tx['accepted_beats']+=1
     tx['accepted_beat_cycles'].append(cycle)
     if v['rlast']==1:
      tx['completion_cycle']=cycle
      if tx['accepted_beats']!=tx['len']+1:
       issues.append({'cycle':cycle,'reason':'accepted burst length differs from ARLEN'})
      pending.popleft();complete.append(tx)
  if v['arvalid']==1 and v['arready']==1:
   total_ar+=1
   tx={'ar_cycle':cycle,'address':hex(v['araddr']),'id':v['arid'],'len':v['arlen'],
       'size_log2_bytes':v['arsize'],'burst':v['arburst'],'timed':active,
       'first_offer_cycle':None,'accepted_beats':0,'accepted_beat_cycles':[]}
   pending.append(tx);maxpending=max(maxpending,len(pending))
   if active:timed_ar.append(tx);arlen[v['arlen']]+=1;arsize[v['arsize']]+=1
 if len(bounds)!=2 or active:raise ValueError('need one complete CSR-commit-bounded window')
 timed_complete=[x for x in complete if x['timed']]
 lines=Counter(int(x['address'],16)&~63 for x in timed_ar)
 offer=Counter(x['first_offer_cycle']-x['ar_cycle'] for x in timed_complete)
 done=Counter(x['completion_cycle']-x['ar_cycle'] for x in timed_complete)
 gaps=Counter(b-a for x in timed_complete for a,b in zip(x['accepted_beat_cycles'],x['accepted_beat_cycles'][1:]))
 result={'scope':'full-burst wrapper conditional synthetic AXI service audit, not measured DRAM/FPGA latency',
  'sampling':'stable values before actual BE/AXI rising edge; identical VCD clock identifier verified',
  'signals':{k:v[1] for k,v in selected.items()},'identical_be_axi_clock':True,
  'configured_model_latency_ticks':sorted(latencies),'configured_queue_depth':sorted(depths),
  'timed_r_backpressure_cycles':timed_backpressure,'timed_accepted_beat_gap_ticks':dict(gaps),'timed_boundaries':bounds,
  'timed_commit_window_cycles':bounds[1]['cycle']-bounds[0]['cycle'],
  'total_accepted_ar':total_ar,'timed_accepted_ar':len(timed_ar),
  'timed_arlen_histogram':dict(arlen),'timed_arsize_histogram':dict(arsize),
  'timed_ar_by_raw_axi_64byte_line':{hex(k):v for k,v in sorted(lines.items())},
  'max_outstanding_ar_entire_run':maxpending,
  'timed_ar_to_first_r_offer_ticks':dict(offer),'timed_ar_to_last_r_accept_ticks':dict(done),
  'timed_transactions':timed_ar,'pending_at_trace_end':len(pending),'issues':issues}
 args.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ('identical_be_axi_clock','configured_model_latency_ticks',
   'timed_commit_window_cycles','timed_accepted_ar','timed_arlen_histogram','timed_arsize_histogram',
   'timed_ar_by_raw_axi_64byte_line','max_outstanding_ar_entire_run',
   'timed_ar_to_first_r_offer_ticks','timed_ar_to_last_r_accept_ticks','issues')},indent=2))

if __name__=='__main__':main()
