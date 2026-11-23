"""New1280 source-bound native/stream contract; no historical producer imports."""
import importlib.util,json,os,sys
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
import bridge
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
BASE,SOURCE=bridge.COHORT,bridge.SOURCE
require,bind,verify=bridge.require,bridge.bind,bridge.verify
ORDER=('d-enabled','d-off','i-enabled')
CAPS=dict(raw_per_case=24*1024**2,raw_total=72*1024**2,audit_per_case=8*1024**2,audit_total=24*1024**2,other_total=24*1024**2,stage_total=128*1024**2,preparation=128*1024,HOME_reserve=1792*1024**2,reader_s=3600,audit_outer_s=3665)
ACTIVE_GUARD=None
CONTEXT=None


def module(path,name,sha):
    require(bind(path)['sha256']==sha,'pinned import '+str(path))
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


# Local pure extraction has no old ROOT, allocation or checker imports.
import foundation
OWNER=module('/home/coyang/zynq-parrot-linux-host-observer/research/retained256-qualification-20261122/software_owned_v2.py','csr1280_owned','52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5')
archive=module('/home/coyang/zynq-parrot-linux-host-observer/research/retained-stream-archive-20261121/archive_stream.py','csr1280_fullstream','15a7aa77dc67c42a3c9c30e1c5ae317b23a643b9fae086977166bf1e19e63a0e')


def owned_run(command,cwd,env,log_path,timeout,limits,guard,allowance):
    def guarded():
        guard();require(allowance()>0,'bounded other/log output,64KiB cleanup reserve')
    life=None
    try:
        with Path(log_path).open('wb') as log:life=OWNER.run(command,cwd,env,log,timeout,guarded,limits)
    except BaseException as error:
        life=getattr(error,'owned_receipt',None)
        raise
    finally:
        if life is not None:archive.write_json(Path(log_path).with_suffix('.owned.json'),life)
    return SimpleNamespace(returncode=life['returncode'])


native=SimpleNamespace(primary_counts=foundation.primary_counts,verify_coverage=foundation.verify_coverage,owned_run=owned_run)
FOUNDATION=[dict(path='/home/coyang/zynq-parrot-retained-observation/testing/rtl/retained-capacity-fixture/check_counter_words.py',bytes=2177,sha256='7286e6db5300f5f458cc26d245b37d3e677fb5ad2691684b345a0c9c3dc17892')]
original=SimpleNamespace(guarded_reader=foundation.guarded_reader)


def runtime_sources():
    plan=json.loads((HERE/'source-plan.json').read_text())
    result=[]
    require(plan['local_python_files']==sorted(r['path'].rsplit('/',1)[-1]for r in plan['local_python_sources']),'literal local source membership')
    for row in plan['local_python_sources']:
        require(Path(row['path']).parent==HERE,'local source namespace');verify(row);result.append(row)
    for row in plan['external_sources']:
        verify(row);result.append(row)
    return sorted({r['path']:r for r in result}.values(),key=lambda r:r['path'])


def context(path,sha):
    global CONTEXT
    plan=json.loads((HERE/'source-plan.json').read_text());root=Path(plan['semantic_prefix'])
    for row in plan['semantic_sources']:verify(row)
    sys.path.insert(0,str(root))
    sem=module(root/'csr1280_profile.py','csr1280_explicit_semantics',plan['semantic_profile_sha256'])
    ctx=sem.load_context(path,sha)
    require(ctx.anchors['model']['sha256']==bridge.SCOPED_SHA,'current qualified bc6f, no historical replacement')
    CONTEXT=SimpleNamespace(sem=sem,ctx=ctx,profile=sem.geometry(1280,256))
    original.audit=SimpleNamespace(selection=lambda:ctx.selected,edges=sem.edges)
    original.source_bindings=ctx.strict.source_bindings
    return CONTEXT


def Validator(program,role):
    require(CONTEXT is not None,'load exact reviewed context first')
    return CONTEXT.sem.Validator(program,role,CONTEXT.profile,CONTEXT.ctx)


