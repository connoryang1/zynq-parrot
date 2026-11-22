"""Explicit attempt2 inheritance; original sources/admission/attempt remain immutable."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ADMISSION_SHA = '6566137fc19eacf07fe48cb35ffe7348e4cc9b0d79af58b8ab6b8beb99c2901b'
NATIVE_SHA = '5716c0e35d385ef38ff38ffb2a760a9b7f2f0f27b1cd5c3d1820350a3a929bae'
STOP_SHA = 'cf8cdaa0b987406a1ffaf94a3386fc33b5c562e8dc75add5d7d5af6431b87bcb'
STOP = Path('/home/coyang/fpga-artifacts/context-resume/retained1792-stream-canonical-20261121/stopped-audit01/root-stop.json')
STAGE = Path('/dev/shm/zp-retained1792-stream-canonical-20261121-01')
AUDIT_PHASE = False


def require(ok, message):
    if not ok: raise ValueError(message)


def bind(path):
    path = Path(path).resolve(); digest = hashlib.sha256(); size = 0
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024), b''):
            size += len(data); digest.update(data)
    return dict(path=str(path), bytes=size, sha256=digest.hexdigest())


PINS_SHA = '464655bb0ab8d71971c1362caf96b17edfc3c3e7da36519230a0fb86da7fbd8e'
require(bind(HERE/'original-sources.json')['sha256'] == PINS_SHA, 'fixed original source manifest')
PINS = json.loads((HERE/'original-sources.json').read_text())
for row in PINS: require(bind(row['path']) == row, 'original source drift')
spec = importlib.util.spec_from_file_location('inherited_stream_contract', PINS[0]['path'])
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
# Export original implementation objects, including unchanged reader/Validator.
ORDER, GEOMETRY, CAPS = old.ORDER, old.GEOMETRY, old.CAPS
native, original, archive = old.native, old.original, old.archive
FOUNDATION, resource_phase = old.FOUNDATION, old.resource_phase
runtime_sources, counters_for = old.runtime_sources, old.counters_for


def sources():
    return [bind(HERE/name) for name in ('continuation.py', 'audit_attempt.py',
            'run_continued.py', 'prepare.py', 'original-sources.json')]


def audit_output(stage, role):
    return Path(stage)/(role+'-audit-attempt2' if role == 'd-enabled' else role+'-audit')


def check_stop(path=STOP, check_original=True):
    require(bind(path)['sha256'] == STOP_SHA, 'trusted stopped-attempt anchor')
    stopped = json.loads(Path(path).read_text())
    require(stopped['root_native'] == dict(session=42109, exit_code=0, proof_sha256=NATIVE_SHA), 'inherited actual native PASS')
    require(stopped['root_audit'] == dict(session=25525, exit_code=1,
        failure='contract.py126 HOME preparation/reserve; no fullperaddress acceptance'), 'failed attempt1 remains FAIL')
    for row in stopped['records']:
        require(bind(row['path']) == {k:row[k] for k in ('path','bytes','sha256')}, 'durable stopped record drift')
        if check_original:
            require(bind(row['original']) == dict(path=row['original'], bytes=row['bytes'], sha256=row['sha256']), 'original stopped input changed')
    life = json.loads((Path(path).parent/'d-enabled-audit/reader.owned.json').read_text())
    require(life['returncode'] == -9 and life['owned_group_remaining'] is False, 'failed reader fully reaped')
    require(not (Path(path).parent/'d-enabled-audit/acceptance.json').exists(), 'attempt1 cannot be promoted')
    return stopped


def validate_bridge(b):
    require(b['schema'] == 'retained1792-audit-continuation-v1' and
        b['state'] == 'ROOT-APPROVED audit attempt2; inherited native only', 'explicit new review required')
    require(b['original_preparation'] == dict(path=str(STAGE/'preparation.json'), bytes=9508, sha256=ADMISSION_SHA), 'fixed inherited admission')
    require(b['inherited_native_sha256'] == NATIVE_SHA and b['failed_attempt'] == bind(STOP), 'fixed native/failed-attempt anchors')
    require(b['change'] == dict(phase='read-only audit only', old_HOME_floor=3*1024**3,
        new_HOME_floor=1024**3, native_HOME_floor=3*1024**3), 'only audit HOME floor change')
    require(b['caps'] == CAPS and b['geometry'] == GEOMETRY and b['sources'] == sources(), 'unchanged caps/geometry; exact new sources')


def load(path, expected_sha):
    require(bind(path)['sha256'] == expected_sha and len(expected_sha) == 64, 'external continuation anchor mismatch')
    b = json.loads(Path(path).read_text()); validate_bridge(b)
    require(Path(path).resolve() == STAGE/'audit-continuation.json', 'fixed continuation path')
    check_stop()
    p, program = old.load(b['original_preparation']['path'], ADMISSION_SHA)
    require(p['stage'] == str(STAGE), 'same original stage, not native retry')
    old.check_native(STAGE, 'd-enabled', p, b['original_preparation']['path'], NATIVE_SHA)
    p['_continuation'] = b
    return p, program


def check_native(stage, role, p, preparation_path, expected_sha):
    inherited = role == 'd-enabled'
    if inherited: require(expected_sha == NATIVE_SHA, 'only exact inherited D-on native')
    return old.check_native(stage, role, p,
        p['_continuation']['original_preparation']['path'] if inherited else preparation_path,
        expected_sha)


def check_budget(stage, p):
    # Count failed and current audit attempts TOGETHER against the old32MiB
    # per-role cap. No abandoned output becomes uncharged scratch.
    stage = Path(stage)
    raw = sum(f.stat().st_size for f in stage.glob('*/trace.fst'))
    audits = [sum(f.stat().st_size for d in stage.glob(role+'-audit*')
              for f in d.rglob('*') if f.is_file()) for role in ORDER]
    total = sum(f.stat().st_size for f in stage.rglob('*') if f.is_file())
    require(total <= CAPS['stage_total'] and raw <= CAPS['raw_total'] and sum(audits) <= CAPS['audit_total'] and total-raw-sum(audits) <= CAPS['other_total'], 'fixed sum/phase budget')
    require(all(f.stat().st_size <= CAPS['raw_per_case'] for f in stage.glob('*/trace.fst')) and all(n <= CAPS['audit_per_case'] for n in audits), 'fixed per-case budget including failed attempt')
    require(shutil.disk_usage(stage).free >= CAPS['RAM_reserve']+CAPS['stage_total']-total, 'RAM1GiB plus remaining stage')
    prep_bytes = sum(f.stat().st_size for root in (HERE,old.HERE) for f in root.rglob('*') if f.is_file())
    floor = 1024**3 if AUDIT_PHASE else CAPS['HOME_reserve']
    require(prep_bytes <= CAPS['preparation'] and shutil.disk_usage(HERE).free >= floor+CAPS['preparation'], 'HOME preparation/reserve (audit1GiB; native3GiB)')


def verify_audit(stage, role, p, preparation_path, expected_sha):
    out=audit_output(stage,role); accepted=out/'acceptance.json'
    require(bind(accepted)['sha256'] == expected_sha, 'external audit acceptance anchor mismatch')
    receipt=json.loads(accepted.read_text())
    require(receipt['attempt'] == (2 if role == 'd-enabled' else 1) and receipt['inherited_native'] == (role == 'd-enabled'), 'explicit new attempt/native inheritance')
    require(receipt['schema'] == 'retained1792-stream-continuation-acceptance-v1' and receipt['role'] == role, 'new exact audit role')
    require(receipt['preparation'] == bind(preparation_path) and receipt['sources'] == p['runtime_sources'], 'trusted source/admission set')
    run=check_native(stage,role,p,preparation_path,receipt['native_sha256'])
    expected_names=('verification.json','selection.tsv','gp0-counter-projection.tsv.gz','counter-check-input/verification.json','counter-words.json','counter-checker.log','counter-checker.owned.json','reader.stderr','reader.owned.json')
    require(receipt['files'] == [bind(out/name) for name in expected_names], 'all archive paths fixed inside owned case; no unsigned path redirection')
    full=json.loads((out/'verification.json').read_text()); adapter_path=out/'counter-check-input/verification.json';adapter=json.loads(adapter_path.read_text());counter=json.loads((out/'counter-words.json').read_text())
    require(full['state'].startswith('PASS') and full['lane'] == role[0] and full['lines'] == 1792 and full['sets'] == 256 and len(full['targets']) == 1792, 'full configured targets')
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
