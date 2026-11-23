"""New safe wrapper contract; original functional admission and guest stay exact."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"linux-tests"))
import image_context as context
import re

import retained29_protocol as base
import run_retained29_session_v2 as stage_client
import retained29_safe_session as session
from retained29_application_protocol import utc

SCHEMA='bp-retained29-safe-functional-session-v1'
ADMISSION_SCHEMA='bp-retained29-safe-functional-admission-v1'
SUCCESS_STATE='PASS-complete-recovered-functional-session'
ROLES=('probe-present','benchmark-functional')
SOURCE_FILES=(*base.SOURCE_FILES,*stage_client.NEW_SOURCES,'linux-tests/retained29_safe_guard.py',
    'linux-tests/retained29_safe_session.py','linux-tests/retained29_safe_functional_protocol.py',
    'linux-tests/run_retained29_safe_functional.py',
    # Runtime journal/clock and UTC validation imports predate this wrapper;
    # include them even though the original base admission did not need them.
    'linux-tests/run_retained29_application_session.py','linux-tests/retained29_application_protocol.py')
SOURCE_FILES=tuple(dict.fromkeys((*SOURCE_FILES,*context.source_names())))
require,binding,verify_binding=base.require,base.binding,base.verify_binding


def source_hashes():return {name:binding(base.ROOT/name)['sha256'] for name in SOURCE_FILES}
def bound_sources(a):return a['supervisor_sources']
def verify_sources(a):require(bound_sources(a)==source_hashes(),'safe functional supervisor source drift')


def verify_artifacts(a):
    verify_binding(a['stage_admission'])
    if a['prior_safe_present'] is not None:verify_binding(a['prior_safe_present'])
    _,core=stage_client.validate_outer(a['stage_admission']['path'])
    for record in core['artifacts'].values():verify_binding(record)


def validate_admission(a):
    require(a.get('schema')==ADMISSION_SCHEMA and a.get('state')=='bound-reviewed-safe-functional','DRAFT UNLAUNCHABLE safe functional wrapper')
    require(not a.get('unlaunchable_reasons') and a.get('role') in ROLES,'reviewed unchanged present/fixed role only')
    verify_sources(a);verify_artifacts(a)
    _,core=stage_client.validate_outer(a['stage_admission']['path'])
    context.registration(core['hardware'],core['artifacts'])
    require(core['role']==a['role'] and core['runtime_ms']==3600000,'exact original role/native bounds')
    if core['role']=='probe-present':require(a['prior_safe_present'] is None,'present first')
    else:
        require(a['prior_safe_present']==core['capability_gate'],'fixed core uses actual safe present result')
        prior=verify_result(a['prior_safe_present'],'probe-present')
        require(prior['hardware']==core['hardware'],'safe present hardware match')
    return core


def result_metadata(a,core):
    return dict(role=core['role'],hardware=core['hardware'],artifacts=core['artifacts'],sources=core['sources'],
        performance_inference=False,original_guest_unchanged=True)


def acquisition_ready(a,at):
    if a['prior_safe_present'] is not None:
        prior=json.loads(Path(a['prior_safe_present']['path']).read_text())
        require(utc(prior['release_after_recovery_utc'])<=utc(at),'safe present must already be closed')


def verify_result(record,role):
    verify_binding(record);result=json.loads(Path(record['path']).read_text())
    require(result.get('schema')==SCHEMA and result.get('safe_engine_schema')==session.ENGINE_SCHEMA
        and result.get('state')==SUCCESS_STATE and result.get('role')==role,'genuine new safe functional completion')
    require(result.get('safe_recovery_verified') is True and result.get('recovery')=='complete before reservation release'
        and result.get('guest_boots')==1 and result.get('performance_inference') is False
        and result.get('performance_accepted') is False and 'error' not in result,'actual full safe functional lifecycle')
    wrapper=result['supervisor_admission'];core=validate_admission(wrapper)
    require(result['admission']==core and result['sources']==core['sources']
        and result['supervisor_sources']==bound_sources(wrapper),'exact original core/separate safe supervisor binding')
    require(result['hardware']==core['hardware'] and result['artifacts']==core['artifacts'],'functional hardware/artifact identity')
    verify_binding(result['supervisor_admission_record'])
    require(json.loads(Path(result['supervisor_admission_record']['path']).read_text())==wrapper,'actual wrapper input record')
    context.actual_allocation(Path(result['guest']['console']['path']).read_text(),core['hardware'],core['artifacts'])
    guest=result['guest'];require(guest.get('runner_exit')==0 and guest.get('runner_signal') is None
        and guest.get('guest_exit')==0 and guest.get('shell_return') is True,'unchanged guest normal return')
    verify_binding(guest['console']);text=Path(guest['console']['path']).read_text();base.complete_console(text,core)
    # The old transport already performs this before exec. Rebind its actual
    # console hash here as well, without changing that frozen guest transport.
    lines=base.clean_lines(text);target=base.GUEST[role]
    hashes=[(n,line) for n,line in enumerate(lines) if re.fullmatch(r'[0-9a-f]{64}  '+re.escape(target),line)]
    first=min(n for n,line in enumerate(lines) if line.startswith(('RESUME_RETAINED29_','RETAINED_STORE_PROBE_')))
    require(len(hashes)==1 and hashes[0][1]==core['artifacts']['elf']['sha256']+'  '+target
        and hashes[0][0]<first,'actual unchanged guest ELF hash before use')
    require(utc(result['started_utc'])<=utc(result['release_after_recovery_utc'])
        and result['release_after_recovery_utc']==result['reservation_release_utc'],'verified recovery precedes release')
    for row in result['operation_logs'].values():verify_binding(row)
    verify_binding(result['operation_journal'])
    publication=json.loads(Path(result['operation_journal']['path']).read_text())
    require(publication['state']=='verified old2dd/helper/overlay/operating recovery' and publication['label']=='final'
        and publication['power_pending'] is None and publication['own_guest'] is None,'actual final safe recovery receipt')
    return result
