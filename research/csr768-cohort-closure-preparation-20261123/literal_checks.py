"""Exact current768 receipt checks; only bind-to-binding name adaptation."""
import json,hashlib
from pathlib import Path

def require(v,m):
    if not v:raise ValueError(m)


def binding(p):
    p=Path(p);h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def verify(r):require(binding(r['path'])=={k:r[k]for k in ('path','bytes','sha256')},'frozen binding '+r['path'])


FOUNDATION=[dict(path="/home/coyang/zynq-parrot-retained-observation/testing/rtl/retained-capacity-fixture/check_counter_words.py",bytes=2177,sha256="7286e6db5300f5f458cc26d245b37d3e677fb5ad2691684b345a0c9c3dc17892")]

def counters_for(role):return [0,768,0,768,0,6144] if role=='d-enabled' else [768,0,768,0,6144,0] if role=='i-enabled' else [0]*6


def semantic_check_native(stage, role, p, preparation_path, expected_sha):
    case=Path(stage)/role; path=case/'verification.json'
    require(binding(path)['sha256'] == expected_sha, 'external native-proof anchor mismatch')
    run=json.loads(path.read_text()); require(run['role'] == role and run['state'].startswith('PASS'), 'complete exact native role')
    require(run['counters'] == counters_for(role), 'all actual GP0 counters exact/nonsaturated')
    require(run['admission'] == binding(case/'admission.json'), 'fixed native admission path')
    ad=json.loads((case/'admission.json').read_text())
    require(ad['preparation'] == binding(preparation_path) and ad['model'] == p['model'] and ad['program'] == p['program'], 'native exact approved inputs')
    require(ad['schema'] == 'csr-unmasked768-capacity-stream-native-v1' and ad['role'] == role, 'new native schema')
    require(ad['reader'] == p['reader'] and ad['compiled_sources'] == p['compiled_sources'], 'native reader/source identity')
    expected=[binding(case/name) for name in ('prog.riscv','prog.nbf','run.log','process.json','trace.fst')]
    require(run['files'] == expected, 'native fixed file paths and hashes')
    require(ad['elf'] == binding(case/'prog.riscv') and ad['nbf'] == binding(case/'prog.nbf'), 'actual loaded inputs')
    program=json.loads(Path(p['program']['path']).read_text())
    require(ad['elf']['sha256'] == program['elf']['sha256'] and ad['nbf']['sha256'] == program['cases'][role]['nbf']['sha256'], 'loaded fixture bytes')
    require(json.loads(Path(ad['runtime_sources']['path']).read_text()) == p['runtime_sources'] and ad['runtime_sources'] == binding(Path(stage)/'runtime-sources.json'), 'exact runtime snapshot')
    return run


def check_native(stage,role,p,preparation_path,expected_sha):
    run=semantic_check_native(stage,role,p,preparation_path,expected_sha)
    out=Path(stage)/role
    require(run['resource_phase']==binding(out/'resource-phase.json') and run['sealed_inputs']==binding(out/'sealed-exit.json'),'native PASS requires actual resource/sealed closure')
    check_phase_receipts(out)
    return run


def check_phase_receipts(out):
    sealed=json.loads((out/'sealed-exit.json').read_text());require(sealed['state']=='PASS all sealed inactive bytes/inventories unchanged','all original input bytes unchanged')
    verify(sealed['inventory'])
    life=json.loads((out/'resource-phase.json').read_text())
    require(life['parent_pipe_serialized'] is True and life['monitor_kind']=='separate-owned-process' and life['returncode']==0 and life['owned_group_remaining'] is False,'accepted RO04 accounting process plus serialized parent Pipe')
    require(life['failure'] is None and life['interval_s']==1 and life['scan_duration_limit_s']==2 and life['poll_gap_limit_s']==5 and life['snapshot_age_limit_s']==5 and life['initial_snapshot_limit_s']==5 and life['max_poll_gap_s']<=5 and life['max_scan_seconds']<=2 and life['max_callback_age_s']<=5 and life['teardown_bound_s']==5,'exact ROOT03 bounded host cadence; all byte/semantic caps unchanged')