def load(path,expected_sha):
    require(bind(path)['sha256']==expected_sha and Path(path)==BASE/'preparation.json','exact standalone preparation')
    p=json.loads(Path(path).read_text())
    require(p['schema']=='csr1280-complete-allslots-v1' and p['state']=='ROOT-PREPARED new1280 actual model; native/audit only after explicit execution','DRAFT cannot run')
    require(p['caps']==CAPS and p['schedule']==list(ORDER),'fixed predeclared role order and caps')
    require(p['runtime_sources']==runtime_sources(),'literal source membership, no sys.modules expansion')
    for row in p['runtime_sources']:verify(row)
    verify(p['source_plan']);require(p['source_plan']==bind(HERE/'source-plan.json'),'exact packet')
    verify(p['semantic_context']);ctx=context(p['semantic_context']['path'],p['semantic_context']['sha256'])
    authority=bridge.read(p['ROOT_authority'],p['semantic_context']['path'])
    require(p['model']==authority['model']==ctx.ctx.anchors['model'],'all source/full/scoped/STD/base lineage')
    require(p['geometry']==ctx.ctx.anchors['actual_geometry17'],'actual17fields1280/sets256/epoch8/trace0')
    import fixed_shared
    policy=fixed_shared.load(p['fixed_reservations']['path'],p['fixed_reservations']['sha256'])
    require(policy['base_closure']==authority['base_closure'],'same closed base/resource anchors')
    proposal=json.loads(Path(ctx.ctx.anchors['closed_anchors']['proposal']['path']).read_text())
    require(p['environment']==proposal['environment'] and p['linked_libraries']==proposal['linked_libraries'] and p['reader']==proposal['reader'],'exact qualified loader/environment/libraries')
    verify(p['reader'])
    for row in p['linked_libraries']:verify(row)
    verify(p['compiled_sources']);raw=json.loads(Path(p['compiled_sources']['path']).read_text())
    require(raw==proposal['compiled_sources'],'every actual compiled source')
    for row in raw.values():verify(row)
    original.source_bindings(Path(p['compiled_sources']['path']))
    st=BASE.stat();require(p['stage_identity']==dict(path=str(BASE),device=st.st_dev,inode=st.st_ino),'actual fresh stage inode')
    require(BASE!=bridge.ORIGINAL_POOL and bridge.ORIGINAL_POOL not in BASE.parents and st.st_dev!=HERE.stat().st_dev,'separate RUN allocation, no sealed-pool/HOME output')
    require(p['program']==ctx.ctx.anchors['programs']['single']['manifest'],'exact immutable MAX1792 manifest')
    verify(p['program']);program=json.loads(Path(p['program']['path']).read_text())
    require(program['elf']['sha256']=='062a3dd884d64bc1fdf7f0048f312cc5efc84280eb89006c21ef6b60f1f43ed6' and program['max_lines']==1792 and program['max_sets']==256,'same runtime-geometry program')
    for row in program['sources']+[program['elf'],program['compiler'],program['converter']]+[program['cases'][role]['nbf']for role in ORDER]:verify(row)
    return p,program


def check_budget(stage,p):
    if ACTIVE_GUARD is not None:return ACTIVE_GUARD()
    import ledger
    return ledger.boundary(stage,p)


@contextmanager
def resource_phase(stage,p,out,receipt):
    global ACTIVE_GUARD
    import ledger
    account=ledger.Ledger(stage,p,out,runtime_sources())
    try:
        with account.phase(receipt) as guard:
            ACTIVE_GUARD=guard
            yield guard
    finally:ACTIVE_GUARD=None


def counters_for(role):return [0,1280,0,1280,0,10240] if role=='d-enabled' else [1280,0,1280,0,10240,0] if role=='i-enabled' else [0]*6


def semantic_check_native(stage, role, p, preparation_path, expected_sha):
    case=Path(stage)/role; path=case/'verification.json'
    require(bind(path)['sha256'] == expected_sha, 'external native-proof anchor mismatch')
    run=json.loads(path.read_text()); require(run['role'] == role and run['state'].startswith('PASS'), 'complete exact native role')
    require(run['counters'] == counters_for(role), 'all actual GP0 counters exact/nonsaturated')
    require(run['admission'] == bind(case/'admission.json'), 'fixed native admission path')
    ad=json.loads((case/'admission.json').read_text())
    require(ad['preparation'] == bind(preparation_path) and ad['model'] == p['model'] and ad['program'] == p['program'], 'native exact approved inputs')
    require(ad['schema'] == 'csr-unmasked1280-capacity-stream-native-v1' and ad['role'] == role, 'new native schema')
    require(ad['reader'] == p['reader'] and ad['compiled_sources'] == p['compiled_sources'], 'native reader/source identity')
    expected=[bind(case/name) for name in ('prog.riscv','prog.nbf','run.log','process.json','trace.fst')]
    require(run['files'] == expected, 'native fixed file paths and hashes')
    require(ad['elf'] == bind(case/'prog.riscv') and ad['nbf'] == bind(case/'prog.nbf'), 'actual loaded inputs')
    program=json.loads(Path(p['program']['path']).read_text())
    require(ad['elf']['sha256'] == program['elf']['sha256'] and ad['nbf']['sha256'] == program['cases'][role]['nbf']['sha256'], 'loaded fixture bytes')
    require(json.loads(Path(ad['runtime_sources']['path']).read_text()) == p['runtime_sources'] and ad['runtime_sources'] == bind(Path(stage)/'runtime-sources.json'), 'exact runtime snapshot')
    return run


def check_native(stage,role,p,preparation_path,expected_sha):
    run=semantic_check_native(stage,role,p,preparation_path,expected_sha)
    out=Path(stage)/role
    require(run['resource_phase']==bind(out/'resource-phase.json') and run['sealed_inputs']==bind(out/'sealed-exit.json'),'native PASS requires actual resource/sealed closure')
    check_phase_receipts(out)
    return run


