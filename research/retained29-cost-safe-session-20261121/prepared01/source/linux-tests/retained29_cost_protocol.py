"""Distinct COST application contract; old matched-controller parser unchanged; no board actions or effects selection."""
from datetime import datetime
import json
from pathlib import Path
import re

import retained29_protocol as base
import run_retained29_session_v2 as stage_client
import retained29_safe_functional_protocol as safe_functional

SCHEMA = 'bp-retained29-cost-application-session-v1'
PLAN_SCHEMA = 'bp-retained29-cost-application-plan-v1'
ROLES = ('cost-pilot-functional', 'cost-performance-acquisition')
WORKLOADS = ('scan', 'lookup', 'parse', 'chase', 'regex')
POLICIES = (('ordinary-i', 9), ('ordinary-d', 6), ('ordinary-joint', 15))
ELF_SHAS = dict(plain='770bbfdb7ee5e92ce78fdf53bd029ebfe9c68586870c80946f7dc1b2a09e31b1',
    regex='e1693d512042779b5496f755d67377681d35926ffbb46e69ca5ff7cc0998969e',probe=base.ELF_SHAS['probe-present'])
GUEST=dict(plain='/tmp/bp-retained29-cost-plain',regex='/tmp/bp-retained29-cost-regex',probe='/tmp/bp-retained29-cost-probe')
import retained29_application_protocol as original
FROZEN=original.SOURCE_FILES
SOURCE_FILES=tuple(dict.fromkeys((*FROZEN,*safe_functional.SOURCE_FILES,
    'linux-tests/scheduler_retained29_cost_benchmark.c','linux-tests/scheduler_retained29_regex_cost_benchmark.c',
    'linux-tests/retained29_cost_protocol.py','linux-tests/run_retained29_cost_session.py')))
PREPARATION_SHA='8f185dfcfe41a7b4274387c9a1eabe525603680f7b03f8bf638cb1090e5a9a41'
SUCCESS_STATE='PASS-complete-recovered-COST-application-session'
require,binding,verify_binding=base.require,base.binding,base.verify_binding


def source_hashes():return {name:binding(base.ROOT/name)['sha256'] for name in SOURCE_FILES}


def utc(value):
    result=datetime.fromisoformat(value)
    require(result.tzinfo is not None and result.utcoffset().total_seconds()==0,'UTC timestamp required')
    return result


def plan_for(role, workload=None, rotation=0):
    require(role in ROLES and type(rotation) is int and 0<=rotation<6,'application role/rotation')
    if role=='cost-pilot-functional':
        require(workload is None,'pilot has fixed lookup and regex workloads')
        loops,repeats,warmup=8,2,4
        inputs=(('lookup',32),('regex',32))
    else:
        require(workload in WORKLOADS,'one declared performance workload')
        loops,repeats,warmup=256,4,16
        inputs=((workload,32),(workload,128))
    cases=[]
    for work,kib in inputs:
        kind='regex' if work=='regex' else 'plain'
        for policy,mask in POLICIES:
            cases.append(dict(id='%s-%d-%s'%(work,kib,policy),kind=kind,workload=work,kib=kib,
                              policy=policy,mask=mask))
    cases=cases[rotation:]+cases[:rotation]
    return dict(role=role,workload=workload,rotation=rotation,loops=loops,repeats=repeats,warmup=warmup,
                sync='futex',profile='plain',advisory_source='none',cases=cases)


def validate_plan(plan):
    require(all(type(plan.get(k)) is int for k in ('rotation','loops','repeats','warmup')),'canonical plan integer types')
    require(type(plan.get('cases')) is list and all(type(c) is dict and type(c.get('kib')) is int
            and type(c.get('mask')) is int for c in plan['cases']),'canonical case integer types')
    require(plan==plan_for(plan.get('role'),plan.get('workload'),plan.get('rotation')),'noncanonical cohort plan')
    return plan