def semantic_verify_audit(stage, role, p, preparation_path, expected_sha):
    out=Path(stage)/(role+'-audit'); accepted=out/'acceptance.json'
    require(binding(accepted)['sha256'] == expected_sha, 'external audit acceptance anchor mismatch')
    receipt=json.loads(accepted.read_text())
    require(receipt['schema'] == 'csr-unmasked768-stream-acceptance-v1' and receipt['role'] == role, 'new exact audit role')
    require(receipt['preparation'] == binding(preparation_path) and receipt['sources'] == p['runtime_sources'], 'trusted source/admission set')
    run=check_native(stage,role,p,preparation_path,receipt['native_sha256'])
    expected_names=('verification.json','selection.tsv','gp0-counter-projection.tsv.gz','counter-check-input/verification.json','counter-words.json','counter-checker.log','counter-checker.owned.json','reader.stderr','reader.owned.json')
    require(receipt['files'] == [binding(out/name) for name in expected_names], 'all archive paths fixed inside owned case; no unsigned path redirection')
    full=json.loads((out/'verification.json').read_text()); adapter_path=out/'counter-check-input/verification.json';adapter=json.loads(adapter_path.read_text());counter=json.loads((out/'counter-words.json').read_text())
    require(full['state'].startswith('PASS') and full['lane'] == role[0] and full['lines'] == 768 and full['actual_count_summary']['sets'] == 256 and len(full['targets']) == 768, 'full configured targets')
    require(binding(out/'selection.tsv')['sha256'] == '2c38d34248a066f58ed9526784955dab7d0b23b1cc15b240129530ec1f81086c', 'exact raw167 selection bytes')
    require(full['bindings'] == dict(fst=binding(Path(stage)/role/'trace.fst'), run=binding(Path(stage)/role/'verification.json'), admission=binding(Path(stage)/role/'admission.json'), program=p['program'], model=p['model'], reader=p['reader'], selection=binding(out/'selection.tsv'), preparation=binding(preparation_path)), 'exact complete proof provenance')
    archive_info=full['archive'];projection=binding(out/'gp0-counter-projection.tsv.gz')
    require(archive_info['counter_projection'] == projection and archive_info['schema'] == 'full167-digest-explicit-counter-projection-v1', 'projection cannot impersonate full167 events')
    stream=archive_info['full_stream'];require(stream['reader_returncode'] == 0 and stream['exact_end_records'] == 1 and stream['lines'] == stream['events']+169 and stream['bytes']>0 and len(stream['sha256']) == 64, 'complete full167 stream digest/count receipt')
    require(adapter == dict(schema='counter-projection-input-only-v1', full_audit=binding(out/'verification.json'), bindings=dict(events=projection,run=binding(Path(stage)/role/'verification.json'))), 'exact adapter to full proof chain')
    checker=next(r for r in FOUNDATION if r['path'].endswith('/check_counter_words.py'))
    require(counter['state'] == 'PASS final FST counter words equal actual GP0 reads' and counter['values'] == run['counters'] and counter['auditor'] == checker and counter['audit'] == binding(adapter_path) and counter['run'] == adapter['bindings']['run'] and counter['events'] == projection, 'unchanged checker source/state/all six values and adapter chain')
    life=json.loads((out/'reader.owned.json').read_text());require(life['returncode'] == 0 and life['failure'] is None and life['owned_group_remaining'] is False, 'actual reader0 and owned cleanup')
    require(life['argv'] == [p['reader']['path'],str(Path(stage)/role/'trace.fst'),str(out/'selection.tsv')], 'actual complete reader invocation')
    require(life['guard_interval_s']==1 and life['poll_gap_limit_s']==5 and life['max_observed_poll_gap_s']<=5 and life['teardown_bound_s']==5,'same03 bounded reader host guard cadence')
    counter_life=json.loads((out/'counter-checker.owned.json').read_text())
    require(counter_life['returncode'] == 0 and counter_life['failure'] is None and counter_life['owned_group_remaining'] is False, 'counter checker actual0 and bounded cleanup')
    return receipt

def verify_audit(stage,role,p,preparation_path,expected_sha):
    receipt=semantic_verify_audit(stage,role,p,preparation_path,expected_sha)
    out=Path(stage)/(role+'-audit')
    require(receipt['resource_phase']==binding(out/'resource-phase.json') and receipt['sealed_inputs']==binding(out/'sealed-exit.json'),'source-bound actual phase/sealed receipts')
    check_phase_receipts(out)
    return receipt
