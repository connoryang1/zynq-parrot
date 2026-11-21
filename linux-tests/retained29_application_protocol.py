"""Explicit application-cohort ABI29 contract; no board actions or effects selection."""
from datetime import datetime
import json
from pathlib import Path
import re

import retained29_protocol as base
import run_retained29_session_v2 as stage_client

SCHEMA = 'bp-retained29-application-session-v1'
PLAN_SCHEMA = 'bp-retained29-application-plan-v1'
ROLES = ('pilot-functional', 'performance-acquisition')
WORKLOADS = ('scan', 'lookup', 'parse', 'chase', 'regex')
POLICIES = (('ordinary-i', 9), ('ordinary-d', 6), ('ordinary-joint', 15))
ELF_SHAS = dict(plain=base.ELF_SHAS['benchmark-functional'],
               regex='2b23a02ed44e6c5a34c418d8d3e9fa9d7f277d465a032a3860172cb9242de129',
               probe=base.ELF_SHAS['probe-present'])
GUEST = dict(plain='/tmp/bp-retained29-app-plain', regex='/tmp/bp-retained29-app-regex',
             probe='/tmp/bp-retained29-app-probe')
FROZEN = tuple(dict.fromkeys((*base.SOURCE_FILES, *stage_client.NEW_SOURCES)))
SOURCE_FILES = (*FROZEN, 'linux-tests/retained29_application_protocol.py',
                'linux-tests/run_retained29_application_session.py',
                'linux-tests/scheduler_retained29_regex_benchmark.c', 'linux-tests/retained29_regex_workload.h')
require, binding, verify_binding = base.require, base.binding, base.verify_binding


def source_hashes():return {name:binding(base.ROOT/name)['sha256'] for name in SOURCE_FILES}


def utc(value):
    result=datetime.fromisoformat(value)
    require(result.tzinfo is not None and result.utcoffset().total_seconds()==0,'UTC timestamp required')
    return result


def plan_for(role, workload=None, rotation=0):
    require(role in ROLES and type(rotation) is int and 0<=rotation<6,'application role/rotation')
    if role=='pilot-functional':
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


def begin(case):return 'RETAINED29_APP_BEGIN case='+case['id']+' kind='+case['kind']


def command(plan,case):
    # All text comes from canonical enum/integer fields; no free shell text.
    return ('echo '+begin(case)+'; '+' '.join(argv_for(plan,case))+
            '; r29a_rc=$?; echo RETAINED29_APP_EXIT case='+case['id']+' rc=$r29a_rc')


def probe_command():
    return ('echo RETAINED29_APP_PROBE_BEGIN; '+GUEST['probe']+
            ' present; r29a_rc=$?; echo RETAINED29_APP_EXIT case=probe rc=$r29a_rc')


def session_begin(plan):
    return ('RETAINED29_APP_SESSION_BEGIN role='+plan['role']+' rotation='+str(plan['rotation'])+' commands=6')


def transfer_commands(a,kind):
    program=a['programs'][kind]
    result=base.transport.validate_transfer(Path(program['transfer']['path']),program['elf']['sha256'])
    require(result is None,'wire transfer required; embedded/alternate commands unsupported')
    return [line.replace(base.transport.GUEST_ELF,GUEST[kind])
            for line in Path(program['transfer']['path']).read_text().splitlines()]


