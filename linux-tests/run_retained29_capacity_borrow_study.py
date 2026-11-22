#!/usr/bin/env python3
"""One prospective global capacity slot; unchanged per-image collector/engine."""
import argparse
import copy
import errno
import fcntl
import json
import os
from pathlib import Path
import sys
import traceback

import analyze_retained29_capacity_borrow_study as analysis
import run_retained29_cost_cohort as collector

p=analysis.p
require=p.require
SCHEMA='bp-retained29-borrow-trace0-capacity-acquisition-v2'
LEDGER_SCHEMA='bp-retained29-borrow-trace0-capacity-ledger-v2'
TEMPLATE_SCHEMA='bp-retained29-borrow-trace0-capacity-slot-template-v2'


def sources():
    return dict(coordinator=p.binding(__file__),analysis=p.binding(analysis.__file__),
                collector=p.binding(collector.__file__),safe_engine=p.binding(p.safe.__file__))


def read_record(record):return analysis.within.bound_json(record)
def save(path,value):p.safe.journal(path,value)


def exact_common_busy(error):
    if not isinstance(error,BlockingIOError) or error.errno not in (errno.EAGAIN,errno.EACCES):return False
    frames=traceback.extract_tb(error.__traceback__)
    if not frames:return False
    frame=frames[-1]
    return (Path(frame.filename).resolve()==Path(p.base.maintained_session.__file__).resolve()
        and frame.name=='reservation'
        and frame.line.strip()=='fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)')


def validate(config,approved=True):
    require(config['schema']==SCHEMA,'new acquisition schema')
    actual=sources()
    require(set(config['sources'])==set(actual) and all(all(config['sources'][name][k]==actual[name][k] for k in ('bytes','sha256')) for name in actual),'coordinator/analysis/collector/engine source drift')
    if not approved:
        require(config['state']=='DRAFT UNLAUNCHABLE' and config['images'] is None and config['output_root'] is None,'explicit pending acquisition draft')
        analysis.validate_declaration(read_record(config['study']));return
    require(config['state']=='predeclared-reviewed capacity acquisition','DRAFT UNLAUNCHABLE')
    require(config['sources']==actual,'approved exact coordinator source paths')
    study=read_record(config['study']);analysis.validate_declaration(study,approved=True)
    root=Path(config['output_root'])
    require(root.is_absolute() and not root.is_symlink() and root!=Path('/'),'fixed owned local output root')
    require(Path(study['attempt_ledger_path']).parent==root,'global ledger inside owned root')
    require(set(config['images'])==set(analysis.IMAGES),'both image admissions required')
    cohorts={}
    for image in analysis.IMAGES:
        image_config=config['images'][image]
        require(image_config['cohort']==study['cohorts'][image],'exact declared image cohort')
        cohort=read_record(image_config['cohort']);cohorts[image]=cohort
        qualification=p.physical_qualification(cohort['physical_qualification'],cohort['hardware'],cohort['artifacts'])
        analysis.image_source_profile(qualification,256 if image=='small' else study['selected_large_lines_per_side'],analysis.SMALL_TOP if image=='small' else study['selected_large_source_TOP'])
        clocks=read_record(qualification['clock_topology'])
        require(clocks['core_hz']==clocks['axi_hz']==20000000,'both actual physical clocks20MHz')
        require(len(image_config['templates'])==16,'all16 frozen image slot templates')
        for record,visit in zip(image_config['templates'],p.canonical_visits()):
            template=read_record(record);body=template['admission']
            require(template['schema']==TEMPLATE_SCHEMA and template['image']==image and template['visit_id']==visit['id'],'fixed slot template')
            require(body['prior_results'] is None and body['cohort']==image_config['cohort'],'only future prior bindings unresolved')
            require(body['schema']==p.ADMISSION_SCHEMA and body['state']=='bound-reviewed-promoted-COST','exact per-image admission schema')
            require(body['session']['visit_id']==visit['id'] and body['session']['plan']==visit['plan'],'exact frozen visit/plan')
            # Existing static source/artifact/physical/capability/functional gates;
            # only prefix results await actual earlier boots. No legacy relaxation.
            p.verify_sources(body);p.verify_artifacts(body)
            p.cost.validate_admission(body['session']);p.cohort_record(body)
        require(Path(cohort['ledger_path']).is_absolute() and Path(cohort['ledger_path']).parent.is_dir(),'fixed prepared authoritative image ledger')
    analysis.matched_hardware(cohorts['small']['hardware'],cohorts['large']['hardware'],study['selected_large_lines_per_side'])
    require(cohorts['small']['ledger_path']!=cohorts['large']['ledger_path'],'independent image acquisition ledgers')
    return study


