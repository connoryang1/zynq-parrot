#!/usr/bin/env python3
"""Complete lossless borrowing fullcore archive; no build/model/FST-reader/cleanup."""
import argparse,importlib.util,json,signal,shutil,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PRODUCER=HERE.parent/'retained-borrow256-trace0-preparation-20261122'
sys.path.insert(0,str(PRODUCER))
import run_full as full
ARCHIVE_API=Path('/home/coyang/zynq-parrot-linux-host-observer/research/retained256-qualification-20261122/close256.py')
spec=importlib.util.spec_from_file_location('qualified_lossless_archive_api',ARCHIVE_API)
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
FULL=full.budget.BASE/'full01'
OUT=full.budget.DURABLE/'closed01'
CAP=64*1024**2;DEADLINE=600
COMPOSITE='ccd530d02b959ac6d5da98d7ad08310d4c65c77942724e9e6136473e86542f4b'
MODEL='695e53dccdf418dac6e40ec1c652752e82fb7187c834dbd689ac80233445a80c'
SELECTION='a6ee5b3a301443b86ea2647a3e827535957da8117c5ce1efde4c1c55c6582f78'
bind,require,write=full.bind,full.require,full.write

def source_home():
    h=full.source.budget();ours=full.source.size(HERE)
    require(h['helper_bytes']+ours<=full.source.HELPER_CAP,'Frozen256 producer+new close helper under prospective8MiB')
    h=dict(h,closure_helper_bytes=ours,helper_bytes=h['helper_bytes']+ours,required_free_bytes=h['required_free_bytes']-ours)
    return h

