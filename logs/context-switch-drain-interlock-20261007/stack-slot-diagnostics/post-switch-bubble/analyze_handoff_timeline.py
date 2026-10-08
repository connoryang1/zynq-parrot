#!/usr/bin/env python3
from pathlib import Path
import csv, json
root=Path(__file__).resolve().parent
with (root/'handoff-timeline.tsv').open() as f:
 rows=list(csv.DictReader(f,delimiter='\t'))
for r in rows:
 for k,v in list(r.items()):
  r[k]=int(v,16) if k in ('ipc','dpc','dpaddr') else int(v)
final_start=37230000000
final_rows=[r for r in rows if r['time'] >= final_start]
final_switches=[r for r in final_rows if r['dsw'] and r['dpc']==0x8000059c]
all_switches=[r for r in rows if r['dsw']]
commits=[r for r in rows if r['csw']]
pfhits=[r for r in rows if r['pfhit']]
transport_keys=('reqacc','respacc','fill','pfwrite')
trans={k:sum(r[k] for r in final_rows) for k in transport_keys}
last_transport={k:max((r['time'] for r in rows if r[k]),default=None) for k in transport_keys}
context2_demand=37242250000
pointer_demands=[]
for ctx in range(10):
 candidates=[r for r in final_rows
             if r['ctx']==ctx and r['dtv'] and 0x80000000 <= r['dpaddr'] < 0x80021000
             and (r['dpaddr'] & 63) == 0]
 first=candidates[0]
 replay=next((r for r in candidates[1:]
              if r['dpaddr']==first['dpaddr'] and r['dlhit']),None)
 pointer_demands.append({
     'context':ctx,
     'address':hex(first['dpaddr']),
     'set':(first['dpaddr'] >> 6) & 63,
     'first_time':first['time'],
     'initial_l1_hit_vector':first['dlhit'],
     'side_buffer_hit':bool(first['pfhit']),
     'replay_time':None if replay is None else replay['time'],
     'replay_l1_hit_vector':None if replay is None else replay['dlhit'],
     'miss_to_replay_cycles':None if replay is None else (replay['time']-first['time'])//50000,
 })
result={
 'trace_window':[min(r['time'] for r in rows),max(r['time'] for r in rows)],
 'trace_cycles':(max(r['time'] for r in rows)-min(r['time'] for r in rows))//50000,
 'final_lap_start':final_start,
 'final_switch_dispatches':len(final_switches),
 'final_switch_contexts':[r['ctx'] for r in final_switches],
 'switch_dispatches_with_retained_prefetch_state':sum(bool(r['pfvalid']) for r in all_switches),
 'switch_dispatches_without_retained_prefetch_state':sum(not r['pfvalid'] for r in all_switches),
 'switch_dispatch_retained_prefetch_fraction':sum(bool(r['pfvalid']) for r in all_switches)/len(all_switches),
 'final_switch_dispatches_with_retained_prefetch_state':sum(bool(r['pfvalid']) for r in final_switches),
 'final_switch_dispatches_without_retained_prefetch_state':sum(not r['pfvalid'] for r in final_switches),
 'final_switch_dispatch_retained_prefetch_fraction':sum(bool(r['pfvalid']) for r in final_switches)/len(final_switches),
 'final_switch_retained_prefetch_contexts':[r['ctx'] for r in final_switches if r['pfvalid']],
 'final_switch_all_mem_busy_zero':all(not r['mb'] for r in final_switches),
 'final_switch_all_mem_ordered_one':all(r['mo'] for r in final_switches),
 'final_switch_all_order_hazard_zero':all(not r['oh'] for r in final_switches),
 'switch_commits':len(commits),
 'detached_transport_events':trans,
 'last_detached_transport_event':last_transport,
 'context2_demand_time':context2_demand,
 'last_fill_to_context2_demand_cycles':(context2_demand-last_transport['fill'])//50000,
 'last_buffer_write_to_context2_demand_cycles':(context2_demand-last_transport['pfwrite'])//50000,
 'side_buffer_hits':[{'time':r['time'],'ctx':r['ctx'],'pc':hex(r['dpc']),'segment':r['pfseg'],'slot':r['pfslot'],'valid_vector':hex(r['pfvalid'])} for r in pfhits],
 'side_buffer_hit_contexts':sorted(set(r['ctx'] for r in pfhits)),
 'final_pointer_demands':pointer_demands,
 'ordinary_pointer_misses':sum(not r['side_buffer_hit'] and r['initial_l1_hit_vector']==0 for r in pointer_demands),
 'interpretation':'The final lap has no detached request, response, fill, or buffer-write event. Every final switch dispatch sees mem_busy=0, mem_ordered=1, and no order hazard. One prior-lap side-buffer entry remains and only context 4 consumes its two words. A repair conditional only on active transport would not delay the context-0/1/2 boundaries surrounding the physical corruption window. Retained prefetch state is present at 38/48 traced switch dispatches and 4/10 final dispatches, including context 2, so it is a plausible but only moderately selective condition.',
}
(root/'handoff-timeline-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
