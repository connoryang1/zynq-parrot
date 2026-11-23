#!/usr/bin/env python3
"""Declared COST geometric hierarchy, only after the complete promotion gate."""
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"linux-tests"))

import cohort_protocol as promotion

require=promotion.require
RESOURCE=('minor_faults','major_faults','user_us','system_us','voluntary_switches','involuntary_switches')
POLICIES=promotion.cost.POLICIES
ENDPOINTS=('whole','steady')
TEST_SCOPE='TEST_ONLY_SYNTHETIC_NO_PHYSICAL_ADMISSION'
ROOT=promotion.base.ROOT
DECLARATION=ROOT/'research/retained29-cost-cohort-20261121/cohort-draft.json'
PLAN_SOURCE=ROOT/'research/retained29-cost-cohort-20261121/validate.py'
require(promotion.binding(DECLARATION)['sha256']=='a7cfd821be032dac5f42cd25b2d6e62e4df7a5ed591b1f2ba77585bf5c84eb9c','frozen declaration bytes')
require(promotion.binding(PLAN_SOURCE)['sha256']=='68b0b412b705c09636248f26560886e6f8f38fd535015bcf375f7bdfa0858185','frozen primary-plan source bytes')
spec=importlib.util.spec_from_file_location('declared_cost_plan',PLAN_SOURCE)
plan_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(plan_module)
PRIMARY=plan_module.PRIMARY


def bound_json(record):
    raw=Path(record['path']).read_bytes()
    require(len(raw)==record['bytes'] and hashlib.sha256(raw).hexdigest()==record['sha256'],'bound JSON changed: '+record['path'])
    return json.loads(raw)


def load_complete(path,expected_sha):
    record=promotion.binding(path)
    require(record['sha256']==expected_sha,'external complete-promotion SHA mismatch')
    gate=bound_json(record)
    require(gate.get('state')=='PASS complete fixed COST cohort admitted for primary analysis'
        and gate.get('primary_analysis_ready') is True,'only complete promotion gate admitted')
    # Rebind/reparse all16 actual sessions, source/hardware qualification, UUIDs,
    # failed-attempt ledger and recovery. No alternate or passing-subset input.
    require(gate==promotion.verify_complete(gate['cohort'],gate['ledger']),'complete promotion gate changed')
    return record,gate


def positive(value):
    require(type(value) is int and 0<value<=2**64-1,'positive unsigned64 cycle count')
    return value


def gm(values):
    require(values and all(math.isfinite(x) and x>0 for x in values),'nonempty positive finite geometric values')
    return math.exp(math.fsum(math.log(x) for x in values)/len(values))


def gm_cycles(values):return math.exp(math.fsum(math.log(positive(x)) for x in values)/len(values))
def paired_ratio(on,off):return math.exp(math.log(positive(on))-math.log(positive(off)))


def sessions_to_boots(gate):
    require(len(gate['sessions'])==len(gate['acquisition_boot_ids'])==16,'pilot+15 complete sessions')
    boots=[]
    for index,(record,identity,visit) in enumerate(zip(gate['sessions'],gate['acquisition_boot_ids'],promotion.canonical_visits())):
        result=bound_json(record)
        require(result['plan']==visit['plan'] and result['visit_id']==visit['id'],'exact fixed run/plan identity')
        boots.append(dict(visit_id=visit['id'],boot_order=index,round=visit['round'],rotation=visit['plan']['rotation'],
            acquisition_boot_id=identity,role=visit['plan']['role'],workload=visit['plan']['workload'],
            started_utc=result['started_utc'],released_utc=result['release_after_recovery_utc'],
            session=record,hardware=result['hardware'],artifacts=result['artifacts'],programs=result['programs'],
            commands=result['guest']['commands']))
    return boots


