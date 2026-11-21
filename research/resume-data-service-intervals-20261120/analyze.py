#!/usr/bin/env python3
"""Describe accepted D-miss/refill intervals in an already audited CLOSED run.

No CPU stall/critical-path fraction, AXI/DRAM attribution or speedup projection.
First response means first ACCEPTED D-cache fill beat in this event schema.
"""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path


def require(value,message):
    if not value:raise ValueError(message)


def integer(value,name):
    require(isinstance(value,(int,str))and not isinstance(value,bool),'noninteger '+name)
    try:result=int(value,0)if isinstance(value,str)else int(value)
    except (TypeError,ValueError):raise ValueError('invalid '+name)
    require(result==value if not isinstance(value,str)else True,'nonintegral '+name)
    require(0<=result<1<<64,'out-of-range '+name)
    return result


def address(value,name='address'):
    return integer(value,name)


def distribution(values):
    values=sorted(values)
    if not values:return {'count':0,'min':None,'median':None,'p90':None,'p99':None,'max':None,'mean':None}
    def quantile(numerator,denominator):
        # Nearest-rank, with the first observation used at the lower endpoint.
        return values[max(0,(len(values)*numerator+denominator-1)//denominator-1)]
    middle=len(values)//2
    median=values[middle]if len(values)%2 else (values[middle-1]+values[middle])/2
    return {'count':len(values),'min':values[0],'median':median,'p90':quantile(9,10),
            'p99':quantile(99,100),'max':values[-1],'mean':sum(values)/len(values)}


def union_intervals(intervals,bounds=None):
    """Half-open cycle intervals; overlap is descriptive occupancy, not stall."""
    points=Counter();count=carry_in=carry_out=0
    for begin,end in intervals:
        require(begin<=end,'backward interval')
        if bounds is not None:
            lo,hi=bounds;require(lo<hi,'empty/backward clipping window')
            if begin<lo<end:carry_in+=1
            if begin<hi<end:carry_out+=1
            begin,end=max(begin,lo),min(end,hi)
        if begin>=end:continue
        points[begin]+=1;points[end]-=1;count+=1
    pending=peak=total=union=overlap=0;previous=None
    for time,change in sorted(points.items()):
        if previous is not None:
            length=time-previous;total+=length*pending
            if pending:union+=length
            if pending>=2:overlap+=length
        pending+=change;require(pending>=0,'interval sweep underflow')
        peak=max(peak,pending);previous=time
    require(pending==0,'interval sweep not closed')
    return {'half_open':True,'intervals_with_positive_duration':count,
            'sum_individual_pending_cycles':total,'union_pending_cycles':union,
            'cycles_with_at_least_two_pending':overlap,'multiplicity_excess_cycles':total-union,
            'max_pending':peak,'carry_in_intervals':carry_in,'carry_out_intervals':carry_out}


def guest_bounds(guest):
    begin=integer(guest['timed_begin'],'timed_begin');end=integer(guest['timed_end'],'timed_end')
    warm=integer(guest['warm_begin'],'warm_begin')
    require(warm<begin<end and integer(guest['complete_ring_cycles'],'complete_ring_cycles')==end-begin,
            'guest complete-ring bounds disagree')
    regions={}
    for region in guest['regions']:
        context=integer(region['context'],'region context');base=address(region['base']);size=integer(region['bytes'],'region bytes')
        require(context in range(4)and context not in regions and size>0 and base+size<=1<<64,
                'invalid/duplicate corpus region')
        regions[context]=(base,base+size)
    require(set(regions)==set(range(4)),'need all four corpus regions')
    for context,a in regions.items():
        for other,b in regions.items():
            if context<other:require(max(a[0],b[0])>=min(a[1],b[1]),'overlapping corpus byte ranges')
    return warm,begin,end,regions


def analyze(events,guest,audit):
    require(audit['validation']=='passed','source full-access audit did not pass')
    warm,begin,end,regions=guest_bounds(guest)
    counts=Counter();pending={};pairs=[];offsets={};last_global=None;last_cycle={};last_beat_global=None
    known={'reference','fill_beat','fill_complete','eviction','invalidate_all','begin','end'}
    for sequence,event in enumerate(events,1):
        kind=event['event'];require(kind in known,'unknown event at row%d'%sequence)
        domain=event['domain'];require(domain in ('dcache','be'),'unknown clock domain')
        require((domain=='be')==(kind in ('begin','end')),'event/clock domain mismatch')
        cycle=integer(event['cycle'],'domain cycle');global_cycle=integer(event['global_cycle'],'global cycle')
        require(last_global is None or global_cycle>=last_global,'backward global chronology')
        require(domain not in last_cycle or cycle>=last_cycle[domain],'backward domain chronology')
        offset=cycle-global_cycle
        require(domain not in offsets or offsets[domain]==offset,'D/BE edge counter disagrees with core global cycles')
        offsets[domain]=offset;last_cycle[domain]=cycle;last_global=global_cycle;counts[kind]+=1
        if kind not in ('reference','fill_beat','fill_complete'):continue
        line=address(event['line'],'line');require(line%64==0,'unaligned line')
        if kind=='reference':
            addr=address(event['address']);require(addr&~63==line,'reference address/line mismatch')
            outcome=event['outcome'];operation=event['operation'];context=integer(event['context'],'context')
            thread=integer(event['thread'],'physical slot')
            require(outcome in ('miss','l1_hit')and operation in ('load','store')and context in range(4)
                    and thread in range(2),'invalid reference fields')
            require(type(event['target'])is bool and type(event['l1_resident'])is bool,'nonboolean reference flag')
            if outcome=='l1_hit':require(event['l1_resident'],'normal hit is not L1 resident')
            counts[operation]+=1;counts[outcome]+=1
            if event['target']:
                require(event['phase']in ('warm','timed'),'missing target phase')
                epoch=integer(event['epoch'],'epoch');require(epoch<16,'target epoch outside16requests')
                require((epoch<8)==(event['phase']=='warm'),'target epoch/phase mismatch')
                require(regions[context][0]<=addr<regions[context][1],'target address outside own corpus')
                lo,hi=(warm,begin)if event['phase']=='warm'else(begin,end)
                require(lo<=global_cycle<hi,'target reference outside declared phase window')
            else:require(event['phase']is None and event['epoch']is None,'non-target has request phase')
            if outcome=='l1_hit':continue
            require(line not in pending,'ambiguous concurrent misses to same line')
            counts['misses']+=1
            pending[line]={'miss_id':counts['misses'],'line':hex(line),'address':hex(addr),'context':context,
                           'physical_slot':thread,'operation':operation,'target':event['target'],
                           'phase':event['phase'],'epoch':event['epoch'],'miss_global_cycle':global_cycle,
                           'miss_dcache_edge':cycle,'first_global_cycle':None,'last_beat_global_cycle':None,
                           'mask':0,'way':None,'beat_masks':[],'beat_global_cycles':[]}
            continue
        require(line in pending,'fill has no matching pending miss')
        item=pending[line];way=integer(event['way'],'fill way');require(way<8,'fill way outside8ways')
        require(item['way']in (None,way),'fill changed way within a line')
        require(global_cycle>=item['miss_global_cycle'],'fill precedes accepted miss')
        if kind=='fill_beat':
            mask=integer(event['mask'],'beat mask')
            require(0<mask<256 and mask&(mask-1)==0 and item['mask']&mask==0,'invalid/duplicate fill beat')
            require(last_beat_global!=global_cycle,'two data fill beats on one physical D edge')
            require(item['last_beat_global_cycle']is None or global_cycle>item['last_beat_global_cycle'],
                    'nonincreasing beat chronology')
            item['way']=way;item['mask']|=mask;item['beat_masks'].append(mask)
            item['beat_global_cycles'].append(global_cycle);item['last_beat_global_cycle']=global_cycle
            if item['first_global_cycle']is None:item['first_global_cycle']=global_cycle
            last_beat_global=global_cycle
        else:
            require(item['mask']==255 and len(item['beat_masks'])==8,'completion before all eight unique beats')
            require(item['way']==way and global_cycle==item['last_beat_global_cycle'],
                    'completion not paired with actual last beat')
            require(global_cycle>item['miss_global_cycle'],'zero/negative complete service interval')
            item.update(complete_global_cycle=global_cycle,complete_dcache_edge=cycle,
                        miss_to_first_accepted_beat_cycles=item['first_global_cycle']-item['miss_global_cycle'],
                        miss_to_complete_cycles=global_cycle-item['miss_global_cycle'])
            pairs.append(item);del pending[line]
    require(not pending,'EOF with unmatched/incomplete misses')
    pairs.sort(key=lambda item:item['miss_id'])
    expected=audit['stats']
    checks={'reference':'accepted_cached_references','load':'accepted_cached_loads','store':'accepted_cached_stores',
            'misses':'ordinary_misses','l1_hit':'normal_l1_hits','fill_beat':'matched_normal_fill_beats',
            'fill_complete':'matched_complete_normal_refills','eviction':'actual_replacement_evictions'}
    for actual,key in checks.items():require(counts[actual]==expected.get(key,0),'source audit count differs: '+key)
    require(counts['fill_beat']==counts['misses']*8 and counts['fill_complete']==counts['misses'],
            'miss/refill/beat count mismatch')
    require(counts['begin']==counts['end']==len(audit['requests']),'source request-boundary count differs')
    target_timed=[item for item in pairs if item['target']and item['phase']=='timed']
    require(len(target_timed)==sum(r['stats'].get('ordinary_misses',0)for r in audit['requests']if r['phase']=='timed'),
            'target-timed miss count differs from source request audit')
    def describe(rows):
        return {'misses':len(rows),
                'miss_to_first_accepted_beat_cycles':distribution([r['miss_to_first_accepted_beat_cycles']for r in rows]),
                'miss_to_complete_cycles':distribution([r['miss_to_complete_cycles']for r in rows]),
                'pending_to_first_beat':union_intervals([(r['miss_global_cycle'],r['first_global_cycle'])for r in rows]),
                'pending_to_complete':union_intervals([(r['miss_global_cycle'],r['complete_global_cycle'])for r in rows])}
    timed=[item for item in pairs if begin<=item['miss_global_cycle']<end]
    intersecting=[r for r in pairs if max(begin,r['miss_global_cycle'])<min(end,r['complete_global_cycle'])]
    result={'scope':'Descriptive accepted D-cache service intervals only; not CPU stalls, critical path, or speedup.',
            'first_response_definition':'First accepted D-cache fill_beat; not necessarily critical data or first AXI response.',
            'interval_definition':'Half-open [accepted miss, accepted full-line completion), measured in physical core-global cycles.',
            'attribution_limits':['Includes unseparated queue/UCE/hierarchy/transport/service timing.',
                                  'Cannot attribute intervals to I-side interference, memory-only latency, or CPU blocked time.',
                                  'No rescheduled execution or FPGA projection.'],
            'domain_edge_minus_global_offsets':offsets,'source_event_counts':dict(counts),
            'all_program':describe(pairs),'timed_ring':{'bounds':[begin,end],'complete_ring_cycles':end-begin,
                'misses_accepted_in_window':describe(timed),'complete_intervals_intersecting_window':len(intersecting),
                'all_pending_to_first_beat_clipped':union_intervals([(r['miss_global_cycle'],r['first_global_cycle'])for r in pairs],(begin,end)),
                'all_pending_to_complete_clipped':union_intervals([(r['miss_global_cycle'],r['complete_global_cycle'])for r in pairs],(begin,end))},
            'target_timed':describe(target_timed)}
    result['target_timed']['pending_to_complete_clipped']=union_intervals(
        [(r['miss_global_cycle'],r['complete_global_cycle'])for r in target_timed],(begin,end))
    return result,pairs


def record(path):
    path=Path(path);h=hashlib.sha256()
    with path.open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return {'path':str(path.resolve()),'bytes':path.stat().st_size,'sha256':h.hexdigest()}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('events','guest','audit-report','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv);require(not args.output.exists(),'output must be new')
    inputs={name:record(path)for name,path in [('events',args.events),('guest',args.guest),('audit',args.audit_report)]}
    guest=json.loads(args.guest.read_text());audit=json.loads(args.audit_report.read_text())
    with args.events.open()as stream:
        report,pairs=analyze((json.loads(line)for line in stream),guest,audit)
    args.output.mkdir(parents=True)
    (args.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    with(args.output/'misses.jsonl').open('w')as stream:
        for row in pairs:stream.write(json.dumps(row,separators=(',',':'))+'\n')
    require(all(record(Path(item['path']))['sha256']==item['sha256']for item in inputs.values()),
            'input changed during analysis')
    manifest={'state':'passed-descriptive-interval-analysis','source':record(__file__),'inputs':inputs,
              'summary':record(args.output/'summary.json'),'paired_misses':record(args.output/'misses.jsonl'),
              'scope':report['scope'],'no_target_execution':True}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'state':manifest['state'],'misses':len(pairs),'output':str(args.output)},indent=2))


if __name__=='__main__':main()