def argv_for(plan, case):
    require(case in plan['cases'],'case outside declared plan')
    return [GUEST[case['kind']],str(plan['loops']),str(plan['repeats']),case['policy'],str(plan['warmup']),
            'futex','plain',str(case['kib']),case['workload'],'none']


def begin(case):return 'RETAINED29_COST_APP_BEGIN case='+case['id']+' kind='+case['kind']


def command(plan,case):
    # All text comes from canonical enum/integer fields; no free shell text.
    return ('echo '+begin(case)+'; '+' '.join(argv_for(plan,case))+
            '; r29a_rc=$?; echo RETAINED29_COST_APP_EXIT case='+case['id']+' rc=$r29a_rc')


def probe_command():
    return ('echo RETAINED29_COST_APP_PROBE_BEGIN; '+GUEST['probe']+
            ' present; r29a_rc=$?; echo RETAINED29_COST_APP_EXIT case=probe rc=$r29a_rc')


def session_begin(plan):
    return ('RETAINED29_COST_APP_SESSION_BEGIN role='+plan['role']+' rotation='+str(plan['rotation'])+' commands=6')


def transfer_commands(a,kind):
    program=a['programs'][kind]
    result=base.transport.validate_transfer(Path(program['transfer']['path']),program['elf']['sha256'])
    require(result is None,'wire transfer required; embedded/alternate commands unsupported')
    return [line.replace(base.transport.GUEST_ELF,GUEST[kind])
            for line in Path(program['transfer']['path']).read_text().splitlines()]


def bound_sources(a):return a['sources']
def verify_sources(a):require(a['sources']==source_hashes(),'COST supervisor/source drift')


def verify_artifacts(a):
    for record in a['artifacts'].values():verify_binding(record)
    for program in a['programs'].values():
        for record in program.values():verify_binding(record)
    for key in ('capability_gate','functional_gate','stage_admission','plan_record','cohort_record','program_preparation'):verify_binding(a[key])


def prior_capability(a):
    gate=safe_functional.verify_result(a['capability_gate'],'probe-present')
    fixed=safe_functional.verify_result(a['functional_gate'],'benchmark-functional')
    require(fixed['admission']['capability_gate']==a['capability_gate'] and utc(fixed['started_utc'])>=utc(gate['release_after_recovery_utc']),'safe present then unchanged fixed functional')
    require(gate['hardware']==fixed['hardware']==a['hardware'],'safe prerequisite hardware')
    for key,value in a['artifacts'].items():
        require(gate['artifacts'][key]==fixed['artifacts'][key]==value,'safe prerequisite exact '+key)
    verify_binding(a['stage_admission']);_,core=stage_client.validate_outer(a['stage_admission']['path'])
    require(core==gate['admission'],'exact already-qualified present staging core')
    return gate,core


def validate_programs(a):
    verify_binding(a['program_preparation']);require(a['program_preparation']['sha256']==PREPARATION_SHA,'fixed COST accepted-runtime/source/link preparation')
    proof=json.loads(Path(a['program_preparation']['path']).read_text())
    require(proof['state']=='PASS source-preserving host control-cost/lifecycle and RV64 accepted-runtime preparation only'
        and proof['legacy_sources_unchanged'] is True and proof['target_executions']==0,'truthful preparation scope')
    require(set(a['programs'])==set(ELF_SHAS),'actual probe and both COST programs')
    for kind,program in a['programs'].items():
        require(set(program)=={'elf','transfer'},'program bindings')
        for record in program.values():verify_binding(record)
        require(program['elf']['sha256']==ELF_SHAS[kind],'fixed COST ELF '+kind);transfer_commands(a,kind)
        if kind!='probe':require(program=={key:proof['programs'][kind][key] for key in ('elf','transfer')},'exact compiled COST program/transfer')


