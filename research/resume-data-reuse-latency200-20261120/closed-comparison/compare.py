#!/usr/bin/env python3
"""Compare only the two CLOSED, audited, same32KiB controls; no execution."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path('/home/coyang/zynq-parrot-linux-research')
OUT=Path(__file__).resolve().parent
C40=ROOT/'research/resume-data-reuse-20261120/compact-thirtytwo-kib'
C200=OUT.parent/'compact-thirtytwo-kib'
SERVICE=ROOT/'research/resume-data-service-intervals-20261120'
SPEC=importlib.util.spec_from_file_location('service_intervals',SERVICE/'analyze.py')
S=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(S)


def require(value,message):
    if not value:raise ValueError(message)


def rec(path):
    path=Path(path);h=hashlib.sha256()
    with path.open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return {'path':str(path.resolve()),'bytes':path.stat().st_size,'sha256':h.hexdigest()}


def verify(item):
    require(rec(item['path'])['sha256']==item['sha256'],'changed bound artifact: '+item['path'])


def load(case,latency):
    session=json.loads((case/'session.json').read_text())
    audit=json.loads((case/'dcache-audit/manifest.json').read_text())
    report=json.loads((case/'dcache-audit/analysis.json').read_text())
    guest=json.loads((case/'guest-observations.json').read_text())
    metadata=json.loads((case/'trace-metadata.json').read_text())
    require(session['state']in('pass','pass-full-audit')and session['protocol']=='compact-v1'
            and session['footprint_kib']==32 and session['physical_slots']==2 and session['logical_contexts']==4,
            'case is not a closed matching32KiB program')
    require(audit['state']=='passed'and audit['complete_converter_eof']and
            audit['converter_returncode']==audit['analyzer_returncode']==0and report['validation']=='passed',
            'full audit/converter incomplete')
    for item in session['source'].values():verify(item)
    for key in('elf','mem','nbf','symbol_file','disassembly'):verify(session['program'][key])
    for key in('runtime_nbf','run_log','stopped_fst','acceptance','guest_observations','trace_metadata'):verify(session[key])
    require(len(report['requests'])==64,'not64 complete requests')
    for context in range(4):
        rows=[row for row in report['requests']if row['context']==context]
        require([row['epoch']for row in rows]==list(range(16))and
                [row['stats']['target_loads']for row in rows]==metadata['expected_target_loads_by_context'][str(context)],
                'request count/independent workload counts differ')
    service=json.loads((SERVICE/('closed%d'%latency)/'summary.json').read_text())
    pairs=[json.loads(line)for line in(SERVICE/('closed%d'%latency)/'misses.jsonl').open()]
    events=[];timed=Counter();all_refs=[]
    for line in(case/'dcache-audit/events.jsonl').open():
        event=json.loads(line)
        if event['event']!='reference':continue
        all_refs.append(event)
        if guest['timed_begin']<=event['global_cycle']<guest['timed_end']:
            timed[event['outcome']]+=1;timed[event['operation']]+=1
            if event['target']:timed['target_'+event['outcome']]+=1
    return {'session':session,'audit':audit,'report':report,'guest':guest,'metadata':metadata,
            'service':service,'pairs':pairs,'timed_counts':dict(timed),'references':all_refs}


def reference_key(row):
    return tuple(row[key]for key in('address','line','context','operation','outcome','target','phase','epoch'))


def extra_reference_diagnostic(a,b,guest200):
    """Bounded linear insertion check, not an assumed architectural equivalence."""
    i=j=0;extras=[];mismatch=None
    while i<len(a)and j<len(b):
        if reference_key(a[i])==reference_key(b[j]):i+=1;j+=1;continue
        found=next((skip for skip in(1,2)if j+skip<len(b)and reference_key(a[i])==reference_key(b[j+skip])),None)
        if found is None:
            mismatch={'old_index':i,'new_index':j,'old':a[i],'new':b[j]};break
        extras.extend(b[j:j+found]);j+=found
    if mismatch is None and i==len(a):extras.extend(b[j:])
    elif mismatch is None:mismatch={'unmatched_old_tail':len(a)-i}
    for row in extras:
        g=row['global_cycle'];row['relative_to_timed_ring']=('before'if g<guest200['timed_begin']else
                                    'inside'if g<guest200['timed_end']else'after')
    return {'40_is_200_subsequence_with_only_reported_insertions':mismatch is None,
            'ignores_physical_slot_and_timestamps':True,'extra200_references':extras,'first_other_difference':mismatch}


def main():
    a,b=load(C40,40),load(C200,200)
    identities={key:a['session']['program'][key]['sha256']==b['session']['program'][key]['sha256']
                for key in('elf','mem','nbf','symbol_file','disassembly')}
    identities.update(runtime_nbf=a['session']['runtime_nbf']['sha256']==b['session']['runtime_nbf']['sha256'],
                      source_hashes={key:item['sha256']for key,item in a['session']['source'].items()}==
                                    {key:item['sha256']for key,item in b['session']['source'].items()},
                      corpus_checksums_bases_bytes_runs=a['guest']['regions']==b['guest']['regions'],
                      static_peer_stacks=a['guest']['stacks']==b['guest']['stacks'],
                      request_metadata=a['metadata']==b['metadata'])
    require(all(identities.values()),'fixed-work/program/layout identity changed')
    stats={key:{'40':a['report']['stats'].get(key,0),'200':b['report']['stats'].get(key,0),
                'delta':b['report']['stats'].get(key,0)-a['report']['stats'].get(key,0)}
           for key in sorted(set(a['report']['stats'])|set(b['report']['stats']))}
    coverage=[]
    for capacity in('0','4','16','32','64','128'):
        old,new=a['report']['coverage'][capacity],b['report']['coverage'][capacity]
        coverage.append({'extra_victim_lines':int(capacity),'full_conditional_counters_identical':old==new,
                         '40':old,'200':new})
    keys=('line','address','context','operation','target','phase','epoch')
    semantic=lambda rows:[tuple(row[key]for key in keys)for row in rows]
    pair_match=semantic(a['pairs'])==semantic(b['pairs'])
    paired={}
    if pair_match:
        for group in('all','timed','target_timed'):
            selected=[]
            for old,new in zip(a['pairs'],b['pairs']):
                timed40=a['guest']['timed_begin']<=old['miss_global_cycle']<a['guest']['timed_end']
                timed200=b['guest']['timed_begin']<=new['miss_global_cycle']<b['guest']['timed_end']
                if group=='timed'and not(timed40 and timed200):continue
                if group=='target_timed'and not(old['target']and old['phase']=='timed'):continue
                selected.append((old,new))
            first=[new['miss_to_first_accepted_beat_cycles']-old['miss_to_first_accepted_beat_cycles']for old,new in selected]
            complete=[new['miss_to_complete_cycles']-old['miss_to_complete_cycles']for old,new in selected]
            paired[group]={'pairs':len(selected),'first_accepted_beat_delta':S.distribution(first),
                           'complete_delta':S.distribution(complete),'delta_histogram':dict(sorted(Counter(complete).items()))}
        paired['same_way_and_rotated_mask_sequence']=all(old['way']==new['way']and old['beat_masks']==new['beat_masks']
                                                       for old,new in zip(a['pairs'],b['pairs']))
        paired['changed_relative_beat_schedules']=sum(
            [g-old['first_global_cycle']for g in old['beat_global_cycles']]!=
            [g-new['first_global_cycle']for g in new['beat_global_cycles']]
            for old,new in zip(a['pairs'],b['pairs']))
    timed_refs=lambda case:[row for row in case['references']
        if case['guest']['timed_begin']<=row['global_cycle']<case['guest']['timed_end']]
    timed_sequence_equal=[reference_key(row)for row in timed_refs(a)]==[reference_key(row)for row in timed_refs(b)]
    require(timed_sequence_equal,'timed accepted reference semantic sequence changed')
    require(pair_match and all(row['full_conditional_counters_identical']for row in coverage),
            'miss sequence or conditional capacity ledger changed')
    delta=b['guest']['complete_ring_cycles']-a['guest']['complete_ring_cycles']
    pending40=a['service']['timed_ring']['all_pending_to_complete_clipped']['union_pending_cycles']
    pending200=b['service']['timed_ring']['all_pending_to_complete_clipped']['union_pending_cycles']
    nominal=a['service']['timed_ring']['misses_accepted_in_window']['misses']*160
    result={'state':'closed-complete-fixed-footprint-latency-comparison','scope':'Controlled synthetic first-response sensitivity only; not FPGA projection or exclusive causal-stall partition.',
            'fixed_input_identities':identities,'complete_ring_cycles':{'40':a['guest']['complete_ring_cycles'],
                  '200':b['guest']['complete_ring_cycles'],'delta':delta},'native_guard_seconds':{'40':1800,'200':2400},
            'timed_reference_semantic_sequence_identical':timed_sequence_equal,'full_program_statistics':stats,'timed_reference_counts':{'40':a['timed_counts'],'200':b['timed_counts']},
            'conditional_victim_curves':coverage,'accepted_miss_semantic_sequence_identical':pair_match,
            'paired_service_deltas':paired,'service_intervals':{'40':a['service'],'200':b['service']},
            'arithmetic_co_movement_not_partition':{'timed_D_misses_40':1711,'configured_tick_delta':160,
                 'miss_count_times_tick_delta':nominal,'whole_ring_delta':delta,'whole_minus_nominal_product':delta-nominal,
                 'pending_union40':pending40,'pending_union200':pending200,'pending_union_delta':pending200-pending40,
                 'whole_delta_minus_pending_union_delta':delta-(pending200-pending40),
                 'interpretation':'Numerical co-movement, not proof that pending occupancy is CPU stalls or that the residual exclusively belongs to I/queue/compute.'},
            'full_reference_sequence_diagnostic':extra_reference_diagnostic(a['references'],b['references'],b['guest']),
            'source':rec(__file__),'service_analyzer_source':rec(SERVICE/'analyze.py'),'service_tests_source':rec(SERVICE/'test_analyze.py'),'input_bindings':{}}
    for label,case,lat in(('40',C40,40),('200',C200,200)):
        result['input_bindings'][label]={name:rec(case/name)for name in('session.json','guest-observations.json',
            'trace-metadata.json','dcache-audit/manifest.json','dcache-audit/analysis.json','dcache-audit/events.jsonl')}
        result['input_bindings'][label]['model']=rec(a['session']['model']['path']if label=='40'else b['session']['model']['path'])
        result['input_bindings'][label]['service_summary']=rec(SERVICE/('closed%d'%lat)/'summary.json')
        result['input_bindings'][label]['service_manifest']=rec(SERVICE/('closed%d'%lat)/'manifest.json')
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'identities':identities,'whole_delta':delta,'pending_union_delta':pending200-pending40,
                     'paired_miss_sequence':pair_match,'paired':paired,
                     'reference_extra_diagnostic':result['full_reference_sequence_diagnostic']},indent=2))


if __name__=='__main__':main()
