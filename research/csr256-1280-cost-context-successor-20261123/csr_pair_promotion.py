"""Promotion gates for the fixed COST cohort; physical/runtime approval starts empty."""
import json
from pathlib import Path
import re
import uuid

import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'linux-tests'))
import retained29_cost_protocol as cost
import retained29_safe_session as safe
import csr_pair_context as context

base=cost.base
require,binding,verify_binding,utc=cost.require,cost.binding,cost.verify_binding,cost.utc
SCHEMA='bp-retained29-promoted-COST-session-v1'
ADMISSION_SCHEMA='bp-retained29-promoted-COST-admission-v1'
COHORT_SCHEMA='bp-retained29-reviewed-COST-cohort-v1'
SUCCESS_STATE='PASS-complete-recovered-promoted-COST-session'
# A reviewed source checkpoint must register actual closed physical evidence.
# A pending/private observer build is not an executed runtime qualification.
APPROVED_PHYSICAL_QUALIFICATIONS={}
APPROVED_OBSERVER_RUNTIMES={}
APPLICATION_RUNTIME=dict(profile='old2dd-no-application-gp0-v1',runner_sha256=base.RUNNER_SHA,
                         helper_sha256=base.HELPER_SHA,application_gp0=False)
SOURCE_FILES=tuple(dict.fromkeys((*cost.SOURCE_FILES,
    'linux-tests/retained29_cost_cohort_protocol.py','linux-tests/run_retained29_cost_cohort.py',
    *(str(Path(__file__).resolve().parent.relative_to(base.ROOT)/n) for n in context.SOURCE_NAMES))))
ORDERS=(('scan','lookup','parse','chase','regex'),('regex','chase','parse','lookup','scan'),
        ('lookup','chase','scan','regex','parse'))


def source_hashes():return {n:binding(base.ROOT/n)['sha256'] for n in SOURCE_FILES}
def bound_sources(a):return a['sources']
def verify_sources(a):require(a['sources']==source_hashes(),'promotion source drift');cost.verify_sources(a['session'])

def canonical_visits():
    result=[dict(id='pilot',order=0,round=None,independent_boot=True,plan=cost.plan_for('cost-pilot-functional'))]
    for r,order in enumerate(ORDERS):
        for workload in order:
            result.append(dict(id='r%d-%s'%(r,workload),order=len(result),round=r,independent_boot=True,
                plan=cost.plan_for('cost-performance-acquisition',workload,2*r)))
    return result


def verify_artifacts(a):
    cost.verify_artifacts(a['session']);verify_binding(a['cohort'])
    for row in a['prior_results']:verify_binding(row)


def physical_qualification(record,hardware,artifacts):
    require(record is not None,'actual physical capacity/source/clock qualification missing')
    verify_binding(record);q=json.loads(Path(record['path']).read_text())
    bit=artifacts['bit']['sha256']
    require(APPROVED_PHYSICAL_QUALIFICATIONS.get(bit)==record['sha256'],'physical-image allowlist empty or wrong qualification')
    require(q['schema']=='bp-retained29-physical-capacity-qualification-v1' and q['state']=='PASS root-reviewed actual physical capacity/source/clock qualification','physical qualification not complete')
    utc(q['closed_utc'])
    require(q['platform']=='FPGA' and q['hardware']==hardware and q['artifacts']==artifacts,'exact physical image/geometry/artifacts')
    runtime=q['observer_runtime']
    require(runtime is not None and runtime['profile']!=APPLICATION_RUNTIME['profile'] and runtime['runner_sha256']!=base.RUNNER_SHA,
            'old2dd application runner cannot claim observer GP0')
    expected=APPROVED_OBSERVER_RUNTIMES.get(runtime['profile'])
    require(expected is not None and expected=={k:runtime[k] for k in ('runner_sha256','source_proof','execution_proof')},
            'actual observer profile/source/execution approval pending')
    for key in ('source_proof','execution_proof'):verify_binding(runtime[key])
    for key in ('canonical_fullcore','source_bridge','clock_topology'):verify_binding(q[key])
    clocks=json.loads(Path(q['clock_topology']['path']).read_text())
    require(clocks['scope']=='actual-FPGA-clock-topology' and clocks['bit_sha256']==bit
        and type(clocks['core_hz']) is int and clocks['core_hz']>0 and type(clocks['axi_hz']) is int and clocks['axi_hz']>0,
        'actual FPGA clocks, not model timing/calibration')
    require(clocks['l1i_bytes']==clocks['l1d_bytes']==32768 and clocks['l1_sets']==64 and clocks['l1_ways']==8
        and clocks['line_bytes']==64 and clocks['l2_bytes']==hardware['l2_bytes']==16384,'ordinary geometry/source qualification')
    rows=q['cases'];require([r['role'] for r in rows]==['d-enabled','d-off','i-enabled'],'all three physical capacity fixtures')
    for row in rows:
        lane=row['role'][0];lines=hardware['retained'][lane+'_lines']
        expected=[0,lines,0,lines,0,8*lines] if lane=='d' else [lines,0,lines,0,8*lines,0]
        if row['role']=='d-off':expected=[0]*6
        require(0<lines and 8*lines<65535 and row['lines']==lines and row['counter_words']==expected,'full-capacity actual nonsaturated GP0 words')
        require(row['complete'] is True and row['all_payloads_checked'] is True and row['observer_stable'] is True
            and row['saturated'] is False and row['recovery_verified'] is True,'complete checked/stable physical fixture')
        require(row['primary_use_rejected']==(row['role']=='d-off'),'negative D-off rejects positive retained-use claim')
        for key in ('receipt','fixture','checker'):verify_binding(row[key])
    context.physical_context(q, hardware, artifacts)
    return q