def estimate(boots):
    """Pure mathematics over all fixed units; tests may supply synthetic boots."""
    require(len(boots)==16,'complete pilot+15 boots required; no subsets')
    require(len({b['acquisition_boot_id'] for b in boots})==16,'distinct actual boot clusters')
    require(all(b['hardware']==boots[0]['hardware'] and b['artifacts']==boots[0]['artifacts'] and b['programs']==boots[0]['programs'] for b in boots),'no cross-image/runtime program pooling')
    require(boots[0]['hardware']['l1i_bytes']==boots[0]['hardware']['l1d_bytes']==32768 and boots[0]['hardware']['l2_bytes']==16384,'ordinary geometry16KiBL2; no old4KiB pooling')
    declaration=json.loads(DECLARATION.read_text())
    require(declaration['primary']==PRIMARY,'unchanged declared primary hierarchy')
    cells=[];pairs=[];clusters=[]
    configs={(w,k,m,e):[] for w in promotion.cost.WORKLOADS for k in (32,128) for _,m in POLICIES for e in ENDPOINTS}
    for b,visit in zip(boots,promotion.canonical_visits()):
        require(b['visit_id']==visit['id'],'fixed boot order')
        require(b['boot_order']==visit['order'] and b['round']==visit['round'] and b['rotation']==visit['plan']['rotation']
            and b['role']==visit['plan']['role'] and b['workload']==visit['plan']['workload'],'fixed boot/round/role metadata')
        plan=visit['plan'];require(len(b['commands'])==6,'all six commands per boot')
        cluster=dict(visit_id=b['visit_id'],acquisition_boot_id=b['acquisition_boot_id'],boot_order=b['boot_order'],
            round=b['round'],rotation=b['rotation'],workload=b['workload'],role=b['role'],
            started_utc=b['started_utc'],released_utc=b['released_utc'],session=b['session'],members=[])
        for position,(command,expected) in enumerate(zip(b['commands'],plan['cases'])):
            require(command['case']==expected and command['complete_cells']==2*plan['repeats'] and len(command['cells'])==2*plan['repeats'],'exact command/cell cohort')
            case=command['case'];member=dict(case_id=case['id'],kind=case['kind'],workload=case['workload'],kib=case['kib'],mask=case['mask'],
                policy=case['policy'],command_position=position,pairs=[],endpoints={})
            for repeat in range(plan['repeats']):
                both=command['cells'][2*repeat:2*repeat+2]
                for order,c in enumerate(both):
                    require((c['repeat'],c['order'],c['enabled'])==(repeat,order,(repeat&1)^order),'fixed ABBA cells')
                    positive(c['whole']);positive(c['steady']);require(c['whole']>=c['steady'],'complete lifecycle includes steady')
                    require(set(c['resource'])==set(RESOURCE) and all(type(c['resource'][n]) is int and c['resource'][n]>=0 for n in RESOURCE),'complete resource counters')
                    cells.append(dict(visit_id=b['visit_id'],boot_id=b['acquisition_boot_id'],boot_order=b['boot_order'],round=b['round'],rotation=b['rotation'],
                        phase='pilot-functional-only' if b['boot_order']==0 else 'performance',workload=case['workload'],kind=case['kind'],kib=case['kib'],policy=case['policy'],mask=case['mask'],
                        command_position=position,repeat=repeat,cell_order=order,enabled=c['enabled'],loops=plan['loops'],warmup=plan['warmup'],
                        whole=c['whole'],steady=c['steady'],resource=c['resource'],control=c['control'],prefix=c['prefix'],replay=c['replay']))
                on=next(c for c in both if c['enabled']);off=next(c for c in both if not c['enabled'])
                pair=dict(visit_id=b['visit_id'],boot_id=b['acquisition_boot_id'],boot_order=b['boot_order'],round=b['round'],rotation=b['rotation'],
                    phase='pilot-functional-only' if b['boot_order']==0 else 'performance',workload=case['workload'],kind=case['kind'],kib=case['kib'],mask=case['mask'],policy=case['policy'],
                    command_position=position,repeat=repeat,on_order=on['order'],off_order=off['order'],
                    whole_on=on['whole'],whole_off=off['whole'],steady_on=on['steady'],steady_off=off['steady'],
                    whole_ratio=paired_ratio(on['whole'],off['whole']),steady_ratio=paired_ratio(on['steady'],off['steady']),
                    on_resource=on['resource'],off_resource=off['resource'])
                pairs.append(pair);member['pairs'].append(pair)
            for endpoint in ENDPOINTS:
                on=[v[endpoint+'_on'] for v in member['pairs']];off=[v[endpoint+'_off'] for v in member['pairs']]
                point=gm([v[endpoint+'_ratio'] for v in member['pairs']])
                member['endpoints'][endpoint]=dict(ratio=point,on_cycles=on,off_cycles=off,on_geomean=gm_cycles(on),off_geomean=gm_cycles(off),
                    on_sum=sum(on),off_sum=sum(off),all_cell_sum=sum(on)+sum(off))
                if b['boot_order']:
                    configs[(case['workload'],case['kib'],case['mask'],endpoint)].append(dict(
                        visit_id=b['visit_id'],boot_id=b['acquisition_boot_id'],round=b['round'],rotation=b['rotation'],boot_order=b['boot_order'],
                        command_position=position,**member['endpoints'][endpoint]))
            cluster['members'].append(member)
        clusters.append(cluster)
    configuration=[]
    for w in promotion.cost.WORKLOADS:
        for kib in (32,128):
            for policy,mask in POLICIES:
                row=dict(workload=w,kib=kib,policy=policy,mask=mask,endpoints={})
                for endpoint in ENDPOINTS:
                    entries=configs[(w,kib,mask,endpoint)]
                    require(len(entries)==3 and [e['round'] for e in entries]==[0,1,2] and len({e['boot_id'] for e in entries})==3,'all3 actual boot estimates per configuration')
                    points=[e['ratio'] for e in entries]
                    row['endpoints'][endpoint]=dict(ratio=gm(points),boots=entries,boot_ratio_range=[min(points),max(points)])
                configuration.append(row)
    summaries=[]
    for policy,mask in POLICIES:
        for endpoint in ENDPOINTS:
            ten=[r['endpoints'][endpoint]['ratio'] for r in configuration if r['mask']==mask]
            require(len(ten)==10,'exact equal10 workload/size configurations')
            summaries.append(dict(policy=policy,mask=mask,endpoint=endpoint,ratio=gm(ten),configuration_ratios=ten,
                role='primary' if mask==15 and endpoint=='whole' else 'diagnostic' if endpoint=='whole' else 'secondary'))
    primary=next(r for r in summaries if r['role']=='primary')
    return dict(primary=primary,summaries=summaries,configurations=configuration,boot_clusters=clusters,
        raw_cells=cells,paired_repeats=pairs,counts=dict(performance_boots=15,pilot_boots=1,configurations=10,
            performance_cells=sum(c['phase']=='performance' for c in cells),performance_pairs=sum(c['phase']=='performance' for c in pairs),
            primary_joint_pairs=sum(c['phase']=='performance' and c['mask']==15 for c in pairs)),
        uncertainty='All three boot estimates and min/max ranges only. No bootstrap, confidence intervals or P values are declared or computed.',
        cluster_unit='One PS boot per workload contains both sizes and all three masks; repeat cells are paired observations, not independent boots.')


