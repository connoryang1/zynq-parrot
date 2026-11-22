"""Copied pure completed-receipt validators only; never import producer contracts."""
import hashlib,json
from pathlib import Path
FOUNDATION=[]
def require(v,m):
 if not v:raise ValueError(m)
def bind(path):
 p=Path(path);h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())
def verify(r):require(bind(r['path'])==r,'literal recorded input changed '+r['path'])
def counters_for(role):return [0,256,0,256,0,2048] if role=='d-enabled' else [256,0,256,0,2048,0] if role=='i-enabled' else [0]*6

def semantic_check_native(stage, role, p, preparation_path, expected_sha):
    case=Path(stage)/role; path=case/'verification.json'
    require(bind(path)['sha256'] == expected_sha, 'external native-proof anchor mismatch')
    run=json.loads(path.read_text()); require(run['role'] == role and run['state'].startswith('PASS'), 'complete exact native role')
    require(run['counters'] == counters_for(role), 'all actual GP0 counters exact/nonsaturated')
    require(run['admission'] == bind(case/'admission.json'), 'fixed native admission path')
    ad=json.loads((case/'admission.json').read_text())
    require(ad['preparation'] == bind(preparation_path) and ad['model'] == p['model'] and ad['program'] == p['program'], 'native exact approved inputs')
    require(ad['schema'] == 'csr-unmasked256-capacity-stream-native-v1' and ad['role'] == role, 'new native schema')
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
    require(receipt['schema'] == 'csr-unmasked256-stream-acceptance-v1' and receipt['role'] == role, 'new exact audit role')
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