def cohort_record(a):
    verify_binding(a['cohort']);record=json.loads(Path(a['cohort']['path']).read_text())
    inner=a['session']
    require(record['schema']==COHORT_SCHEMA and record['state']=='predeclared-reviewed','DRAFT promotion cohort cannot execute')
    utc(record['declared_utc'])
    require(record['sources']==a['sources']==source_hashes() and record['cost_sources']==inner['sources'], 'exact promotion and frozen COST source maps')
    require(record['program_sha256']==cost.ELF_SHAS and record['artifacts']==inner['artifacts'] and record['hardware']==inner['hardware'],'same-image COST cohort/programs')
    require(record['visits']==canonical_visits(),'fixed pilot plus15 slots/order/rotations')
    require(record['application_runtime']==APPLICATION_RUNTIME,'fixed application old2dd profile; observer is separate')
    require(record['legacy_cohort']==inner['cohort_record'],'same unchanged COST declaration')
    verify_binding(record['legacy_cohort']);legacy=json.loads(Path(record['legacy_cohort']['path']).read_text())
    require(legacy['visits']==record['visits'],'legacy declaration cannot change slots/order')
    path=Path(record['ledger_path']);require(path.name=='acquisition-ledger.json' and path.is_absolute(),'explicit fixed cohort ledger')
    qualification=physical_qualification(record['physical_qualification'],inner['hardware'],inner['artifacts'])
    require(utc(qualification['closed_utc'])<=utc(record['declared_utc']),'actual physical prerequisite closes before promotion declaration')
    return record


def static_admission(a):
    require(a.get('schema')==ADMISSION_SCHEMA and a.get('state')=='bound-reviewed-promoted-COST','DRAFT UNLAUNCHABLE promoted COST')
    verify_sources(a);verify_artifacts(a)
    core=cost.validate_admission(a['session']);record=cohort_record(a)
    selected=[v for v in record['visits'] if v['id']==a['session']['visit_id']]
    require(len(selected)==1 and selected[0]['plan']==a['session']['plan'],'exact promoted visit')
    require(type(a['prior_results']) is list and len(a['prior_results'])==selected[0]['order'],'complete prior-slot prefix')
    return core,record,selected[0]


def boot_id(result):
    logs=result['operation_logs']
    names=[n for n in logs if re.fullmatch(r'[0-9]{4}-remote-identity\.log',n)]
    require(len(names)==1,'unique actual acquisition identity log')
    name='%04d-guard-probe.log'%(int(names[0][:4])+1)
    require(name in logs,'actual acquisition guard immediately follows identity')
    verify_binding(logs[names[0]]);verify_binding(logs[name])
    raw=json.loads(Path(logs[name]['path']).read_text());safe.guard.idle(raw,base.RUNNER_SHA)
    value=raw['boot_id']
    require(str(uuid.UUID(value))==value,'canonical actual PS boot UUID')
    return value


def validate_fresh_boot(raw,previous):
    safe.guard.idle(raw,base.RUNNER_SHA);value=raw['boot_id']
    require(str(uuid.UUID(value))==value and value not in previous,'reused/noncanonical acquisition PS boot UUID')
    return value


