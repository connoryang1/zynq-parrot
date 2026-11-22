#!/usr/bin/env python3
"""Prospective matched-capacity COST analysis; both full promotion gates required."""
import argparse
import copy
import json
import math
from pathlib import Path
import sys
import analyze_retained29_cost_cohort as within

p=within.promotion
require=p.require
IMAGES=('small','large')
BP='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c'
APPROVED_CAPACITY_BRIDGES={}
FIXED=dict(BP=BP,retained_sets=256,epoch_bits=8,line_bytes=64,
    l1i_bytes=32768,l1d_bytes=32768,l1_sets=64,l1_ways=8,l2_bytes=16384,
    core_hz=20000000,axi_hz=20000000,num_threads=2,num_contexts=4,
    cfg='e_bp_unicore_zynqparrot_prefetch16k_cfg',
    build_defines=dict(BP_RETAINED_BUFFER=1,BP_RETAINED_OBSERVE=1,BP_AXI_RESPONSE_DELAY=0),
    capture_masks=dict(ordinary_i=9,ordinary_d=6,ordinary_joint=15),
    source='none',kernel_nbf_sha256=p.base.NBF_SHA,application_runtime=p.APPLICATION_RUNTIME)
PRIMARY=dict(policy='ordinary-joint',mask=15,endpoint='whole',contrast='enabled_large/enabled_small',
    repeats='GM four paired repeat ratios within same indexed workload boot',
    boots='GM three boot estimates per workload/size configuration',
    configurations='equal-weight GM ten workload/size configurations',
    uncertainty='all three boot estimates and ranges; no CI/P/bootstrap')
METRICS=('enabled_large_over_small','off_large_over_small','within_small_on_over_off',
         'within_large_on_over_off','ratio_of_ratios')
DECLARATION=Path(__file__).resolve().parents[1]/'research/retained29-matched-capacity-20261121/declaration.DRAFT.json'


def schedule():
    visits=p.canonical_visits()
    entries=[dict(order=0,image='small',visit_id='pilot',cohort_index=0),
             dict(order=1,image='large',visit_id='pilot',cohort_index=0)]
    for slot,visit in enumerate(visits[1:]):
        for image in IMAGES if slot%2==0 else tuple(reversed(IMAGES)):
            entries.append(dict(order=len(entries),image=image,visit_id=visit['id'],cohort_index=slot+1))
    return entries


def validate_declaration(d,approved=False):
    require(d['schema']=='bp-retained29-matched-capacity-study-v1','new explicit capacity study')
    require(d['fixed']==FIXED and d['primary']==PRIMARY and d['schedule']==schedule(),'fixed architecture/estimator/interleaving')
    require(d['small_lines_per_side']==256 and d['small_total_payload_bytes']==32768,'full first way baseline, not absent controller')
    require(d['program_sha256']==p.cost.ELF_SHAS and d['visits_per_image']==p.canonical_visits(),'unchanged COST programs/16boot plans')
    require(d['failure_policy']=='first failed attempt stops study; no retries, subsets or winner selection','fixed failure policy')
    actual=source_hashes()
    require(set(d['sources'])==set(actual) and all(all(d['sources'][name][k]==actual[name][k] for k in ('bytes','sha256')) for name in actual),'exact new analysis source bytes')
    if not approved:
        require(d['state']=='DRAFT UNLAUNCHABLE' and d['selected_large_lines_per_side'] is None and
            d['source_capacity_bridge'] is None and d['cohorts']==dict.fromkeys(IMAGES) and d['attempt_ledger_path'] is None,
            'hardware/cohort/ledger fields pending, not fabricated')
        return
    require(d['state']=='predeclared-reviewed matched-capacity COST','DRAFT UNLAUNCHABLE')
    require(d['sources']==actual,'approved executable analysis source paths')
    n=d['selected_large_lines_per_side']
    require(type(n) is int and 256<n<8192,'balanced selected capacity within nonsaturated physical fixture bound')
    bridge_record=d['source_capacity_bridge'];bridge=within.bound_json(bridge_record)
    require(APPROVED_CAPACITY_BRIDGES.get(bridge_record['sha256'])==dict(small=256,large=n,BP=BP),'actual source/fit/correctness selection bridge not registered')
    require(bridge['schema']=='bp-retained29-capacity-defaults-only-bridge-v1' and
        bridge['state']=='PASS root-reviewed defaults-only source fit correctness clock bridge','actual reviewed bridge')
    require(bridge['fixed']==FIXED and bridge['small_lines_per_side']==256 and bridge['large_lines_per_side']==n,
        'same BP/capture/sets/epochs/ordinary geometry/clocks; capacity defaults only')
    require(bridge['allowed_changed_defines']==['BP_RETAINED_I_LINES','BP_RETAINED_D_LINES'] and
        bridge['selection_basis']=='maximum balanced routed-fit/timing/correctness before application outcomes','capacity selection not effect-driven')
    for key in ('source_diff_proof','small_fit_correctness','large_fit_correctness'):p.verify_binding(bridge[key])
    require(bridge['cohorts']==d['cohorts'],'same independently promoted per-image cohorts')
    require(p.utc(bridge['selected_utc'])<=p.utc(d['declared_utc']),'hardware selection before declaration')
    require(Path(d['attempt_ledger_path']).is_absolute() and Path(d['attempt_ledger_path']).name=='matched-capacity-attempts.json','fixed prospective global ledger')