def image_ledger(config,image):
    cohort_record=config['images'][image]['cohort'];cohort=read_record(cohort_record)
    path=Path(cohort['ledger_path'])
    # Use the existing per-image lock inode, never the physical reservation or
    # a handoff FD. Release before invoking the unchanged collector.
    with path.with_name('acquisition-ledger.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        value=collector.ledger_read(path,cohort_record)
        return dict(record=p.binding(path) if path.exists() else None,value=value)


def prefix(config,ledger,order):
    require(ledger['schema']==LEDGER_SCHEMA and ledger['study']==config['study'],'same global study ledger')
    expected=analysis.schedule()
    require(len(ledger['entries'])<=32,'at most32 fixed slots')
    ids=set();previous=None;accepted={image:[] for image in analysis.IMAGES}
    for entry,wanted in zip(ledger['entries'][:order],expected):
        require(all(entry[k]==v for k,v in wanted.items()) and entry['state']=='PASS','exact complete prior global prefix; failures stop study')
        result=read_record(entry['result'])
        checked=p.verify_session(entry['result'],config['images'][entry['image']]['cohort'],accepted[entry['image']])
        accepted[entry['image']].append(checked)
        require(entry['boot_id']==checked['boot_id'] and entry['boot_id'] not in ids,'actual unique accepted global UUID')
        ids.add(entry['boot_id'])
        start,end=p.utc(result['started_utc']),p.utc(result['release_after_recovery_utc'])
        require(start<=end and (previous is None or previous<=start),'global recovered chronology')
        previous=end
    require(len(ledger['entries'][:order])==order,'complete earlier global slots')
    return ids,previous


def expected_prior(config,ledger,image):
    return [entry['result'] for entry in ledger['entries'] if entry['image']==image and entry['state']=='PASS']


def current_snapshot(config,entry):
    return image_ledger(config,entry['image'])


def verify_prefix_snapshot(config,ledger,entry,snapshot):
    prior=expected_prior(config,ledger,entry['image']);rows=snapshot['value']['entries']
    require(len(rows)==entry['cohort_index'] and all(r['state']=='PASS' for r in rows),'authoritative image prefix has failure/running/unexpected slot')
    require([r['result'] for r in rows]==prior,'authoritative image prefix equals global accepted results')
    accepted=[]
    for row in rows:accepted.append(p.verify_session(row['result'],config['images'][entry['image']]['cohort'],accepted))
    return prior


def actual_start(config,ledger,entry,dispatch,output,input_record):
    # Called only by unchanged safe.execute's operations factory, after common
    # reservation and durable reserved/session + original source snapshots.
    require(sources()==config['sources'],'global source drift before actual common acquisition')
    session=output/'session.json';state=json.loads(session.read_text())
    require(state['safe_engine_schema']==p.safe.ENGINE_SCHEMA and state['state']=='reserved' and state['supervisor_admission_record']==input_record,'actual reserved session identity')
    require(p.utc(read_record(config['study'])['declared_utc'])<=p.utc(state['started_utc']),'global study declared before acquisition')
    snapshot=Path(dispatch['directory'])/'common-acquisition.json'
    with snapshot.open('xb') as stream:
        stream.write(session.read_bytes());stream.flush();os.fsync(stream.fileno())
    descriptor=os.open(str(snapshot.parent),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    entry.update(state='START',actual_common_reservation=True)
    dispatch.update(state='START',actual_common_reservation=True,common_acquisition=p.binding(snapshot),
        common_lock=str(p.base.maintained_session.SESSION_LOCK))
    save(Path(config['output_root'])/'matched-capacity-attempts.json',ledger)


def engine_for(config,ledger,entry,dispatch,output,input_record):
    def engine(*args,**kwargs):
        original_factory=kwargs['operations']
        def after_reservation(*factory_args):
            ops=original_factory(*factory_args)
            actual_start(config,ledger,entry,dispatch,output,input_record)
            return ops
        kwargs['operations']=after_reservation
        return p.safe.execute(*args,**kwargs)
    return engine


def reconcile(config,ledger,entry,snapshot=None):
    """Read/reparse only; never runs a collector, target or recovery operation."""
    dispatch=entry['dispatches'][-1];output=Path(dispatch['output']);input_record=dispatch['input']
    directory=Path(config['output_root'])/('slot%02d-dispatch%02d'%(entry['order'],len(entry['dispatches'])))
    require(Path(dispatch['directory'])==directory and output==directory/'session' and
        input_record['path']==str(directory/'admission.json') and dispatch['dispatch_record']['path']==str(directory/'dispatch.json'),
        'fixed owned dispatch/input/result paths; no unsigned redirection')
    p.verify_binding(dispatch['dispatch_record'])
    declared=read_record(dispatch['dispatch_record'])
    require(declared['not_actual_target_attempt'] is True and declared['input']==input_record and declared['output']==str(output)
        and declared['prior_image_ledger']==dispatch['prior_image_ledger'] and declared['sources']==config['sources']
        and declared['config']==dispatch['config'] and declared['order']==entry['order']
        and declared['image']==entry['image'] and declared['visit_id']==entry['visit_id'],'exact pre-invocation dispatch binding')
    for name,row in config['sources'].items():
        copied=p.binding(directory/'coordinator-sources'/name)
        require(all(copied[k]==row[k] for k in ('bytes','sha256')),'actual immutable extra-wrapper source snapshot')
    require(sources()==config['sources'] and read_record(dispatch['config'])==config,'exact dispatched sources/config')
    p.verify_binding(input_record);admission=read_record(input_record)
    p.verify_sources(admission)
    snapshot=current_snapshot(config,entry) if snapshot is None else snapshot
    rows=snapshot['value']['entries'];index=entry['cohort_index']
    if len(rows)==index+1:
        row=rows[index]
        require(row['input']==input_record and row['id']==entry['visit_id'] and row['order']==index,'only our exact authoritative claimed slot')
        if row['state']=='PASS':
            common=p.binding(directory/'common-acquisition.json')
            if dispatch.get('common_acquisition') is not None:require(dispatch['common_acquisition']==common,'immutable actual common-acquisition record')
            reserved=read_record(common)
            require(reserved['state']=='reserved' and reserved['safe_engine_schema']==p.safe.ENGINE_SCHEMA and
                reserved['supervisor_admission_record']==input_record,'source-bound actual common reservation before target claim')
            record=p.binding(output/'session.json')
            require(row['result']==record,'authoritative PASS exact local result')
            result=read_record(record);accepted=p.verify_prefix(admission)
            checked=p.verify_session(record,admission['cohort'],accepted)
            seen,last=prefix(config,ledger,entry['order'])
            require(checked['boot_id']==row['boot_id'] and checked['boot_id'] not in seen,'all32 actual acquisition UUIDs unique')
            require(last is None or last<=p.utc(result['started_utc']),'previous image recovered before this actual boot')
            entry.update(state='PASS',result=record,boot_id=checked['boot_id'],actual_common_reservation=True,closed_utc=p.safe.now())
            dispatch.update(state='PASS',authoritative_image_ledger=snapshot['record'])
            return 'PASS'
        if row['state']=='FAIL':
            entry.update(state='FAIL',authoritative_image_ledger=snapshot['record'],closed_utc=p.safe.now())
            dispatch['state']='FAIL';return 'FAIL'
        require(row['state']=='running','known authoritative state')
        entry.update(state='BLOCKED',reason='authoritative acquisition still running; no new hardware action')
        return 'BLOCKED'
    require(len(rows)==index,'no unexpected authoritative image attempt')
    outcome_path=Path(dispatch['directory'])/'collector-outcome.json'
    if outcome_path.exists():
        outcome=json.loads(outcome_path.read_text())
        require(outcome['dispatch']==dispatch['dispatch_record'] and outcome['input']==input_record,'bound local outcome')
        if outcome['state']=='busy-no-acquisition' and snapshot==dispatch['prior_image_ledger'] and not output.exists():
            entry.update(state='DEFERRED',actual_common_reservation=False)
            dispatch.update(state='DEFERRED',outcome=p.binding(outcome_path));return 'DEFERRED'
    entry.update(state='BLOCKED',reason='missing/ambiguous authoritative acquisition or local outcome; no blind rerun')
    return 'BLOCKED'


def prepare_dispatch(config,config_record,ledger,entry):
    snapshot=current_snapshot(config,entry)
    prior=verify_prefix_snapshot(config,ledger,entry,snapshot)
    template_record=config['images'][entry['image']]['templates'][entry['cohort_index']]
    template=read_record(template_record);admission=copy.deepcopy(template['admission'])
    admission['prior_results']=prior
    p.validate_admission(admission)
    serial=len(entry['dispatches'])+1
    directory=Path(config['output_root'])/('slot%02d-dispatch%02d'%(entry['order'],serial))
    directory.mkdir(exist_ok=False)
    path=directory/'admission.json';save(path,admission);input_record=p.binding(path)
    # Snapshot the extra wrapper sources separately; do not alter the old safe
    # engine's bound source set, collector or common-lock protocol.
    for name,row in config['sources'].items():
        target=directory/'coordinator-sources'/name;target.parent.mkdir(exist_ok=True)
        with target.open('xb') as stream:
            stream.write(Path(row['path']).read_bytes());stream.flush();os.fsync(stream.fileno())
        require(p.binding(target)['sha256']==row['sha256'],'new wrapper source snapshot')
    descriptor=os.open(str(directory/'coordinator-sources'),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    record=dict(schema='bp-retained29-capacity-DISPATCH-v1',not_actual_target_attempt=True,
        image=entry['image'],visit_id=entry['visit_id'],order=entry['order'],config=config_record,
        sources=config['sources'],template=template_record,input=input_record,prior_image_ledger=snapshot,
        output=str(directory/'session'),created_utc=p.safe.now())
    save(directory/'dispatch.json',record)
    dispatch=dict(state='DISPATCH',directory=str(directory),output=record['output'],input=input_record,config=config_record,
        prior_image_ledger=snapshot,dispatch_record=p.binding(directory/'dispatch.json'),actual_common_reservation=False)
    entry['dispatches'].append(dispatch);entry.update(state='DISPATCH',actual_common_reservation=False)
    save(Path(config['output_root'])/'matched-capacity-attempts.json',ledger)
    return admission,dispatch


def advance(config_record,execute=False,reconcile_only=False,invoke=collector.execute):
    config=read_record(config_record);study=validate(config)
    require(execute!=reconcile_only,'one explicit next acquisition or read-only reconciliation')
    root=Path(config['output_root']);root.mkdir(parents=True,exist_ok=True)
    with (root/'matched-capacity-coordinator.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=root/'matched-capacity-attempts.json'
        ledger=json.loads(path.read_text()) if path.exists() else dict(schema=LEDGER_SCHEMA,study=config['study'],config=config_record,
            root_identity=dict(device=root.stat().st_dev,inode=root.stat().st_ino),entries=[])
        require(ledger['config']==config_record and ledger['root_identity']==dict(device=root.stat().st_dev,inode=root.stat().st_ino),'exact global config/root identity')
        index=next((i for i,e in enumerate(ledger['entries']) if e['state']!='PASS'),len(ledger['entries']))
        prefix(config,ledger,index)
        if index==32:return 'COMPLETE'
        if index<len(ledger['entries']):
            require(index==len(ledger['entries'])-1,'only one pending global slot')
            entry=ledger['entries'][index]
            require(all(entry[k]==v for k,v in analysis.schedule()[index].items()),'pending slot image/order cannot change')
            if entry['state']=='FAIL':return 'FAIL'
            if entry['state']!='DEFERRED':
                state=reconcile(config,ledger,entry);save(path,ledger)
                # Never execute a second dispatch in a reconciliation invocation,
                # even when a prior crash is proved recovered/PASS or busy.
                return state
            require(all(d['state']=='DEFERRED' and d['actual_common_reservation'] is False for d in entry['dispatches']),'only exact busy deferrals may redispatch')
            require(reconcile(config,ledger,entry)=='DEFERRED','deferred source/outcome/authoritative no-acquisition proof unchanged')
            save(path,ledger)
            if reconcile_only:return 'DEFERRED'
        else:
            if reconcile_only:return 'NO-PENDING-DISPATCH'
            entry=dict(analysis.schedule()[index],state='NEW',dispatches=[]);ledger['entries'].append(entry)
        admission,dispatch=prepare_dispatch(config,config_record,ledger,entry)
        output=Path(dispatch['output']);error=None
        try:
            invoke(admission,output,dispatch['input'],engine=engine_for(config,ledger,entry,dispatch,output,dispatch['input']))
            local=dict(state='returned',dispatch=dispatch['dispatch_record'],input=dispatch['input'])
        except BaseException as caught:
            error=caught
            after=current_snapshot(config,entry)
            busy=exact_common_busy(caught) and after==dispatch['prior_image_ledger'] and not output.exists() and entry['state']=='DISPATCH'
            local=dict(state='busy-no-acquisition' if busy else 'exception',dispatch=dispatch['dispatch_record'],input=dispatch['input'],error=repr(caught))
        save(Path(dispatch['directory'])/'collector-outcome.json',local)
        state=reconcile(config,ledger,entry);save(path,ledger)
        if state=='PASS' and error is not None:
            # A caught failure after authoritative PASS is not a silent new run;
            # fail this global study. Crash-only recovery uses reconcile_only.
            entry.update(state='FAIL',error='collector raised after authoritative PASS: '+repr(error));save(path,ledger);return 'FAIL'
        return state


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('config',type=Path)
    parser.add_argument('--config-sha256',required=True)
    parser.add_argument('--execute',action='store_true',help='at most one next physical session, never retries')
    parser.add_argument('--reconcile-only',action='store_true',help='read-only, no collector/recovery/target calls')
    a=parser.parse_args();record=p.binding(a.config);require(record['sha256']==a.config_sha256,'external coordinator-config anchor')
    if not a.execute and not a.reconcile_only:
        config=read_record(record);validate(config,approved=config['state']!='DRAFT UNLAUNCHABLE');print('CAPACITY_ACQUISITION_OFFLINE_ONLY=1');return
    state=advance(record,a.execute,a.reconcile_only)
    print('CAPACITY_ACQUISITION_STATE='+state)
    if state in ('FAIL','BLOCKED'):raise SystemExit(1)
    if state=='DEFERRED':raise SystemExit(75)


if __name__=='__main__':main()