def verify_session(record,cohort_binding,accepted):
    verify_binding(record);r=json.loads(Path(record['path']).read_text())
    require(r.get('schema')==SCHEMA and r.get('state')==SUCCESS_STATE and 'error' not in r,'earlier failed/incomplete attempt stops cohort')
    require(r.get('safe_engine_schema')==safe.ENGINE_SCHEMA and r.get('safe_recovery_verified') is True
        and r.get('recovery')=='complete before reservation release' and r.get('guest_boots')==1
        and r.get('performance_accepted') is False,'actual safe complete session/recovery')
    a=r['supervisor_admission'];core,cohort,visit=static_admission(a)
    require(a['cohort']==cohort_binding and visit['order']==len(accepted) and a['prior_results']==[x['record'] for x in accepted],
            'exact prior-slot acceptance and same cohort')
    inner=a['session'];require(r['admission']==core and r['supervisor_sources']==a['sources'],'actual core/source snapshot')
    for key,value in result_metadata(a,core).items():require(r[key]==value,'result promotion metadata '+key)
    verify_binding(r['supervisor_admission_record'])
    require(json.loads(Path(r['supervisor_admission_record']['path']).read_text())==a,'actual promoted input binding')
    for name,sha in a['sources'].items():
        require(binding(Path(record['path']).parent/'host-sources'/name)['sha256']==sha,'actual frozen host source snapshot')
    guest=r['guest'];require(guest['runner_exit']==guest['guest_exit']==0 and guest['runner_signal'] is None
        and guest['shell_return'] is True and guest['executed_case_ids']==[c['id'] for c in inner['plan']['cases']], 'all six commands returned normally')
    verify_binding(guest['console']);parsed=cost.complete_console(Path(guest['console']['path']).read_text(),inner)
    require(all(guest[key]==value for key,value in parsed.items()),'all WHOLE/control/resource/terminal rows reparsed')
    cost.acquisition_ready(inner,r['started_utc'])
    require(utc(cohort['declared_utc'])<=utc(r['started_utc'])<=utc(r['release_after_recovery_utc'])
        and r['release_after_recovery_utc']==r['reservation_release_utc'],'actual declaration/acquisition/recovery chronology')
    if accepted:require(utc(accepted[-1]['result']['release_after_recovery_utc'])<=utc(r['started_utc']),'nonoverlapping prior slot completion')
    for row in r['operation_logs'].values():verify_binding(row)
    verify_binding(r['operation_journal']);publication=json.loads(Path(r['operation_journal']['path']).read_text())
    require(publication['state']=='verified old2dd/helper/overlay/operating recovery' and publication['label']=='final'
        and publication['power_pending'] is None and publication['own_guest'] is None,'actual final recovered inventory/publication')
    value=boot_id(r);require(value not in {x['boot_id'] for x in accepted},'reused actual acquisition UUID')
    return dict(record=record,result=r,boot_id=value,visit=visit)


def verify_prefix(a):
    accepted=[]
    for record in a['prior_results']:accepted.append(verify_session(record,a['cohort'],accepted))
    return accepted


def validate_admission(a):
    core,record,visit=static_admission(a);verify_prefix(a)
    return core


def acquisition_ready(a,at):
    cost.acquisition_ready(a['session'],at)
    _,cohort,visit=static_admission(a);previous=verify_prefix(a)
    require(utc(cohort['declared_utc'])<=utc(at),'promotion declaration before acquisition')
    if previous:require(utc(previous[-1]['result']['release_after_recovery_utc'])<=utc(at),'previous slot complete before next acquisition')


def result_metadata(a,core):
    return dict(cost.result_metadata(a['session'],core),promotion_cohort=a['cohort'],application_runtime=APPLICATION_RUNTIME)


def verify_complete(cohort_binding,ledger_record):
    """The sole primary-admission gate; it computes no application effects."""
    verify_binding(cohort_binding);verify_binding(ledger_record)
    ledger=json.loads(Path(ledger_record['path']).read_text())
    require(ledger['schema']=='bp-retained29-cost-acquisition-ledger-v1' and ledger['cohort']==cohort_binding,'same actual acquisition ledger')
    require(len(ledger['entries'])==16 and all(e['state']=='PASS' for e in ledger['entries']),'all16 attempted slots complete; failures/subsets forbidden')
    accepted=[]
    for n,e in enumerate(ledger['entries']):
        require(e['order']==n and e['id']==canonical_visits()[n]['id'],'actual ledger slot order')
        item=verify_session(e['result'],cohort_binding,accepted)
        require(item['boot_id']==e['boot_id'],'ledger actual acquisition UUID')
        accepted.append(item)
    require(len({r['boot_id'] for r in accepted})==16,'separate pilot and15 actual independent acquisition boots')
    return dict(state='PASS complete fixed COST cohort admitted for primary analysis',primary_analysis_ready=True,
        cohort=cohort_binding,ledger=ledger_record,sessions=[r['record'] for r in accepted],
        acquisition_boot_ids=[r['boot_id'] for r in accepted],performance_boots=15,pilot_boots=1,
        primary='WHOLE',secondary='steady',effect_selection='none',
        limits='Same-image incremental demand-retention costs; repeated crossover carryover; no application GP0 or advisory-prefetch claim.')