def source_hashes():
    return {'analysis':p.binding(__file__), 'within_analysis':p.binding(within.__file__),
            'promotion_verifier':p.binding(p.__file__)}


def matched_hardware(small,large,lines):
    require(type(lines) is int and 256<lines<8192,'preselected balanced larger capacity')
    for h,n in ((small,256),(large,lines)):
        require(h['retained']==dict(i_lines=n,d_lines=n,set_log2=8),'balanced full payload capacity and same256sets')
        require(h['l1i_bytes']==h['l1d_bytes']==32768 and h['l2_bytes']==16384,'ordinary geometry; no old4KiB L2 pooling')
    a,b=copy.deepcopy(small),copy.deepcopy(large)
    for h in (a,b):
        for key in ('i_lines','d_lines'):del h['retained'][key]
    require(a==b,'hardware differs outside retained payload capacity')


def verify_study(d,study_record,gates,ledger_record):
    validate_declaration(d,approved=True)
    ledger=within.bound_json(ledger_record)
    require(ledger['schema']=='bp-retained29-matched-capacity-attempt-ledger-v1' and ledger['study']==study_record,'same source-bound study ledger')
    require(ledger_record['path']==d['attempt_ledger_path'],'fixed declared ledger path')
    require(len(ledger['entries'])==32 and all(e['state']=='PASS' for e in ledger['entries']),'all32 attempts complete; any failure/pending/subset stops study')
    require(not ledger.get('failed_attempts',[]),'earlier failed attempt forbids a passing replacement study')
    cohorts={image:within.bound_json(gates[image]['cohort']) for image in IMAGES}
    for image in IMAGES:
        require(gates[image]['cohort']==d['cohorts'][image],'exact independently promoted image cohort')
        qualification=p.physical_qualification(cohorts[image]['physical_qualification'],cohorts[image]['hardware'],cohorts[image]['artifacts'])
        clocks=within.bound_json(qualification['clock_topology'])
        require(clocks['core_hz']==clocks['axi_hz']==20000000,'same actual20MHz physical clocks, not simulation')
    matched_hardware(cohorts['small']['hardware'],cohorts['large']['hardware'],d['selected_large_lines_per_side'])
    require(cohorts['small']['program_sha256']==cohorts['large']['program_sha256']==p.cost.ELF_SHAS,'identical application ELFs')
    require(cohorts['small']['artifacts']['bit']['sha256']!=cohorts['large']['artifacts']['bit']['sha256'],'distinct fitted capacity images')
    seen=set();previous=None
    for entry,expected in zip(ledger['entries'],schedule()):
        require(all(entry[k]==v for k,v in expected.items()),'fixed global image/slot/parity order')
        image,index=entry['image'],entry['cohort_index'];gate=gates[image]
        require(entry['result']==gate['sessions'][index] and entry['boot_id']==gate['acquisition_boot_ids'][index],'actual accepted per-image result and acquisition UUID')
        require(entry['boot_id'] not in seen,'all32 actual acquisition UUIDs distinct');seen.add(entry['boot_id'])
        result=within.bound_json(entry['result'])
        start,end=p.utc(result['started_utc']),p.utc(result['release_after_recovery_utc'])
        require(p.utc(d['declared_utc'])<=start<=end and (previous is None or previous<=start),'actual interleaved chronology/recovery before next boot')
        previous=end
    return ledger