def validate_admission(a):
    require(a.get('schema')==SCHEMA and a.get('state')=='bound-reviewed-COST-session','DRAFT UNLAUNCHABLE COST session')
    require(not a.get('unlaunchable_reasons'),'unresolved COST blockers');validate_plan(a['plan'])
    require(a['role']==a['plan']['role'] and a['runtime_ms']==3600000 and a['one_guest_boot'] is True,'fixed COST role/one boot/native bounds')
    require(a['host']=='xilinx@192.168.4.35' and a['runner_sha256']==base.RUNNER_SHA and a['board_helper_sha256']==base.HELPER_SHA,'fixed old2dd/de54, no observer install')
    verify_sources(a);verify_artifacts(a);validate_programs(a)
    require(a['legacy_sources']==original.source_hashes() and len(a['legacy_sources'])==21,'all21 original application sources unchanged')
    require(set(a['artifacts'])=={'nbf','package','bit','fit','kernel_verification'}
        and a['artifacts']['nbf']['sha256']==base.NBF_SHA and a['artifacts']['kernel_verification']['sha256']==base.KERNEL_PROOF_SHA,'exact kernel29/46MiB hardware artifact set')
    gate,core=prior_capability(a)
    declared=json.loads(Path(a['plan_record']['path']).read_text())
    require(declared['schema']==PLAN_SCHEMA and declared['state']=='predeclared-reviewed' and declared['plan']==a['plan']
        and declared['sources']==a['sources'] and declared['elf_sha256']==ELF_SHAS,'new fixed COST plan/source/ELF declaration')
    require(declared['primary']=='WHOLE' and declared['secondary']=='steady' and declared['effect_selection']=='none','whole primary, no effect selection')
    utc(declared['declared_utc']);validate_cohort(a)
    return core


def validate_cohort(a):
    record=json.loads(Path(a['cohort_record']['path']).read_text())
    require(record['schema']=='bp-retained29-cost-cohort-v1' and record['state']=='predeclared-reviewed'
        and record['sources']==a['sources'] and record['elf_sha256']==ELF_SHAS
        and record['artifacts']==a['artifacts'],'new independently predeclared COST cohort')
    utc(record['declared_utc']);visits=record['visits']
    require(type(visits) is list and visits and len({v['id'] for v in visits})==len(visits),'distinct planned boot visits')
    for visit in visits:
        require(re.fullmatch(r'[A-Za-z0-9_-]+',visit['id']) and visit['independent_boot'] is True,'explicit independent boot intention')
        validate_plan(visit['plan'])
    selected=[v for v in visits if v['id']==a['visit_id']]
    require(len(selected)==1 and selected[0]['plan']==a['plan'],'exact predeclared visit/order')
    if a['role']=='cost-performance-acquisition':
        require(sum(v['plan']['role']=='cost-performance-acquisition' and v['plan']['workload']==a['plan']['workload'] for v in visits)>=2,
            'at least two declared independent boots for this workload; completed cohort audit still required')
    return record


def acquisition_ready(a,at):
    for key in ('capability_gate','functional_gate'):
        result=json.loads(Path(a[key]['path']).read_text())
        require(utc(result['release_after_recovery_utc'])<=utc(at),'actual prior safe gate closed before launch')
    for key in ('plan_record','cohort_record'):
        require(utc(json.loads(Path(a[key]['path']).read_text())['declared_utc'])<=utc(at),'declaration must precede acquisition')


def result_metadata(a,core):
    return dict(role=a['role'],plan=a['plan'],sources=a['sources'],legacy_sources=a['legacy_sources'],hardware=a['hardware'],
        artifacts=a['artifacts'],programs=a['programs'],primary='WHOLE',secondary='steady',effect_selection='none',
        baseline='mode0-no-retained-control',declared_retained_writes='source telemetry, not hardware counters',
        cohort_record=a['cohort_record'],visit_id=a['visit_id'],advisory_effectiveness_claim=False)