def prior_capability(a):
    verify_binding(a['capability_gate']);gate=json.loads(Path(a['capability_gate']['path']).read_text())
    require(gate.get('state')=='PASS-complete-recovered-functional-session' and gate.get('role')=='probe-present',
            'actual successful present probe required before matrix launch')
    require(gate.get('guest_boots')==1 and gate.get('recovery')=='complete before reservation release'
            and gate.get('performance_inference') is False,'prior probe full recovery scope')
    utc(gate['release_after_recovery_utc'])
    require(gate['hardware']==a['hardware'],'present probe exact hardware binding')
    for key,value in a['artifacts'].items():
        require(gate['artifacts'][key]==value,'prior probe artifact mismatch: '+key)
    base.validate_admission(gate['admission']) # genuine old probe role only, never benchmark-functional
    require(gate['admission']['role']=='probe-present' and gate['artifacts']==gate['admission']['artifacts'],
            'prior probe admission artifact binding')
    require(gate['sources']==gate['admission']['sources']=={k:a['sources'][k] for k in base.SOURCE_FILES},
            'frozen probe source binding')
    guest=gate['guest'];require(guest.get('runner_exit')==0 and guest.get('runner_signal') is None
        and guest.get('guest_exit')==0 and guest.get('shell_return') is True,'prior probe normal return')
    verify_binding(guest['console']);base.complete_console(Path(guest['console']['path']).read_text(),gate['admission'])
    verify_binding(a['functional_gate']);functional=json.loads(Path(a['functional_gate']['path']).read_text())
    require(functional.get('state')=='PASS-complete-recovered-functional-session'
            and functional.get('role')=='benchmark-functional' and functional.get('guest_boots')==1
            and functional.get('recovery')=='complete before reservation release'
            and functional.get('performance_inference') is False,'unchanged fixed V1 functional first gate required')
    require(utc(functional['release_after_recovery_utc'])>=utc(gate['release_after_recovery_utc']),'present before fixed functional gate')
    require(functional['hardware']==a['hardware'] and functional['sources']==gate['sources'],'fixed functional hardware/source identity')
    base.validate_admission(functional['admission'])
    require(functional['admission']['role']=='benchmark-functional'
            and functional['admission']['capability_gate']==a['capability_gate']
            and functional['artifacts']==functional['admission']['artifacts'],'genuine fixed functional admission')
    for key,value in a['artifacts'].items():require(functional['artifacts'][key]==value,'fixed functional artifact mismatch '+key)
    normal=functional['guest'];require(normal.get('runner_exit')==0 and normal.get('runner_signal') is None
        and normal.get('guest_exit')==0 and normal.get('shell_return') is True,'fixed functional normal return')
    verify_binding(normal['console']);base.complete_console(Path(normal['console']['path']).read_text(),functional['admission'])
    verify_binding(a['stage_admission'])
    _,stage_base=stage_client.validate_outer(Path(a['stage_admission']['path']))
    require(stage_base==gate['admission'],'stage handle must be exact successful present-probe admission')
    return gate,stage_base


def validate_admission(a):
    require(a.get('schema')==SCHEMA,'application schema; old fixed roles unsupported')
    require(a.get('state')=='bound-reviewed-application-session','DRAFT UNLAUNCHABLE; no hardware/capability admission')
    require(not a.get('unlaunchable_reasons'),'unresolved draft admission blockers')
    validate_plan(a['plan']);require(a.get('role')==a['plan']['role'],'explicit role/plan')
    require(a.get('runtime_ms')==3600000 and a.get('one_guest_boot') is True,'fixed native3600s, one boot')
    require(a.get('host')=='xilinx@192.168.4.35','fixed board host')
    require(a.get('runner_sha256')==base.RUNNER_SHA and a.get('board_helper_sha256')==base.HELPER_SHA,'old2dd/de54 fixed')
    require(a.get('sources')==source_hashes(),'application/frozen source drift')
    require(type(a.get('hardware')) is dict and a['hardware'].get('l1i_bytes')==32768
            and a['hardware'].get('l1d_bytes')==32768 and a['hardware'].get('l2_bytes')==16384,'explicit ordinary cache geometry')
    retained=a['hardware']['retained']
    require(set(retained)=={'i_lines','d_lines','set_log2'} and all(type(v) is int for v in retained.values())
            and 1<=retained['i_lines']<=65535 and 1<=retained['d_lines']<=65535 and 0<=retained['set_log2']<=15,
            'canonical retained geometry')
    require(a.get('legacy_sources')=={k:a['sources'][k] for k in FROZEN} and len(FROZEN)==17,'all17 frozen identities')
    require(set(a['programs'])==set(ELF_SHAS),'both workload ELFs and actual probe required')
    for kind,program in a['programs'].items():
        require(set(program)=={'elf','transfer'},'program artifacts')
        for record in program.values():verify_binding(record)
        require(program['elf']['sha256']==ELF_SHAS[kind],'fixed accepted ELF identity: '+kind)
        transfer_commands(a,kind)
    require(set(a['artifacts'])=={'nbf','package','bit','fit','kernel_verification'},'hardware artifact set')
    for record in a['artifacts'].values():verify_binding(record)
    require(a['artifacts']['nbf']['sha256']==base.NBF_SHA
            and a['artifacts']['kernel_verification']['sha256']==base.KERNEL_PROOF_SHA,'actual46M kernel29 inputs')
    gate,_=prior_capability(a)
    verify_binding(a['plan_record']);declared=json.loads(Path(a['plan_record']['path']).read_text())
    require(declared.get('schema')==PLAN_SCHEMA and declared.get('state')=='predeclared-reviewed' and declared.get('plan')==a['plan']
            and declared.get('sources')==a['sources'] and declared.get('elf_sha256')==ELF_SHAS,'predeclared immutable plan binding')
    require(declared.get('primary')=='WHOLE' and declared.get('secondary')=='steady'
            and declared.get('effect_selection')=='none','fixed metrics/no result selection')
    utc(declared['declared_utc'])
    return a


