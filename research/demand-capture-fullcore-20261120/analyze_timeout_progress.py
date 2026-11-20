#!/usr/bin/env python3
"""Verify architectural progress from a closed FST converted on stdin.

Samples pre-edge stable values at actual BE clock rises using the maintained
cache_overlap_vcd parser. No guessed timescale-to-cycle conversion is used.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from cache_overlap_vcd import rising_edges

WATCH = {
    'clock': '.be.clk_i',
    'reset': '.be.reset_i',
    'commit_pc': '.be.calculator.commit_pkt_cast_o.pc',
    'commit_v': '.be.calculator.commit_pkt_cast_o.instret',
    'dispatch_pc': '.be.scheduler.dispatch_pkt_cast_o.pc',
    'dispatch_v': '.be.scheduler.dispatch_pkt_cast_o.v',
    'expected_npc': '.be.director.expected_npc_o',
    'icache_state': '.fe.icache.state_r',
    'capture_active': '.fe.icache.demand_capture_active_r',
}
PHASE_STORES = {0x8000029e: 1, 0x800002aa: 2, 0x800002dc: 3,
                0x80000342: 4, 0x80000380: 5, 0x8000040c: 6, 0x80000468: 7}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    scopes=[]; found={}; timescale=[]; in_timescale=False
    for line in sys.stdin:
        w=line.split()
        if '$timescale' in line: in_timescale=True
        if in_timescale:
            timescale += [x for x in w if x not in ('$timescale','$end')]
            if '$end' in line: in_timescale=False
        if w[:1]==['$scope']: scopes.append(w[2])
        elif w[:1]==['$upscope']: scopes.pop()
        elif w[:1]==['$var']:
            full='.'.join(scopes+[w[4]])
            for key,suffix in WATCH.items():
                if full.endswith(suffix):
                    found.setdefault(key,[]).append((w[3],full))
        elif w[:1]==['$enddefinitions']: break
    for key in ('clock','reset','commit_pc','commit_v'):
        if len(found.get(key,[]))!=1:
            raise ValueError('missing or ambiguous '+key+': '+repr(found.get(key)))
    selected={key:values[0] for key,values in found.items() if len(values)==1}
    last_commits=deque(maxlen=128); last_bins=deque(maxlen=16)
    phase_events=[]; retired=0; body_retired=0; last_commit_cycle=None
    last_body_cycle=None; longest_body_gap=0; current_bin=None; bin_data=None
    final=None; edges=0
    for cycle,timestamp,values in rising_edges(sys.stdin,selected):
        edges=cycle+1; final={'cycle':cycle,'timestamp':timestamp,'values':values}
        bin_index=cycle//1000
        if bin_index!=current_bin:
            if bin_data is not None: last_bins.append(bin_data)
            current_bin=bin_index
            bin_data={'start_cycle':bin_index*1000,'retired':0,
                      'first_pc':None,'last_pc':None}
        if values.get('reset')!=0 or values.get('commit_v')!=1: continue
        pc=values['commit_pc']; retired+=1
        event={'cycle':cycle,'timestamp':timestamp,'pc':hex(pc)}
        last_commits.append(event); last_commit_cycle=cycle
        bin_data['retired']+=1
        if bin_data['first_pc'] is None: bin_data['first_pc']=hex(pc)
        bin_data['last_pc']=hex(pc)
        if pc in PHASE_STORES:
            phase_events.append(dict(event,phase=PHASE_STORES[pc]))
        if 0x800007c0<=pc<0x800087c0:
            body_retired+=1
            if last_body_cycle is not None:
                longest_body_gap=max(longest_body_gap,cycle-last_body_cycle)
            last_body_cycle=cycle
    if bin_data is not None: last_bins.append(bin_data)
    out={'scope':'architectural progress only; no performance/RTL acceptance',
         'sampling':'stable values before actual be.clk_i rising edges',
         'timescale':''.join(timescale),'signals':{k:v[1] for k,v in selected.items()},
         'be_edges':edges,'retired':retired,'nop_stream_retired':body_retired,
         'longest_nop_stream_commit_gap_cycles':longest_body_gap,
         'cycles_since_final_commit':None if last_commit_cycle is None else edges-1-last_commit_cycle,
         'phase_store_commits':phase_events,'last_1000cycle_bins':list(last_bins),
         'last_commits':list(last_commits),'final':final}
    args.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:out[k] for k in ('be_edges','retired','nop_stream_retired',
                        'longest_nop_stream_commit_gap_cycles','cycles_since_final_commit',
                        'phase_store_commits','last_1000cycle_bins')},indent=2))

if __name__=='__main__': main()
