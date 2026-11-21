#!/usr/bin/env python3
"""Describe the ONE admitted fully audited pair; no target runs or selection."""
import argparse
import gzip
import hashlib
import heapq
import json
from pathlib import Path
from prepare import HERE,bind
from audit_closed_case import verify


def load_sequence(lines,regions):
    """Normalize immutable target references, never outcome or cycle timing."""
    count=0;digest=hashlib.sha256();requests={}
    for line in lines:
        e=json.loads(line)
        if e['event']!='reference' or not e['target'] or e['epoch'] is None:
            continue
        if e['operation']!='load':raise ValueError('target mutation inside request')
        actor=e['context'];base,size=regions[actor]
        address=int(e['address'],16)
        if not base<=address<base+size:raise ValueError('request accessed another actor corpus')
        normalized=[actor,e['epoch'],e['phase'],address-base,e['operation']]
        digest.update((json.dumps(normalized,separators=(',',':'))+'\n').encode())
        key=f'{actor}:{e["epoch"]}'
        requests[key]=requests.get(key,0)+1;count+=1
    return dict(load_count=count,normalized_sha256=digest.hexdigest(),by_request=requests)


def compare_guests(a,b):
    if a['regions']!=b['regions'] or a.get('stacks')!=b.get('stacks'):
        raise ValueError('private allocation/check/storage identity differs')
    if a['mode']!=0 or b['mode']!=15:raise ValueError('wrong pair modes/order')
    return dict(primary_whole_core_cycles={'off0':a['phases']['whole_cycles'],'joint15':b['phases']['whole_cycles']},
                secondary_ring_core_cycles={'off0':a['phases']['ring_cycles'],'joint15':b['phases']['ring_cycles']})