def estimate(small_boots,large_boots,large_lines):
    """Pure declared arithmetic; synthetic callers get no physical admission."""
    require(len(small_boots)==len(large_boots)==16,'both complete16boot image cohorts, no subsets')
    matched_hardware(small_boots[0]['hardware'],large_boots[0]['hardware'],large_lines)
    require(small_boots[0]['programs']==large_boots[0]['programs'],'same exact programs across images')
    require(len({b['acquisition_boot_id'] for b in small_boots+large_boots})==32,'all32 distinct actual boot clusters')
    images={name:within.estimate(boots) for name,boots in zip(IMAGES,(small_boots,large_boots))}
    paired=[];points={}
    for left,right in zip(images['small']['paired_repeats'],images['large']['paired_repeats']):
        keys=('visit_id','round','rotation','phase','workload','kind','kib','mask','policy','command_position','repeat','on_order','off_order')
        require(all(left[k]==right[k] for k in keys),'paired same indexed round/workload/size/policy/repeat/order')
        row={k:left[k] for k in keys};row['boot_ids']={image:value['boot_id'] for image,value in zip(IMAGES,(left,right))}
        row['raw']={image:{k:v for k,v in value.items() if k.endswith(('_on','_off','_resource'))} for image,value in zip(IMAGES,(left,right))}
        row['endpoints']={}
        for endpoint in within.ENDPOINTS:
            so,sf,lo,lf=(value[endpoint+'_'+side] for value,side in ((left,'on'),(left,'off'),(right,'on'),(right,'off')))
            ratios=dict(enabled_large_over_small=within.paired_ratio(lo,so),off_large_over_small=within.paired_ratio(lf,sf),
                within_small_on_over_off=within.paired_ratio(so,sf),within_large_on_over_off=within.paired_ratio(lo,lf))
            ratios['ratio_of_ratios']=ratios['within_large_on_over_off']/ratios['within_small_on_over_off'];row['endpoints'][endpoint]=ratios
            if left['phase']=='performance':
                key=(left['workload'],left['kib'],left['mask'],endpoint,left['round'])
                points.setdefault(key,[]).append(row)
        paired.append(row)
    configs=[]
    for work in p.cost.WORKLOADS:
        for kib in (32,128):
            for policy,mask in p.cost.POLICIES:
                config=dict(workload=work,kib=kib,policy=policy,mask=mask,endpoints={})
                for endpoint in within.ENDPOINTS:
                    entries=[]
                    for round_ in range(3):
                        rows=points[(work,kib,mask,endpoint,round_)]
                        require(len(rows)==4 and {r['repeat'] for r in rows}==set(range(4)),'all four paired repeats in each of three boot pairs')
                        entries.append(dict(round=round_,rotation=2*round_,boot_ids=rows[0]['boot_ids'],
                            ratios={metric:within.gm([r['endpoints'][endpoint][metric] for r in rows]) for metric in METRICS}))
                    config['endpoints'][endpoint]=dict(boots=entries,
                        ratios={metric:within.gm([b['ratios'][metric] for b in entries]) for metric in METRICS},
                        boot_ranges={metric:[min(b['ratios'][metric] for b in entries),max(b['ratios'][metric] for b in entries)] for metric in METRICS})
                configs.append(config)
    summaries=[]
    for policy,mask in p.cost.POLICIES:
        for endpoint in within.ENDPOINTS:
            ten=[row['endpoints'][endpoint] for row in configs if row['mask']==mask]
            require(len(ten)==10,'equal ten workload/size configurations')
            summaries.append(dict(policy=policy,mask=mask,endpoint=endpoint,
                ratios={metric:within.gm([x['ratios'][metric] for x in ten]) for metric in METRICS},
                role='primary capacity contrast' if mask==15 and endpoint=='whole' else 'diagnostic' if endpoint=='whole' else 'secondary'))
    return dict(primary=next(s for s in summaries if s['mask']==15 and s['endpoint']=='whole'),summaries=summaries,
        configurations=configs,paired_repeats=paired,image_estimates=images,
        counts=dict(performance_boots=30,pilot_boots=2,performance_primary_paired_repeats=120,equal_configurations=10),
        uncertainty=PRIMARY['uncertainty'],limits='Enabled large/small complete lifecycle costs; capacity changes lookup/clear/interference too. No per-application hits/occupancy, advisory-prefetch, controller-absent or simulation-to-FPGA inference.')


def analyze(study_path,study_sha,small_path,small_sha,large_path,large_sha,ledger_path,ledger_sha):
    sources_before=source_hashes()
    study_record=p.binding(study_path);require(study_record['sha256']==study_sha,'external study anchor')
    d=within.bound_json(study_record);validate_declaration(d,approved=True)
    records={};gates={}
    for image,path,sha in (('small',small_path,small_sha),('large',large_path,large_sha)):
        records[image],gates[image]=within.load_complete(path,sha)
    ledger_record=p.binding(ledger_path);require(ledger_record['sha256']==ledger_sha,'external global-ledger anchor')
    verify_study(d,study_record,gates,ledger_record)
    boots={image:within.sessions_to_boots(gates[image]) for image in IMAGES}
    estimates=estimate(boots['small'],boots['large'],d['selected_large_lines_per_side'])
    require(source_hashes()==sources_before,'analysis/verifier sources immutable')
    return dict(schema='bp-retained29-matched-capacity-analysis-v1',scope='COMPLETE_TWO_IMAGE_PHYSICAL_STUDY',
        inputs=dict(study=study_record,complete_gates=records,global_ledger=ledger_record,sources=sources_before),
        estimates=estimates)


