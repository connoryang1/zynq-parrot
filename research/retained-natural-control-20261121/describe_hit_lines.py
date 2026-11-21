#!/usr/bin/env python3
"""Distinct actual D retained-hit lines; no occupancy/capacity/speedup model."""
import argparse
import bisect
import collections
import gzip
import json
from pathlib import Path
from prepare import bind


def describe(normal,retained,phases):
    intervals=[];pending=None
    for line in normal:
        e=json.loads(line)
        if e['event']=='reference' and e['outcome']=='miss':
            if pending is not None:raise ValueError('overlapping miss intervals')
            pending=e
        elif e['event']=='fill_complete':
            if pending is None or pending['line']!=e['line']:raise ValueError('unmatched full refill')
            intervals.append((pending['global_cycle'],e['global_cycle'],pending));pending=None
    if pending is not None:raise ValueError('undrained ordinary miss')
    starts=[r[0] for r in intervals]
    result={w:dict(total_hits=0,lines=set(),request_target_hits=0,target_lines=set(),by_actor={str(a):set() for a in range(4)}) for w in ('program','whole','timed_ring')}
    for line in retained:
        e=json.loads(line)
        if e['lane']!='d' or e['event']!='lookup_response' or not e['hit']:continue
        cycle=e['global_cycle'];index=bisect.bisect_right(starts,cycle)-1
        if index<0:raise ValueError('hit precedes ordinary miss')
        begin,end,owner=intervals[index]
        if not begin<=cycle<=end or owner['line']!=e['address'] or owner['operation']!='load':raise ValueError('hit/ordinary-miss interval provenance mismatch')
        for window,bounds in (('program',None),('whole',(phases['whole_begin'],phases['whole_end'])),('timed_ring',(phases['timed_begin'],phases['timed_end']))):
            if bounds is not None and not bounds[0]<=cycle<bounds[1]:continue
            counts=result[window];counts['total_hits']+=1;counts['lines'].add(e['address'])
            if owner['target'] and owner['epoch'] is not None:
                counts['request_target_hits']+=1;counts['target_lines'].add(e['address']);counts['by_actor'][str(owner['context'])].add(e['address'])
    return {w:dict(total_hits=c['total_hits'],distinct_hit_lines=len(c['lines']),request_target_hits=c['request_target_hits'],
                   distinct_request_target_lines=len(c['target_lines']),distinct_request_target_lines_by_actor={a:len(lines) for a,lines in c['by_actor'].items()}) for w,c in result.items()}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--comparison',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    before=bind(a.comparison);comparison=json.loads(a.comparison.read_text())
    if comparison['state']!='CLOSED-complete-audited-single-pair':raise ValueError('all complete paired audits required')
    records=comparison['bindings']['15'];guest=json.loads(Path(records['guest']['path']).read_text())
    for k in ('events','retained_events','guest'):
        if bind(records[k]['path'])!=records[k]:raise ValueError('closed input changed')
    with gzip.open(records['events']['path'],'rt') as normal,gzip.open(records['retained_events']['path'],'rt') as retained:
        counts=describe(normal,retained,guest['phases'])
    for window,c in counts.items():
        expected=comparison['results']['15']['D_lookups_joined_to_ordinary_L1_load_miss_and_complete_refill'][window]['hits']
        if c['total_hits']!=expected:raise ValueError('distinct-line description lost actual hits')
    if bind(a.comparison)!=before:raise ValueError('comparison changed')
    if a.output.exists():raise ValueError('preserve existing description')
    report=dict(state='CLOSED-actual-D-hit-line-description',comparison=before,source=bind(__file__),inputs={k:records[k] for k in ('events','retained_events','guest')},counts=counts,
                scope='Observed distinct lines across complete execution, not simultaneous residency, guaranteed extra unique slots, a capacity curve or a performance projection. Request-target hits are joined to actual normal L1 load misses inside independently checked request windows.')
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