def parse_benchmark(text,case,plan,hardware):
    lines=base.clean_lines(text)
    require(not base.KERNEL_FAILURE_MARKER.search(text) and base.TIMER_GUARD_MARKER not in text,'kernel/timer failure')
    require(not any('HOST_VERIFY_' in s or s.startswith(('PIPE_HINT_','ICACHE_RETENTION_PROBE_','RETAINED_STORE_PROBE_'))
                    for s in lines),'host/legacy/probe contamination inside benchmark')
    prefix='RESUME_RETAINED29_REGEX_COST_' if case['kind']=='regex' else 'RESUME_RETAINED29_COST_'
    selected=[s for s in lines if s.startswith('RESUME_RETAINED29_')]
    count=plan['repeats']*2
    require(len(selected)==3+count*6 and selected[-1]==prefix+'PASS','complete exact command marker set')
    config=base.fields(selected[0],prefix+'CONFIG',('loops','repeats','warmup','policy','enabled_mask','sync','profile',
        'corpus_kib','workload','advisory_source','task_preview_mode','i_lines','d_lines','set_log2','line_bytes','same_set_invalidation','poll_limit'))
    wanted=dict(loops=str(plan['loops']),repeats=str(plan['repeats']),warmup=str(plan['warmup']),policy=case['policy'],
        enabled_mask=str(case['mask']),sync='futex',profile='plain',corpus_kib=str(case['kib']),workload=case['workload'],
        advisory_source='none',task_preview_mode='0',line_bytes='64',same_set_invalidation='1',poll_limit='4096')
    require(all(config[k]==v for k,v in wanted.items()),'command configuration mismatch')
    require(all(base.number(config[k])==v for k,v in hardware['retained'].items()),'configured actual geometry')
    require(selected[1]==prefix+'SCOPE version=29-cost mode=cell activation=before-allocation cleanup=mode0 busy=uce_client_backend matched_lifecycle=1 advisory_source=none baseline=mode0-no-retained-control','complete lifecycle scope')
    schemas=(('RESULT',('cycles','loops')),('WHOLE',('cycles','loops')),
        ('CONTROL',('requested','active_raw','reset_raw','busy_scope','retained_control_writes')),
        ('RESOURCE',('minor_faults','major_faults','user_us','system_us','voluntary_switches','involuntary_switches')),
        ('PREFIX',('before','after','new_activity','advisory_source')),('REPLAY',('before','after','new_activity','advisory_source')))
    cells=[]
    for cell in range(count):
        repeat,order=divmod(cell,2);enabled=(repeat&1)^order;rows={}
        for line,(name,names) in zip(selected[2+6*cell:8+6*cell],schemas):
            row=base.fields(line,prefix+name,('repeat','order','enabled',*names))
            require(tuple(base.number(row[k]) for k in ('repeat','order','enabled'))==(repeat,order,enabled),'ABBA cell order/key')
            rows[name]=row
        require(rows['RESULT']['loops']==rows['WHOLE']['loops']==str(plan['loops']),'loops')
        steady,whole=base.number(rows['RESULT']['cycles']),base.number(rows['WHOLE']['cycles'])
        require(0<steady<=whole,'WHOLE includes steady')
        control=rows['CONTROL'];require(base.number(control['requested'])==case['mask']*enabled
            and control['busy_scope']=='uce_client_backend' and control['retained_control_writes']==str(2*enabled),'actual requested mask/scope/declared retained writes')
        base.status_geometry(base.raw(control['active_raw']),hardware['retained'],case['mask']*enabled,False)
        base.status_geometry(base.raw(control['reset_raw']),hardware['retained'],0,True)
        resource={k:base.number(rows['RESOURCE'][k]) for k in schemas[3][1]}
        for name,pending,counters,shifts in (('PREFIX',base.PREFIX_PENDING,base.PREFIX_COUNTERS,((22,16),(38,8),(46,8),(55,9))),
                ('REPLAY',base.REPLAY_PENDING,base.REPLAY_COUNTERS,((10,16),(26,16),(42,8),(50,8)))):
            row=rows[name];before,after=base.raw(row['before']),base.raw(row['after'])
            require(row['new_activity']=='0' and row['advisory_source']=='none','source-none declaration')
            require(not (before|after)&pending and before&counters==after&counters,'pending/new advisory activity')
            require(all((before>>s)&((1<<w)-1)!=(1<<w)-1 for s,w in shifts),'saturated advisory counters')
        cells.append(dict(repeat=repeat,order=order,enabled=enabled,steady=steady,whole=whole,resource=resource,
                          control=control,prefix=rows['PREFIX'],replay=rows['REPLAY']))
    return dict(case=case,cells=cells,complete_cells=count,scope='COST repeated lifecycle, mode0 baseline has zero retained writes; enabled pays two; UCE/client/backend busy only; declared writes are source telemetry')