def parse_benchmark(text,case,plan,hardware):
    lines=base.clean_lines(text)
    require(not base.KERNEL_FAILURE_MARKER.search(text) and base.TIMER_GUARD_MARKER not in text,'kernel/timer failure')
    require(not any('HOST_VERIFY_' in s or s.startswith(('PIPE_HINT_','ICACHE_RETENTION_PROBE_','RETAINED_STORE_PROBE_'))
                    for s in lines),'host/legacy/probe contamination inside benchmark')
    prefix='RESUME_RETAINED29_REGEX_' if case['kind']=='regex' else 'RESUME_RETAINED29_'
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
    require(selected[1]==prefix+'SCOPE version=29 mode=cell activation=before-allocation cleanup=mode0 busy=uce_client_backend matched_lifecycle=1 advisory_source=none','complete lifecycle scope')
    schemas=(('RESULT',('cycles','loops')),('WHOLE',('cycles','loops')),
        ('CONTROL',('requested','active_raw','reset_raw','busy_scope')),
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
            and control['busy_scope']=='uce_client_backend','actual requested mask/scope')
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
    return dict(case=case,cells=cells,complete_cells=count,scope='repeated matched lifecycle; UCE/client/backend busy only')


def parse_commands(text,a,complete=True):
    plan=validate_plan(a['plan']);lines=base.clean_lines(text)
    require(not base.KERNEL_FAILURE_MARKER.search(text) and base.TIMER_GUARD_MARKER not in text,'kernel/timer failure')
    markers=[s for s in lines if s.startswith('RETAINED29_APP_')]
    expected=[session_begin(plan),'RETAINED29_APP_PROBE_BEGIN','RETAINED29_APP_EXIT case=probe rc=0','RETAINED29_APP_RETURN case=probe']
    for case in plan['cases']:
        expected += [begin(case),'RETAINED29_APP_EXIT case='+case['id']+' rc=0','RETAINED29_APP_RETURN case='+case['id']]
    if complete:expected+=['RETAINED29_APP_SESSION_END commands=6 exits=7']
    require(markers==expected,'session/case/probe/exit/return chronology or completeness')
    for kind in ('probe','plain','regex'):
        wanted=a['programs'][kind]['elf']['sha256']+'  '+GUEST[kind]
        hashes=[(n,s) for n,s in enumerate(lines) if re.fullmatch(r'[0-9a-f]{64}  '+re.escape(GUEST[kind]),s)]
        require(len(hashes)==1 and hashes[0][1]==wanted and hashes[0][0]<lines.index('RETAINED29_APP_PROBE_BEGIN'),
                'actual guest hash before any use: '+kind)
    start=lines.index('RETAINED29_APP_PROBE_BEGIN')+1;end=lines.index('RETAINED29_APP_EXIT case=probe rc=0')
    base.parse_guest('\n'.join(lines[start:end]),dict(role='probe-present',hardware=a['hardware']))
    results=[]
    for case in plan['cases']:
        start=lines.index(begin(case))+1;end=lines.index('RETAINED29_APP_EXIT case='+case['id']+' rc=0')
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
    require(lines.index('RETAINED29_APP_SESSION_END commands=6 exits=7')<positions[0]
            and all(x<y for x,y in zip(positions,positions[1:])),'full return before ordered terminal')
    return result