def csv_write(path,rows,fields):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for row in rows:writer.writerow(row)


def write_outputs(report,out):
    require(report['scope'] in (TEST_SCOPE,'COMPLETE_PROMOTION_ADMITTED_FPGA_COHORT'),'explicit physical-admitted or test-only export scope')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    prefix='TEST ONLY — synthetic, no physical admission. ' if report['scope']==TEST_SCOPE else ''
    analysis=report['estimates'];point=analysis['primary']['ratio']
    text=[prefix+'This reports the fixed complete-COST cohort estimator and preserves all raw paired costs. '
          'Joint15 WHOLE is primary; I9/D6 are diagnostics and steady timing is secondary.',
          '', 'Joint15 WHOLE on/off geometric ratio: **%.9f** (cost change **%+.6f%%**).'%(point,100*(point-1)),
          'Each configuration has three independent workload boots; rows below show their actual estimates and range, not confidence intervals.',
          '', '| Workload | KiB | Three boot WHOLE ratios | Declared GM | Boot min–max |',
          '| --- | ---: | --- | ---: | --- |']
    for row in analysis['configurations']:
        if row['mask']!=15:continue
        endpoint=row['endpoints']['whole'];text.append('| %s | %d | %s | %.9f | %.9f–%.9f |'%(row['workload'],row['kib'],
            ', '.join('%.9f'%b['ratio'] for b in endpoint['boots']),endpoint['ratio'],*endpoint['boot_ratio_range']))
    text += ['', '| Policy | Endpoint | Role | Equal-ten ratio |', '| --- | --- | --- | ---: |']
    for summary in analysis['summaries']:
        text.append('| %s | %s | %s | %.9f |'%(summary['policy'],summary['endpoint'],summary['role'],summary['ratio']))
    text += ['', 'A ratio below one means fewer on cycles; neutral and regressing configurations remain included. '
        'The hierarchy is four paired repeat ratios per boot, three boots per configuration, then equal weight across ten workload × size configurations. '
        'Boot clusters retain both footprints and all masks; raw on/off cycles, resources and order are in CSV/JSON.',
        '', 'This estimates incremental demand-retention activation/lifecycle cost on one hardware image. Common maintenance and ordinary fences remain; '
        'crossover cache/allocator carryover is retained. Old2dd observes no per-application retained hits or occupancy. '
        'Declared control writes are source telemetry; no advisory-prefetch, controller-absent or simulation-to-FPGA claim follows.',
        '', 'Complete-gate SHA: `'+report['inputs'].get('complete_gate',{}).get('sha256','TEST_ONLY-no-physical-admission')+'`. '
        'Full input/source/run identities are bound in `analysis.json` and `manifest.json`.']
    (out/'RESULTS.md').write_text('\n'.join(text)+'\n')
    (out/'analysis.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    cellrows=[]
    for value in analysis['raw_cells']:
        row={k:v for k,v in value.items() if k not in ('resource','control','prefix','replay')}
        row.update(value['resource']);row.update({k+'_json':json.dumps(value[k],sort_keys=True,separators=(',',':')) for k in ('control','prefix','replay')});cellrows.append(dict(scope=report['scope'],**row))
    csv_write(out/'cells.csv',cellrows,list(cellrows[0]))
    pairrows=[]
    for value in analysis['paired_repeats']:
        row={k:v for k,v in value.items() if k not in ('on_resource','off_resource')}
        for side in ('on','off'):row.update({side+'_'+k:value[side+'_resource'][k] for k in RESOURCE})
        pairrows.append(dict(scope=report['scope'],**row))
    csv_write(out/'paired-repeats.csv',pairrows,list(pairrows[0]))
    rows=[]
    for value in analysis['configurations']:
        for endpoint,data in value['endpoints'].items():
            rows.append(dict(scope=report['scope'],workload=value['workload'],kib=value['kib'],mask=value['mask'],policy=value['policy'],endpoint=endpoint,
                ratio=data['ratio'],boot0=data['boots'][0]['ratio'],boot1=data['boots'][1]['ratio'],boot2=data['boots'][2]['ratio'],
                boot_min=data['boot_ratio_range'][0],boot_max=data['boot_ratio_range'][1]))
    csv_write(out/'configurations.csv',rows,list(rows[0]))
    files=[promotion.binding(p) for p in sorted(out.iterdir()) if p.is_file()]
    (out/'manifest.json').write_text(json.dumps(dict(scope=report['scope'],inputs=report['inputs'],files=files),indent=2,sort_keys=True)+'\n')


def analyze(path,expected_sha):
    before=promotion.binding(__file__);record,gate=load_complete(path,expected_sha)
    boots=sessions_to_boots(gate);cohort=bound_json(gate['cohort'])
    report=dict(schema='bp-retained29-cost-analysis-v1',scope='COMPLETE_PROMOTION_ADMITTED_FPGA_COHORT',
        declaration=PRIMARY,inputs=dict(complete_gate=record,promotion_cohort=gate['cohort'],ledger=gate['ledger'],
            sessions=gate['sessions'],analysis_source=before,promotion_verifier=promotion.binding(promotion.__file__),analysis_plan=promotion.binding(PLAN_SOURCE),frozen_declaration=promotion.binding(DECLARATION)),
        identities=dict(hardware=boots[0]['hardware'],artifacts=boots[0]['artifacts'],programs=boots[0]['programs'],
            application_runtime=promotion.APPLICATION_RUNTIME,physical_qualification=cohort['physical_qualification']),
        analysis_environment=dict(python=sys.version.split()[0],platform=sys.platform,math='stdlib log/exp/fsum; no statistical resampling'),
        estimates=estimate(boots))
    require(promotion.binding(__file__)==before,'analysis source immutable')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--complete-gate',required=True,type=Path)
    parser.add_argument('--complete-sha256',required=True)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();require(not args.out.exists(),'new analysis output only')
    report=analyze(args.complete_gate,args.complete_sha256)
    write_outputs(report,args.out)
    print(args.out/'manifest.json')


if __name__=='__main__':main()