def parse_commands(text,a,complete=True):
    plan=validate_plan(a['plan']);lines=base.clean_lines(text)
    require(not any(s.startswith('RETAINED29_APP_') for s in lines),'old application session marker contamination')
    require(not base.KERNEL_FAILURE_MARKER.search(text) and base.TIMER_GUARD_MARKER not in text,'kernel/timer failure')
    markers=[s for s in lines if s.startswith('RETAINED29_COST_APP_')]
    expected=[session_begin(plan),'RETAINED29_COST_APP_PROBE_BEGIN','RETAINED29_COST_APP_EXIT case=probe rc=0','RETAINED29_COST_APP_RETURN case=probe']
    for case in plan['cases']:
        expected += [begin(case),'RETAINED29_COST_APP_EXIT case='+case['id']+' rc=0','RETAINED29_COST_APP_RETURN case='+case['id']]
    if complete:expected+=['RETAINED29_COST_APP_SESSION_END commands=6 exits=7']
    require(markers==expected,'session/case/probe/exit/return chronology or completeness')
    for kind in ('probe','plain','regex'):
        wanted=a['programs'][kind]['elf']['sha256']+'  '+GUEST[kind]
        hashes=[(n,s) for n,s in enumerate(lines) if re.fullmatch(r'[0-9a-f]{64}  '+re.escape(GUEST[kind]),s)]
        require(len(hashes)==1 and hashes[0][1]==wanted and hashes[0][0]<lines.index('RETAINED29_COST_APP_PROBE_BEGIN'),
                'actual guest hash before any use: '+kind)
    start=lines.index('RETAINED29_COST_APP_PROBE_BEGIN')+1;end=lines.index('RETAINED29_COST_APP_EXIT case=probe rc=0')
    base.parse_guest('\n'.join(lines[start:end]),dict(role='probe-present',hardware=a['hardware']))
    results=[]
    for case in plan['cases']:
        start=lines.index(begin(case))+1;end=lines.index('RETAINED29_COST_APP_EXIT case='+case['id']+' rc=0')
        results.append(parse_benchmark('\n'.join(lines[start:end]),case,plan,a['hardware']))
    previous={}
    for result in results:
        for cell in result['cells']:
            for name,mask in (('prefix',base.PREFIX_COUNTERS),('replay',base.REPLAY_COUNTERS)):
                before,after=base.raw(cell[name]['before'])&mask,base.raw(cell[name]['after'])&mask
                require(name not in previous or previous[name]==before,'source counter discontinuity between cells/commands')
                previous[name]=after
    # A benchmark/probe outside its declared window cannot be silently ignored.
    require(sum(s.startswith('RESUME_RETAINED29_') for s in lines)==sum(3+12*plan['repeats'] for _ in results),'stray benchmark markers')
    require(sum(s.startswith('RETAINED_STORE_PROBE_') for s in lines)==2,'stray/missing capability probe rows')
    require(not any('HOST_VERIFY_' in s or s.startswith(('PIPE_HINT_','ICACHE_RETENTION_PROBE_')) for s in lines),'host/legacy marker contamination')
    return dict(commands=results,complete_commands=6,complete_cells=12*plan['repeats'],
                guest_exits=7,all_shell_returns=True,primary='WHOLE',secondary='steady',effect_selection='none')