def check_phase_receipts(out):
    sealed=json.loads((out/'sealed-exit.json').read_text());require(sealed['state']=='PASS all sealed inactive bytes/inventories unchanged','all original input bytes unchanged')
    verify(sealed['inventory'])
    life=json.loads((out/'resource-phase.json').read_text())
    require(life['parent_pipe_serialized'] is True and life['monitor_kind']=='separate-owned-process' and life['returncode']==0 and life['owned_group_remaining'] is False,'accepted RO04 accounting process plus serialized parent Pipe')
    require(life['failure'] is None and life['poll_gap_limit_s']==1 and life['max_poll_gap_s']<=1 and life['max_scan_seconds']<=.5,'same1s polling guard no waiver')

def semantic_verify_audit(stage, role, p, preparation_path, expected_sha):
    out=Path(stage)/(role+'-audit'); accepted=out/'acceptance.json'
    require(bind(accepted)['sha256'] == expected_sha, 'external audit acceptance anchor mismatch')
    receipt=json.loads(accepted.read_text())
    require(receipt['schema'] == 'csr-unmasked1280-stream-acceptance-v1' and receipt['role'] == role, 'new exact audit role')
    require(receipt['preparation'] == bind(preparation_path) and receipt['sources'] == p['runtime_sources'], 'trusted source/admission set')
    run=check_native(stage,role,p,preparation_path,receipt['native_sha256'])
    expected_names=('verification.json','selection.tsv','gp0-counter-projection.tsv.gz','counter-check-input/verification.json','counter-words.json','counter-checker.log','counter-checker.owned.json','reader.stderr','reader.owned.json')
    require(receipt['files'] == [bind(out/name) for name in expected_names], 'all archive paths fixed inside owned case; no unsigned path redirection')
    full=json.loads((out/'verification.json').read_text()); adapter_path=out/'counter-check-input/verification.json';adapter=json.loads(adapter_path.read_text());counter=json.loads((out/'counter-words.json').read_text())
    require(full['state'].startswith('PASS') and full['lane'] == role[0] and full['lines'] == 1280 and full['sets'] == 256 and len(full['targets']) == 1280, 'full configured targets')
    require(bind(out/'selection.tsv')['sha256'] == '2c38d34248a066f58ed9526784955dab7d0b23b1cc15b240129530ec1f81086c', 'exact raw167 selection bytes')
    require(full['bindings'] == dict(fst=bind(Path(stage)/role/'trace.fst'), run=bind(Path(stage)/role/'verification.json'), admission=bind(Path(stage)/role/'admission.json'), program=p['program'], model=p['model'], reader=p['reader'], selection=bind(out/'selection.tsv'), preparation=bind(preparation_path)), 'exact complete proof provenance')
    archive_info=full['archive'];projection=bind(out/'gp0-counter-projection.tsv.gz')
    require(archive_info['counter_projection'] == projection and archive_info['schema'] == 'full167-digest-explicit-counter-projection-v1', 'projection cannot impersonate full167 events')
    stream=archive_info['full_stream'];require(stream['reader_returncode'] == 0 and stream['exact_end_records'] == 1 and stream['lines'] == stream['events']+169 and stream['bytes']>0 and len(stream['sha256']) == 64, 'complete full167 stream digest/count receipt')
    require(adapter == dict(schema='counter-projection-input-only-v1', full_audit=bind(out/'verification.json'), bindings=dict(events=projection,run=bind(Path(stage)/role/'verification.json'))), 'exact adapter to full proof chain')
    checker=next(r for r in FOUNDATION if r['path'].endswith('/check_counter_words.py'))
    require(counter['state'] == 'PASS final FST counter words equal actual GP0 reads' and counter['values'] == run['counters'] and counter['auditor'] == checker and counter['audit'] == bind(adapter_path) and counter['run'] == adapter['bindings']['run'] and counter['events'] == projection, 'unchanged checker source/state/all six values and adapter chain')
    life=json.loads((out/'reader.owned.json').read_text());require(life['returncode'] == 0 and life['failure'] is None and life['owned_group_remaining'] is False, 'actual reader0 and owned cleanup')
    require(life['argv'] == [p['reader']['path'],str(Path(stage)/role/'trace.fst'),str(out/'selection.tsv')], 'actual complete reader invocation')
    counter_life=json.loads((out/'counter-checker.owned.json').read_text())
    require(counter_life['returncode'] == 0 and counter_life['failure'] is None and counter_life['owned_group_remaining'] is False, 'counter checker actual0 and bounded cleanup')
    return receipt

def verify_audit(stage,role,p,preparation_path,expected_sha):
    receipt=semantic_verify_audit(stage,role,p,preparation_path,expected_sha)
    out=Path(stage)/(role+'-audit')
    require(receipt['resource_phase']==bind(out/'resource-phase.json') and receipt['sealed_inputs']==bind(out/'sealed-exit.json'),'source-bound actual phase/sealed receipts')
    check_phase_receipts(out)
    return receipt