def join_d_lookup_refills(normal,retained,phases):
    """Every actual D lookup must belong to an accepted ordinary L1 load miss."""
    def selected(lines,is_normal):
        for line in lines:
            e=json.loads(line)
            if is_normal:
                if e['event']=='reference' and e['outcome']=='miss':priority=0
                elif e['event']=='fill_complete':priority=3
                else:continue
            else:
                if e['lane']!='d':continue
                if e['event']=='lookup_accept':priority=1
                elif e['event']=='lookup_response':priority=2
                else:continue
            yield (e['global_cycle'],priority,e)
    pending=None;counts={w:dict(lookups=0,hits=0,misses=0) for w in ('program','whole','timed_ring')}
    for cycle,_,e in heapq.merge(selected(normal,True),selected(retained,False),key=lambda row:row[:2]):
        kind=e['event']
        if kind=='reference':
            if pending is not None:raise ValueError('overlapping ordinary misses')
            pending=dict(line=e['line'],operation=e['operation'],lookup=False,response=False)
        elif kind=='lookup_accept':
            if pending is None or pending['operation']!='load' or pending['line']!=e['address'] or pending['lookup']:
                raise ValueError('D lookup lacks matching accepted ordinary L1 load miss')
            pending['lookup']=True
        elif kind=='lookup_response':
            if pending is None or not pending['lookup'] or pending['response'] or pending['line']!=e['address']:
                raise ValueError('D response lacks ordinary miss ownership')
            pending['response']=True
            for name,bounds in (('program',None),('whole',(phases['whole_begin'],phases['whole_end'])),('timed_ring',(phases['timed_begin'],phases['timed_end']))):
                if bounds is None or bounds[0]<=cycle<bounds[1]:
                    counts[name]['lookups']+=1;counts[name]['hits' if e['hit'] else 'misses']+=1
        else:
            if pending is None or pending['line']!=e['line']:raise ValueError('full refill lacks ordinary miss owner')
            if pending['lookup'] and not pending['response']:raise ValueError('refill completed before retained lookup response')
            pending=None
    if pending is not None:raise ValueError('ordinary miss not fully refilled at closed EOF')
    return counts


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cohort',type=Path,required=True)
    p.add_argument('--audits',type=Path,required=True,help='contains mode{0,15}-{normal,retained}/')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    before=bind(a.cohort);cohort=json.loads(a.cohort.read_text())
    if cohort['state']!='COMPLETE-both-arms-awaiting-full-trace-audit-no-performance-inference':raise ValueError('both complete arms required')
    bindings={};results={};guests={};sequences={}
    for mode in (0,15):
        row=next(r for r in cohort['runs'] if r['mode']==mode)
        if row['state']!='COMPLETE-checks-PASS-awaiting-full-trace-audit':raise ValueError('incomplete arm')
        for key in ('trace','log','guest','trace_metadata'):verify(row[key])
        guests[mode]=json.loads(Path(row['guest']['path']).read_text())
        normal_path=a.audits/f'mode{mode}-normal/summary.json';normal=json.loads(normal_path.read_text())
        retained_path=a.audits/f'mode{mode}-retained/analysis.json';retained=json.loads(retained_path.read_text())
        if normal['state']!='PASS-complete-normal-D-audit' or retained['state']!='PASS-retained-port-audit':raise ValueError('all actual path audits required')
        if normal['cohort']!=before or retained['cohort']!=before:raise ValueError('audit cohort binding mismatch')
        if normal['closed_trace']!=row['trace'] or retained['trace']!=row['trace']:raise ValueError('audit trace binding mismatch')
        if normal['mode']!=mode or retained['mode']!=mode:raise ValueError('audit mode mismatch')
        normal_report=json.loads(Path(normal['normal_dcache_report']['path']).read_text())
        verify(normal['normal_dcache_report'])
        stats=normal_report['report']['stats']
        if stats['ordinary_misses']!=stats['matched_complete_normal_refills'] or stats['matched_normal_fill_beats']!=8*stats['ordinary_misses']:
            raise ValueError('normal full-refill count mismatch')
        regions={r['context']:(r['base'],r['bytes']) for r in guests[mode]['regions']}
        event_path=a.audits/f'mode{mode}-normal/normal-dcache/events.jsonl.gz'
        with gzip.open(event_path,'rt') as f:sequences[mode]=load_sequence(f,regions)
        if sequences[mode]['load_count']!=10586 or len(sequences[mode]['by_request'])!=64:raise ValueError('expected64requests/10586loads not represented')
        retained_events=a.audits/f'mode{mode}-retained/events.jsonl.gz'
        with gzip.open(event_path,'rt') as normal_events,gzip.open(retained_events,'rt') as side_events:
            joined=join_d_lookup_refills(normal_events,side_events,guests[mode]['phases'])
        for window,counts in joined.items():
            actual=retained['report']['counts'][window]['d']
            if (counts['lookups'],counts['hits'])!=(actual.get('lookup_response',0),actual.get('lookup_hit',0)):
                raise ValueError('joined D side-only hit totals differ from actual retained telemetry')
        bindings[str(mode)]=dict(normal=bind(normal_path),retained=bind(retained_path),events=bind(event_path),retained_events=bind(retained_events),guest=row['guest'],trace=row['trace'])
        results[str(mode)]=dict(normal_dcache_counts=normal['counts'],retained_counts=retained['report']['counts'],
                                retired_context_slots=retained['report']['retired_context_slots'],D_lookups_joined_to_ordinary_L1_load_miss_and_complete_refill=joined)
    if sequences[0]!=sequences[15]:raise ValueError('executed target load sequence differs between arms')
    endpoints=compare_guests(guests[0],guests[15])
    for values in endpoints.values():
        values['joint_minus_off']=values['joint15']-values['off0']
        values['joint_relative_change_percent']=100*(values['joint15']/values['off0']-1)
    for record in cohort['frozen_inputs'].values():verify(record)
    if bind(a.cohort)!=before:raise ValueError('closed cohort mutated')
    a.output.mkdir(parents=True,exist_ok=False)
    report=dict(state='CLOSED-complete-audited-single-pair',scope='One preregistered native-simulation capacity/cost pair, not Linux/FPGA application performance or prefetch effectiveness.',
                cohort=before,source=bind(__file__),bindings=bindings,endpoints=endpoints,results=results,
                checked_target_load_sequence=sequences[0],
                model=cohort['model'],elf=cohort['elf'],corrected_base_nbf=cohort['base_nbf'],
                topology=dict(resident_slots=2,logical_contexts=4),
                geometry=dict(ordinary_i_bytes=32768,ordinary_d_bytes=32768,retained_i_full64B_lines=1280,retained_d_full64B_lines=1280,retained_sets=256),
                workload=dict(kind='lookup',private_bytes_per_actor=32768,actors=4,warm_rounds=8,timed_rounds=8),
                limits=['Single pair, no confidence interval or effect-based sample extension; either sign retained.',
                        'WHOLE includes capability/control/alloc/work/check/peerpark/free/off+poll and excludes CRT/load/UART. Baremetal peer parking is not OS process reap.',
                        'Joint demand-populated retention changes capacity/cost; no explicit advisory prefetch. Raw physical slots do not guarantee additional unique capacity, and mutation kills can remove an entire retained set.',
                        'I-only/D-only attribution is not measured by this pair. Legacy conditional victim coverage is not translated into speedup.',
                        'Native HP0 delay0 model is uncalibrated. L2/config differs from old F35 latency40/200 cases; do not pool or project to FPGA/Linux.'])
    (a.output/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(state=report['state'],endpoints=endpoints),indent=2))


if __name__=='__main__':main()
