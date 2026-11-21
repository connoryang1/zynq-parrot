#!/usr/bin/env python3
"""Descriptive accepted retained-port service histograms, never stall time."""
import argparse
import collections
import gzip
import json
from pathlib import Path
from prepare import bind


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--comparison',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 before=bind(a.comparison);comparison=json.loads(a.comparison.read_text())
 if comparison['state']!='CLOSED-complete-audited-single-pair':raise ValueError('complete audited pair required')
 binding=comparison['bindings']['15'];guest=json.loads(Path(binding['guest']['path']).read_text());phases=guest['phases']
 source=binding['retained_events']
 if bind(source['path'])!=source:raise ValueError('closed events changed')
 hist={w:{lane:{k:collections.Counter() for k in ('lookup_hit','lookup_miss','insert_publication','insert_not_published')} for lane in ('i','d')} for w in ('program','whole','timed_ring')}
 with gzip.open(source['path'],'rt') as f:
  for line in f:
   e=json.loads(line);kind=e['event']
   if kind=='lookup_response':kind='lookup_hit' if e['hit'] else 'lookup_miss'
   if kind not in ('lookup_hit','lookup_miss','insert_publication','insert_not_published'):continue
   for window,bounds in (('program',None),('whole',(phases['whole_begin'],phases['whole_end'])),('timed_ring',(phases['timed_begin'],phases['timed_end']))):
    if bounds is None or bounds[0]<=e['global_cycle']<bounds[1]:hist[window][e['lane']][kind][e['lane_edges']]+=1
 result={}
 for window,lanes in hist.items():
  result[window]={}
  for lane,kinds in lanes.items():
   result[window][lane]={}
   for kind,counts in kinds.items():
    expected=comparison['results']['15']['retained_counts'][window][lane].get(kind,0)
    if sum(counts.values())!=expected:raise ValueError('histogram count differs from actual retained audit')
    n=sum(counts.values());ordered=sorted(counts.items());mid=(n-1)//2;running=0;median=None
    for value,count in ordered:
     running+=count
     if median is None and running>mid:median=value
    result[window][lane][kind]=dict(count=n,minimum=min(counts) if counts else None,lower_median=median,maximum=max(counts) if counts else None,histogram=dict(ordered))
 if bind(a.comparison)!=before:raise ValueError('comparison changed')
 if a.output.exists():raise ValueError('preserve existing summary')
 report=dict(state='CLOSED-descriptive-retained-port-service',comparison=before,events=source,source=bind(__file__),result=result,
 scope='Lane-clock edges from accepted lookup to accepted response, or accepted insertion to observed publication/not-published terminal pulse. Does not include waiting before acceptance, ordinary L1 promotion, architectural load readiness, or assign exclusive stall/critical-path time. No causal partition or FPGA projection.')
 a.output.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(result['timed_ring'],indent=2))


if __name__=='__main__':main()
