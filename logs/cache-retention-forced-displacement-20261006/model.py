#!/usr/bin/env python3
import hashlib,json,statistics
from pathlib import Path
root=Path(__file__).resolve().parents[2]
paths={n:root/f'logs/context-resume-footprint-20261002/{n}.json' for n in ('scan','trie-stream','pointer-compute')}
SETS=64; LINE=64; COLD_INCREMENT=39; RESIDENTS={1,2}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def unique(xs):
 out=[]; seen=set()
 for x in xs:
  if x not in seen: seen.add(x); out.append(x)
 return out

def epochs(accesses):
 out=[]
 for a in accesses:
  c=int(a['context']); line=int(a['address'])//LINE
  if not out or out[-1]['context']!=c: out.append({'context':c,'lines':[],'cycles':[]})
  out[-1]['lines'].append(line)
  out[-1]['cycles'].append(int(a['cycle']))
 return out

def retained(prior,budget,ways):
 out=[]; set_counts={}
 for line in unique(prior):
  if len(out)>=budget: break
  s=line%SETS
  if set_counts.get(s,0)>=ways: continue
  out.append(line); set_counts[s]=set_counts.get(s,0)+1
 return out

def summarize(vals):
 return {'minimum':min(vals),'median':statistics.median(vals),'mean':statistics.mean(vals),'maximum':max(vals)} if vals else None

out={'method':'Assume every resident epoch resumes after complete displacement. Retain the first unique lines from that context previous epoch, capped by both a global 128/192-line budget and 2/3 lines per cache set. Count retained lines used anywhere in the next epoch; each avoids at most one measured 39-cycle cold-data increment. Context 0 is interference and is not evaluated as a resident.','inputs':{str(p.relative_to(root)):sha(p) for p in paths.values()},'traces':{},'limits':['This is a forced-displacement upper bound, not a cache RTL or cycle-accurate replay result.','The source traces are warm; addresses and recurrence are retained, while every evaluated resume is hypothetically made cold.','Only data lines are modeled.','A retained matching line is credited a full 39 cycles even if its real service would hit below L1 or overlap another miss.','First-use history is used; an optimal retention selector could do better.']}
for name,p in paths.items():
 es=epochs(json.loads(p.read_text())['accesses']); prev={}; rows=[]
 for idx,e in enumerate(es):
  c=e['context']
  if c in RESIDENTS and c in prev:
   target=set(e['lines']); span=max(1,e['cycles'][-1]-e['cycles'][0]+1)
   cold_projected=span+len(target)*COLD_INCREMENT
   row={'epoch':idx,'context':c,'target_unique_lines':len(target),'warm_access_span_cycles':span,'forced_cold_projected_cycles':cold_projected,'policies':{}}
   for budget,ways in ((128,2),(192,3)):
    kept=retained(prev[c],budget,ways); hits=len(set(kept)&target)
    retained_projected=span+(len(target)-hits)*COLD_INCREMENT
    row['policies'][f'{budget}l_{ways}w']={'retained_lines':len(kept),'useful_lines':hits,'saved_cycles_upper':hits*COLD_INCREMENT,'forced_cold_projected_cycles_after_retention':retained_projected,'forced_cold_projected_speedup':cold_projected/retained_projected,'forced_cold_projected_reduction_percent':100*(cold_projected-retained_projected)/cold_projected}
   rows.append(row)
  if c in RESIDENTS: prev[c]=e['lines']
 summary={}
 for key in ('128l_2w','192l_3w'):
  useful=[r['policies'][key]['useful_lines'] for r in rows]; saved=[r['policies'][key]['saved_cycles_upper'] for r in rows]
  retained_counts=[r['policies'][key]['retained_lines'] for r in rows]
  speedups=[r['policies'][key]['forced_cold_projected_speedup'] for r in rows]
  reductions=[r['policies'][key]['forced_cold_projected_reduction_percent'] for r in rows]
  summary[key]={'evaluated_resumes':len(rows),'retained_lines':summarize(retained_counts),'useful_lines_per_resume':summarize(useful),'saved_cycles_upper_per_resume':summarize(saved),'forced_cold_projected_speedup':summarize(speedups),'forced_cold_projected_reduction_percent':summarize(reductions),'total_useful_lines':sum(useful),'total_saved_cycles_upper':sum(saved)}
 out['traces'][name]={'summary':summary,'rows':rows}
Path(__file__).with_name('results.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
