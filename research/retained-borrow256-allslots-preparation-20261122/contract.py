"""New matched borrowing256 cohort; frozen semantic Validator and complete streams."""
import importlib.util,json,sys,shutil
from pathlib import Path
from contextlib import contextmanager
import bridge
HERE=Path(__file__).resolve().parent
BASE=bridge.COHORT
SOURCE=bridge.SOURCE
PRIOR=Path('/home/coyang/fpga-artifacts/context-resume/retained256-scoped-allslots-20261122/preparation01/profile256.py')
require,bind,verify=bridge.require,bridge.bind,bridge.verify
require(bind(PRIOR)['sha256']=='1830d5ba237e7ff84bfbd4cb33d2527ec8b85878f1d7facfccb9524a618779fb','fixed prior256 semantic profile bytes')
sys.path.insert(0,str(PRIOR.parent))
spec=importlib.util.spec_from_file_location('prior256_semantics',PRIOR)
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
old,native,original,archive=prior.old,prior.native,prior.original,prior.archive
FOUNDATION=prior.FOUNDATION
TRANSITIVE=[Path(m.__file__)for m in list(sys.modules.values()) if getattr(m,'__file__',None) and str(m.__file__).startswith('/home/coyang/') and str(m.__file__).endswith('.py')]
Validator=prior.Validator
ORDER=prior.ORDER
GEOMETRY=dict(prior.GEOMETRY,cache_miss_trace=0)
PREFLIGHT=bridge.POOL/'allslots-resource-preflight01.json'
CAPS={}
ACTIVE_GUARD=None


def caps(allocation):
    require(allocation in (128*1024**2,256*1024**2),'prospective pool subdivision only')
    small=allocation==128*1024**2
    return dict(old.CAPS,raw_per_case=(30 if small else 64)*1024**2,raw_total=(90 if small else 192)*1024**2,
                audit_per_case=(8 if small else 16)*1024**2,audit_total=(24 if small else 48)*1024**2,
                other_total=(14 if small else 16)*1024**2,stage_total=allocation,preparation=1024**2,HOME_reserve=2560*1024**2)


def runtime_sources():
    local=[bind(p)for p in sorted(HERE.glob('*.py'))]
    # Preserve the exact previously qualified semantic/transitive modules even
    # though this cohort does not call their historical model admission path.
    paths=[PRIOR,*[Path(r['path'])for r in prior.runtime_sources()]]
    paths+=TRANSITIVE+list(bridge.PREP.glob('*.py'))+[SOURCE/'testing/check_run.py',SOURCE/'testing/rtl/retained-advisory-trace/validate.py']
    return sorted({r['path']:r for r in local+[bind(p)for p in paths]}.values(),key=lambda r:r['path'])


def load(path,expected_sha):
    global CAPS
    require(bind(path)['sha256']==expected_sha and Path(path)==BASE/'preparation.json','external fixed new cohort preparation')
    p=json.loads(Path(path).read_text())
    require(p['schema']=='borrow256-complete-allslots-v1' and p['state']=='ROOT-PREPARED actual qualified borrowing256; native/audit only after explicit ROOT execution','new prospective cohort schema')
    verify(p['resource_preflight']);q=json.loads(PREFLIGHT.read_text())
    require(p['resource_preflight']==bind(PREFLIGHT) and q['script']['sha256']=='0d609bc3bf008970e932e2c2f5b98e89e26b3fabb9d378c5d76fe654ff473519','exact reviewed prospective split')
    CAPS=caps(q['prospective_cohort_bytes'])
    require(p['caps']==CAPS and p['geometry']==GEOMETRY and p['schedule']==list(ORDER),'fixed capacity/ordinary geometry/schedule/phase caps')
    require(p['runtime_sources']==runtime_sources(),'exact new/foundation/transitive runtime sources')
    for row in p['runtime_sources']:verify(row)
    from_bridge=bridge.read()
    require(p['model_bridge']==from_bridge and p['model']==from_bridge['model'],'actual new qualification, not old source/model approval')
    require(p['environment']==from_bridge['environment'] and p['linked_libraries']==from_bridge['linked_libraries'] and p['reader']==from_bridge['reader'],'same runtime/actual libraries/reader')
    verify(p['compiled_sources']);require(json.loads(Path(p['compiled_sources']['path']).read_text())==from_bridge['compiled_sources'],'all396 actual compiled inputs')
    original.source_bindings(Path(p['compiled_sources']['path']))
    st=BASE.stat();require(p['stage_identity']==dict(path=str(BASE),device=st.st_dev,inode=st.st_ino),'actual fixed ROOT cohort namespace')
    require(BASE.parent==bridge.POOL and st.st_dev==bridge.POOL.stat().st_dev!=HERE.stat().st_dev,'inside existing768MiB ROOT pool, no HOME borrowing')
    require(p['program']['sha256']=='88546c8afc17c482e42cb731459f44c2a40f2f6aeee2c172321534c872dabd72','unchanged max1792 program manifest')
    verify(p['program']);program=json.loads(Path(p['program']['path']).read_text())
    require(program['elf']['sha256']=='062a3dd884d64bc1fdf7f0048f312cc5efc84280eb89006c21ef6b60f1f43ed6' and program['max_lines']==1792 and program['max_sets']==256,'unchanged geometry-aware ELF and bounds')
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



def counters_for(role):return [0,256,0,256,0,2048] if role=='d-enabled' else [256,0,256,0,2048,0] if role=='i-enabled' else [0]*6

def semantic_check_native(stage, role, p, preparation_path, expected_sha):
    case=Path(stage)/role; path=case/'verification.json'
    require(bind(path)['sha256'] == expected_sha, 'external native-proof anchor mismatch')
    run=json.loads(path.read_text()); require(run['role'] == role and run['state'].startswith('PASS'), 'complete exact native role')
    require(run['counters'] == counters_for(role), 'all actual GP0 counters exact/nonsaturated')
    require(run['admission'] == bind(case/'admission.json'), 'fixed native admission path')
    ad=json.loads((case/'admission.json').read_text())
    require(ad['preparation'] == bind(preparation_path) and ad['model'] == p['model'] and ad['program'] == p['program'], 'native exact approved inputs')
    require(ad['schema'] == 'borrow256-capacity-stream-native-v1' and ad['role'] == role, 'new native schema')
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
    require(receipt['schema'] == 'borrow256-stream-acceptance-v1' and receipt['role'] == role, 'new exact audit role')
    require(receipt['preparation'] == bind(preparation_path) and receipt['sources'] == p['runtime_sources'], 'trusted source/admission set')
    run=check_native(stage,role,p,preparation_path,receipt['native_sha256'])
    expected_names=('verification.json','selection.tsv','gp0-counter-projection.tsv.gz','counter-check-input/verification.json','counter-words.json','counter-checker.log','counter-checker.owned.json','reader.stderr','reader.owned.json')
    require(receipt['files'] == [bind(out/name) for name in expected_names], 'all archive paths fixed inside owned case; no unsigned path redirection')
    full=json.loads((out/'verification.json').read_text()); adapter_path=out/'counter-check-input/verification.json';adapter=json.loads(adapter_path.read_text());counter=json.loads((out/'counter-words.json').read_text())
    require(full['state'].startswith('PASS') and full['lane'] == role[0] and full['lines'] == 256 and full['sets'] == 256 and len(full['targets']) == 256, 'full configured targets')
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