def complete_console(text,a):
    base.boot_bound(text,a);result=parse_commands(text,a)
    lines=base.clean_lines(text)
    require(not any(s.startswith(('ACTIVE_RUNNER','RUNNER_CLEANUP_SYNC_FAILED','NBF_SHA_MISMATCH',
                    'CONTROL_PROGRAM_SHA_MISMATCH','BITSTREAM_SHA_MISMATCH')) for s in lines),'board runner/helper failure')
    checks=(lambda s:bool(re.fullmatch(r'(?:INFO:\s*)?CORE(?:\[0\])? PASS',s)),
            lambda s:'Returning from ps_main with RC: 0' in s,
            lambda s:s in ('INFO:    BSG PASS','INFO: BSG PASS','BSG PASS'),
            lambda s:s.startswith('BOARD_RUNNER_SOURCE_SHA256='))
    positions=[]
    for check in checks:
        found=[n for n,s in enumerate(lines) if check(s)]
        require(len(found)==1,'complete unique CORE/HOST/BSG/helper terminals');positions+=found
    require(lines[positions[-1]]=='BOARD_RUNNER_SOURCE_SHA256='+base.HELPER_SHA,'executed helper identity')
    require(lines.index('RETAINED29_COST_APP_SESSION_END commands=6 exits=7')<positions[0]
            and all(x<y for x,y in zip(positions,positions[1:])),'full return before ordered terminal')
    return result


def verify_result(record):
    """Rebind a complete recovered acquisition; not a completed-cohort audit."""
    verify_binding(record);result=json.loads(Path(record['path']).read_text())
    require(result.get('schema')==SCHEMA and result.get('state')==SUCCESS_STATE
        and result.get('safe_engine_schema')==safe_functional.session.ENGINE_SCHEMA
        and result.get('safe_recovery_verified') is True and result.get('recovery')=='complete before reservation release'
        and result.get('guest_boots')==1 and result.get('performance_accepted') is False and 'error' not in result,
        'complete safe COST acquisition only')
    a=result['supervisor_admission'];core=validate_admission(a)
    require(result['admission']==core and result['supervisor_sources']==a['sources'],'actual staging core/safe supervisor sources')
    for key,value in result_metadata(a,core).items():require(result[key]==value,'COST result identity '+key)
    verify_binding(result['supervisor_admission_record'])
    require(json.loads(Path(result['supervisor_admission_record']['path']).read_text())==a,'actual COST input bytes')
    guest=result['guest'];require(guest['runner_exit']==guest['guest_exit']==0 and guest['runner_signal'] is None
        and guest['shell_return'] is True and guest['executed_case_ids']==[case['id'] for case in a['plan']['cases']],
        'actual normal complete six-command return')
    verify_binding(guest['console']);parsed=complete_console(Path(guest['console']['path']).read_text(),a)
    require(all(guest[key]==value for key,value in parsed.items()),'console/parsed COST result identity')
    acquisition_ready(a,result['started_utc'])
    require(utc(result['started_utc'])<=utc(result['release_after_recovery_utc'])
        and result['release_after_recovery_utc']==result['reservation_release_utc'],'COST start/recovery/release chronology')
    for row in result['operation_logs'].values():verify_binding(row)
    verify_binding(result['operation_journal']);publication=json.loads(Path(result['operation_journal']['path']).read_text())
    require(publication['state']=='verified old2dd/helper/overlay/operating recovery' and publication['label']=='final'
        and publication['power_pending'] is None and publication['own_guest'] is None,'actual final safe COST recovery receipt')
    return result