def snapshot():
    require(bind(FULL/'session.json')['sha256']==COMPOSITE,'actual ROOT complete fullcore receipt')
    q=json.loads((FULL/'session.json').read_text())
    require(q['state']=='PASS borrow-only trace0 clean fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-geometry-source-audits','complete fullcore PASS')
    require(q['source_tree_baseline']=='1008854d30e5d923c86c3232fc22af039467d552'and q['source_bp']=='bb575a764c200f07c6f3259a179bdc861dd7593f','borrowing-only source heads')
    full.validate_selection(Path(q['selection']['path']),SELECTION)
    require(full.full_bind(q['model']['path'])==q['model']and q['model']['sha256']==MODEL,'same complete model/stat')
    require(bind(q['prepared']['path'])==q['prepared'],'actual ROOT Make-n+build preparation')
    prepared=json.loads(Path(q['prepared']['path']).read_text());require(prepared['durable_allocation_bytes']==CAP,'prospective64MiB allocation')
    require(prepared['actual_make_preflight'],'actual Make-n, not metadata-only')
    full.dryrun.verify(prepared['actual_make_preflight']['path'],full.commands(),256)
    require(bind(q['actual_source_list']['path'])==q['actual_source_list'],'same actual consumed sources')
    actual,stamp=full.actual_sources(FULL/'verilator',256)
    require(actual==json.loads(Path(q['actual_source_list']['path']).read_text())and stamp==q['model_stamp'],'all consumed source bytes/stat/flags+trace0 stamp')
    for r in q['inputs']:require(bind(r['path'])==r,'all frozen producer/helpers unchanged')
    for r in q['closed_audits'].values():require(bind(r['path'])==r,'complete closed audit bytes')
    strict=json.loads(Path(q['closed_audits']['strict']['path']).read_text());counter=json.loads(Path(q['closed_audits']['counter']['path']).read_text());params=json.loads(Path(q['closed_audits']['parameters']['path']).read_text())['facts']['values']
    require(strict['accepted']is True and len(strict['cold_function_retirement'])==16,'full512/realwrites/16I instructions')
    require(counter['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'actual independent clock/GP0 counters')
    require(len(params)==17 and params['core_minimal.cache_miss_trace_p']==0,'all17 original geometry/trace0 parameters')
    expected,_=full.module('archive_actual_geometry',PRODUCER/'geometry.py').expected(256);require(params==expected,'ALL17 exact parameter values')
    labels=['make-preflight','clean','build','loader','integrity-run','integrity-checker','advisory-run','advisory-checker','strict','counter','parameters']
    require([r['label']for r in q['commands']]==labels,'all11 actual phases')
    for row in q['commands']:
        life=row['ownership'];require(life['failure']is None and not life['owned_group_remaining'],'all owned groups closed')
        if not row['label'].endswith('-run'):require(life['returncode']==0,'actual phase success')
        require(bind(row['log']['path'])==row['log'],'all actual command logs')
    obj=Path(q['model']['path']).parent
    generated=[p for p in obj.iterdir()if p.is_file()and(p.suffix in('.cpp','.h','.hpp','.mk','.dat')or p.name.startswith('.build_config-'))]
    require(any(p.suffix=='.cpp'for p in generated)and any(p.suffix=='.h'for p in generated),'ALL generated source for later qualified clone')
    sources=[Path(p)for p in actual['sources']]+generated
    directories=[PRODUCER,HERE]
    for directory in directories:sources += [p for p in directory.rglob('*')if p.is_file()and '__pycache__'not in p.parts]
    sources += [Path(r['path'])for r in q['inputs']]
    # Preserve archive API import dependencies, without their output directories.
    sources += list(ARCHIVE_API.parent.glob('*.py'))
    sources += [ARCHIVE_API,full.STRICT,full.COUNTER,full.COUNTER.with_name('build_full.py'),full.GENERATED_GEOMETRY,full.ROOT/'testing/check_run.py',full.FIXTURE]
    software=json.loads(Path(q['software_proof']['path']).read_text());require(bind(q['software_proof']['path'])==q['software_proof'],'original exact program preparation proof')
    sources += [Path(q['software_proof']['path'])]
    parent_row=software['old_program_proof'];require(bind(parent_row['path'])==parent_row,'original256 software lineage');sources.append(Path(parent_row['path']))
    parent=json.loads(Path(parent_row['path']).read_text())
    for row in parent['sources']+[parent['nbf_script'],parent['cold08_source'],software['source'],software['script']]+software['helper_sources']:
        require(bind(row['path'])==row,'original program source/nbf script');sources.append(Path(row['path']))
    fixture=json.loads(full.FIXTURE.read_text());require(bind(fixture['source']['path'])==fixture['source'],'cold08 exact C source');sources.append(Path(fixture['source']['path']))
    source_proof=json.loads(Path(q['source_preparation']['path']).read_text());sources += [Path(r['path'])for r in source_proof['files']]
    singles=[Path(q['model']['path'])]+[FULL/role/name for role in('integrity','advisory')for name in('trace.fst','prog.riscv','prog.nbf')]
    metadata=[p for p in FULL.rglob('*')if p.is_file()and 'verilator'not in p.relative_to(FULL).parts and p not in singles]
    # Keep every actual preparation/Make-n proof and all producer setup refusals.
    metadata += [Path(q['prepared']['path'])]+[p for p in (full.budget.BASE/'preflight01').rglob('*')if p.is_file()and p.suffix in('.json','.log')]
    metadata += [p for p in (full.budget.DURABLE/'home-proof01').rglob('*')if p.is_file()]
    groups=dict(sources=[bind(p)for p in dict.fromkeys(sources)],metadata=[bind(p)for p in dict.fromkeys(metadata)],singles=[bind(p)for p in singles])
    return q,groups

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');ap.add_argument('--admission-sha256',required=True);a=ap.parse_args()
    admission=HERE/'admission.json';require(bind(admission)['sha256']==a.admission_sha256,'ROOT-reviewed archive source admission');p=json.loads(admission.read_text())
    for row in p['inputs']:require(bind(row['path'])==row,'archive input drift')
    require(a.execute,'ROOT explicit archive execution only; preparing agent never archives')
    require(CAP==full.budget.DURABLE_CAP==p['durable_bytes']and p['seconds']==DEADLINE,'fixed prospective64MiB/600s')
    require(not OUT.exists(),'fresh closed01 output only; preserve all failures')
    start=time.monotonic();base=full.budget.check();home=source_home();closed=full.source.closed_scratch.verify(full=True);released=full.check_released_inputs(True)
    # Full guards refresh dynamic CAD reservations at phase boundaries. The
    # cheap per-read guard uses the last observed requirements conservatively.
    # CAD growth can only make that cached requirement stricter, never weaker.
    work_required=base['required_free_bytes'];home_snapshot=home
    def cheap():
        require(time.monotonic()-start<DEADLINE,'fixed600s complete archival deadline')
        used=full.source.size(full.budget.DURABLE);require(used<=CAP,'ALL HOME proof copies+archives/metadata under64MiB')
        require(shutil.disk_usage(full.budget.BASE.parent).free>=work_required,'same-volume full work plus activeCAD remaining reserve')
        need=full.source.FLOOR+full.source.SOURCE_CAP-home_snapshot['source_bytes']+full.source.HELPER_CAP-home_snapshot['helper_bytes']+home_snapshot['old_remaining_bytes']+CAP-used
        require(shutil.disk_usage(HERE).free>=need,'HOME2.5GiB plus ALL remaining source/helper/old/new durable and activeCAD allocations')
        full.source.closed_scratch.verify()
    def boundary():
        nonlocal work_required,home_snapshot
        now=full.budget.check();now_home=source_home()
        require(now['own_bytes']==base['own_bytes'],'complete source/model/native work stage frozen')
        require(all(now_home[k]==home[k]for k in ('source_bytes','helper_bytes','closure_helper_bytes','closed_archive','closed_borrow','old_control')),'all frozen source/helper bytes and formal releases unchanged')
        require(full.check_released_inputs()==released,'closed borrow/control/R7 footprints unchanged')
        work_required=now['required_free_bytes'];home_snapshot=now_home;cheap()
    q,groups=snapshot();cheap();OUT.mkdir(parents=True)
    record=dict(state='RUNNING lossless borrowing fullcore archive only',admission=bind(admission),script=bind(__file__),qualified_archive_api=bind(ARCHIVE_API),composite=bind(FULL/'session.json'),model=q['model'],actual_source_list=q['actual_source_list'],groups=groups,archives=[],deadline_seconds=DEADLINE,durable_allocation_bytes=CAP,resource_preflight=base,source_helper_preflight=home,closed_scratch_before=closed,released_reservations_before=released)
    write(OUT/'plan.json',record)
    saved={sig:signal.getsignal(sig)for sig in [signal.SIGALRM,signal.SIGTERM,signal.SIGINT,signal.SIGHUP]}
    def stop(sig,frame):raise TimeoutError('own archive process signal '+str(sig))
    for sig in saved:signal.signal(sig,stop)
    signal.alarm(max(1,int(DEADLINE-(time.monotonic()-start))))
    try:
        for name in('sources','metadata'):
            boundary();record['archives'].append(api.archive_group(OUT/(name+'.tar.gz'),groups[name],cheap))
        for i,row in enumerate(groups['singles']):
            boundary();record['archives'].append(api.archive_one(OUT/('%02d-%s.gz'%(i,Path(row['path']).name)),row,cheap))
        _,after=snapshot();require(after==groups,'ALL consumed/generated/model/2FST/program/proof bytes unchanged');boundary()
        record['closed_scratch_after']=full.source.closed_scratch.verify(full=True);require(record['closed_scratch_after']==closed,'closed old scratch family unchanged')
        record['released_reservations_after']=full.check_released_inputs(True);require(record['released_reservations_after']==released,'ALL formally released occupied bytes unchanged')
        for row in p['inputs']:require(bind(row['path'])==row,'archive source/end unchanged')
        record.update(state='PASS complete lossless borrowing256 trace0 fullcore archive; no cleanup/rerun',elapsed_seconds=time.monotonic()-start,durable_bytes=full.source.size(full.budget.DURABLE),all_required_data_retained=True,scope='Synthetic fullcore correctness/durability only; no all256slot/area/fit/physical/application claim; canonical-borrow matched qualification, not final performance-arm selection. Every earlier failure remains unchanged.')
    except BaseException as error:record.update(state='FAIL archive preserved; no exclusions/extension/cleanup',error=repr(error));raise
    finally:
        signal.alarm(0)
        for sig,handler in saved.items():signal.signal(sig,handler)
        write(OUT/'archive.json',record)
        try:cheap()
        except BaseException as error:record.update(state='FAIL final archive resource/deadline guard preserved',final_guard_error=repr(error));write(OUT/'archive.json',record);raise
        print(OUT/'archive.json',record['state'])
if __name__=='__main__':main()