def write_outputs(report,out):
    require(report['scope'] in ('COMPLETE_TWO_IMAGE_PHYSICAL_STUDY',within.TEST_SCOPE),'explicit admitted/test-only scope')
    out=Path(out);out.mkdir(exist_ok=False,parents=True)
    (out/'analysis.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    estimates=report['estimates'];prefix='TEST ONLY, synthetic; no physical admission. ' if report['scope']==within.TEST_SCOPE else ''
    text=[prefix+'This compares complete enabled WHOLE costs of the preselected large and256-per-side retained capacities. Both complete image cohorts, all32 boots and both pilots are required.',
        '', 'Joint15 WHOLE enabled_large/enabled_small ratio: **%.9f**.'%estimates['primary']['ratios']['enabled_large_over_small'],
        '', '| Workload | KiB | Three paired-boot enabled ratios | GM | Range |', '| --- | ---: | --- | ---: | --- |']
    config_rows=[]
    for row in estimates['configurations']:
        for endpoint,values in row['endpoints'].items():
            for metric in METRICS:
                values3=[b['ratios'][metric] for b in values['boots']]
                config_rows.append(dict(scope=report['scope'],workload=row['workload'],kib=row['kib'],mask=row['mask'],endpoint=endpoint,metric=metric,ratio=values['ratios'][metric],boot0=values3[0],boot1=values3[1],boot2=values3[2],minimum=min(values3),maximum=max(values3)))
        if row['mask']==15:
            values=row['endpoints']['whole'];metric='enabled_large_over_small'
            text.append('| %s | %s | %s | %.9f | %.9f–%.9f |'%(row['workload'],row['kib'],', '.join('%.9f'%b['ratios'][metric] for b in values['boots']),values['ratios'][metric],*values['boot_ranges'][metric]))
    text+=['','All ratios use GM4 repeats→GM3 boot pairs→equal10 configurations. Within-image on/off, ratio-of-ratios and off-large/off-small diagnose activation and cross-image baseline differences; I9/D6 are diagnostic and steady is secondary. Every raw cell, resources and order remain in per-image JSON/CSV. All three boot estimates/ranges are descriptive; no CI/P/bootstrap. Capacity can change service/clear/interference as well as retained bytes. Old2dd gives no application retained-use counts; source-none is demand capture, not advisory prefetch. No controller-absent or simulation/FPGA pooling claim.']
    (out/'RESULTS.md').write_text('\n'.join(text)+'\n')
    within.csv_write(out/'configurations.csv',config_rows,list(config_rows[0]))
    raw=[]
    for image in IMAGES:
        for cell in estimates['image_estimates'][image]['raw_cells']:
            raw.append(dict(image=image,**{k:v for k,v in cell.items() if k not in ('resource','control','prefix','replay')},resource_json=json.dumps(cell['resource'],sort_keys=True),control_json=json.dumps(cell['control'],sort_keys=True),prefix_json=json.dumps(cell['prefix'],sort_keys=True),replay_json=json.dumps(cell['replay'],sort_keys=True)))
    within.csv_write(out/'raw-cells.csv',raw,list(raw[0]))
    (out/'manifest.json').write_text(json.dumps(dict(scope=report['scope'],inputs=report['inputs'],files=[p.binding(x) for x in sorted(out.iterdir())]),indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-draft',action='store_true')
    for name in ('study','small-complete','large-complete','ledger','out'):parser.add_argument('--'+name,type=Path)
    for name in ('study-sha256','small-sha256','large-sha256','ledger-sha256'):parser.add_argument('--'+name)
    a=parser.parse_args()
    if a.check_draft:
        validate_declaration(json.loads(DECLARATION.read_text()));print('PASS DRAFT structural/source checks; UNLAUNCHABLE');return
    require(all(getattr(a,n) is not None for n in ('study','small_complete','large_complete','ledger','out','study_sha256','small_sha256','large_sha256','ledger_sha256')),'all externally anchored complete inputs required')
    write_outputs(analyze(a.study,a.study_sha256,a.small_complete,a.small_sha256,a.large_complete,a.large_sha256,a.ledger,a.ledger_sha256),a.out)


if __name__=='__main__':main()
