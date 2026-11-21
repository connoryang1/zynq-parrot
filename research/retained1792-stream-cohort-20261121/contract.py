"""Fixed software/schema contract; future model admission is an external trust anchor."""
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'retained-capacity1792-runner-20261121'
STREAM = HERE.parent / 'retained-stream-archive-20261121'
ORDER = ('d-enabled', 'd-off', 'i-enabled')
GEOMETRY = dict(i_lines=1792, d_lines=1792, sets=256, line_bytes=64,
                ordinary_sets=64, ordinary_ways=8, l2_bytes=16384,
                observe=1, delay=0, num_threads=2, num_contexts=4)
CAPS = dict(raw_per_case=128*1024**2, raw_total=384*1024**2,
            audit_per_case=32*1024**2, audit_total=96*1024**2,
            other_total=32*1024**2, stage_total=512*1024**2,
            preparation=8*1024**2, HOME_reserve=3*1024**3,
            RAM_reserve=1024**3, native_ms=1800000,
            native_outer_s=1980, reader_s=3600, audit_outer_s=3665, cleanup_s=5)
MODEL_CHECKS = ('canonical_fullcore_closed', 'canonical_source_inputs_exact',
                'trace_only_eval_identity', 'schema167_exact',
                'geometry1792_256_static16k', 'strict512_8writes_16I',
                'observer_counters', 'assert_scope_bound')


def require(ok, message):
    if not ok: raise ValueError(message)


def bind(path):
    path = Path(path).resolve(); digest = hashlib.sha256(); size = 0
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024), b''):
            size += len(data); digest.update(data)
    return dict(path=str(path), bytes=size, sha256=digest.hexdigest())


def verify(record):
    require(bind(record['path']) == record, 'binding changed: ' + record['path'])


# Check the exact old modules BEFORE imports, not a caller-provided source list.
require(bind(HERE/'foundation.json')['sha256'] == '14c3f9c3284ebe823f6b9b0a5bdf27a2cfa27fb88938ba461ef90f1b906e19b5', 'fixed foundation manifest')
FOUNDATION = json.loads((HERE/'foundation.json').read_text())
for record in FOUNDATION: verify(record)
OLD = Path(next(r['path'] for r in FOUNDATION if r['path'].endswith('/run1792.py'))).parent
STREAM = Path(next(r['path'] for r in FOUNDATION if r['path'].endswith('/archive_stream.py'))).parent
sys.path.insert(0, str(OLD))
native = importlib.import_module('run1792')
original = importlib.import_module('audit1792')
sys.path.insert(0, str(STREAM))
archive = importlib.import_module('archive_stream')
resource_phase = importlib.import_module('budget1792').resource_phase


def runtime_sources():
    local = [HERE/name for name in ('contract.py', 'run_stream1792.py', 'audit_stream1792.py', 'foundation.json')]
    return [bind(p) for p in local] + FOUNDATION


def load(path, expected_sha, approved=True):
    require(isinstance(expected_sha, str) and len(expected_sha) == 64, 'external admission SHA required')
    require(bind(path)['sha256'] == expected_sha, 'external admission anchor mismatch')
    p = json.loads(Path(path).read_text())
    require(p['schema'] == 'retained1792-stream-cohort-v1' and p['schedule'] == list(ORDER), 'new fixed cohort contract')
    require(p['geometry'] == GEOMETRY and p['caps'] == CAPS, 'fixed geometry/budgets')
    actual_sources = runtime_sources()
    if approved:
        require(p['state'] == 'ROOT-APPROVED future1792-stream complete-audit', 'DRAFT UNLAUNCHABLE')
        require(p['runtime_sources'] == actual_sources, 'exact source set, bytes and paths')
    else:
        # A pending draft may be reviewed from a relocated checkout. Executable
        # admission above always binds actual paths; draft review binds bytes.
        def identities(rows):
            return [(Path(r['path']).name,r['bytes'],r['sha256']) for r in rows[:4]] + rows[4:]
        require(identities(p['runtime_sources']) == identities(actual_sources), 'exact source set and bytes for pending draft')
    require(p['program']['sha256'] == '88546c8afc17c482e42cb731459f44c2a40f2f6aeee2c172321534c872dabd72', 'unchanged1792 fixture manifest')
    verify(p['program']); program = json.loads(Path(p['program']['path']).read_text())
    require(program['elf']['sha256'] == '062a3dd884d64bc1fdf7f0048f312cc5efc84280eb89006c21ef6b60f1f43ed6', 'unchanged1792 ELF')
    require(program['max_lines'] == program['code_functions'] == 1792 and program['max_sets'] == 256, 'software bounds')
    for record in program['sources'] + [program['elf'], program['compiler'], program['converter']]: verify(record)
    for role in ORDER: verify(program['cases'][role]['nbf'])
    require(p['reader']['bytes'] == 151200 and p['reader']['sha256'] == 'a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541', 'exact maintained reader')
    verify(p['reader'])
    if not approved:
        require(p['state'] == 'DRAFT UNLAUNCHABLE model/canonical-gate/host-admission pending', 'explicit pending draft')
        require(all(p[k] is None for k in ('model', 'model_approval', 'canonical_fullcore', 'observation_qualification', 'compiled_sources', 'model_stamp', 'host_admission', 'stage')), 'no placeholder masquerades as model approval')
        return p, program
    require(p['state'] == 'ROOT-APPROVED future1792-stream complete-audit', 'DRAFT UNLAUNCHABLE')
    for key in ('model', 'model_approval', 'canonical_fullcore', 'observation_qualification', 'compiled_sources', 'model_stamp', 'host_admission'):
        require(isinstance(p[key], dict), 'pending model/host binding: ' + key); verify(p[key])
    approval = json.loads(Path(p['model_approval']['path']).read_text())
    require(approval['schema'] == 'root-reviewed1792-model-bridge-v1' and approval['state'] == 'ROOT-REVIEWED closed canonical gate plus observation clone', 'explicit model review, not generic PASS guessing')
    for key in ('model', 'canonical_fullcore', 'observation_qualification', 'compiled_sources', 'model_stamp', 'geometry'):
        require(approval[key] == p[key], 'reviewed model bridge: ' + key)
    require(approval['checks'] == dict.fromkeys(MODEL_CHECKS, True), 'all model/trace/source correctness checks reviewed')
    require(approval['schema167'] == bind(OLD/'schema167.json'), 'exact raw167 schema, no alias adaptation')
    require(p['environment'] == approval['environment'] and p['linked_libraries'] == approval['linked_libraries'], 'actual model runtime/dependencies reviewed')
    require(set(p['environment']) == {'LD_LIBRARY_PATH'}, 'bounded model environment')
    for record in p['linked_libraries']: verify(record)
    raw = json.loads(Path(p['compiled_sources']['path']).read_text()); sources = raw.get('sources', raw)
    for path, record in sources.items():
        actual = bind(path); require(all(actual[k] == record[k] for k in ('path', 'bytes', 'sha256')), 'actual compiled source drift')
    original.source_bindings(Path(p['compiled_sources']['path']))
    stage = Path(p['stage']); require(str(stage).startswith('/dev/shm/') and stage.is_dir() and not stage.is_symlink(), 'new actual ROOT RAM stage')
    require(str(stage) != '/dev/shm/zp-retained1792-allslots-20261121-01', 'stopped cohort is immutable')
    require(Path(p['model']['path']).parent == stage/'model' and not Path(p['model']['path']).is_symlink(), 'model charged in owned stage')
    host = json.loads(Path(p['host_admission']['path']).read_text()); stat = stage.stat()
    require(host['state'] == 'ROOT-APPROVED fixed512MiB stage and source guard' and host['stage'] == dict(path=str(stage), device=stat.st_dev, inode=stat.st_ino), 'actual owned stage identity')
    require(host['runtime_sources'] == p['runtime_sources'] and host['caps'] == CAPS and host['model'] == p['model'], 'source-bound host approval')
    require(host['RAM_free_bytes'] >= CAPS['RAM_reserve']+CAPS['stage_total'] and host['HOME_free_bytes'] >= CAPS['HOME_reserve']+CAPS['preparation'], 'actual host approval resources')
    return p, program


def check_budget(stage, p):
    stage = Path(stage)
    raw = sum(f.stat().st_size for f in stage.glob('*/trace.fst'))
    audit_dirs = [stage/(role+'-audit') for role in ORDER]
    audits = [sum(f.stat().st_size for f in d.rglob('*') if f.is_file()) for d in audit_dirs]
    total = sum(f.stat().st_size for f in stage.rglob('*') if f.is_file())
    require(total <= CAPS['stage_total'] and raw <= CAPS['raw_total'] and sum(audits) <= CAPS['audit_total'] and total-raw-sum(audits) <= CAPS['other_total'], 'fixed sum/phase budget')
    require(all(f.stat().st_size <= CAPS['raw_per_case'] for f in stage.glob('*/trace.fst')) and all(n <= CAPS['audit_per_case'] for n in audits), 'fixed per-case budget')
    require(shutil.disk_usage(stage).free >= CAPS['RAM_reserve']+CAPS['stage_total']-total, 'RAM1GiB plus remaining stage')
    require(sum(f.stat().st_size for f in HERE.rglob('*') if f.is_file()) <= CAPS['preparation'] and shutil.disk_usage(HERE).free >= CAPS['HOME_reserve']+CAPS['preparation'], 'HOME preparation/reserve')


def counters_for(role):
    return [0,1792,0,1792,0,14336] if role == 'd-enabled' else [1792,0,1792,0,14336,0] if role == 'i-enabled' else [0]*6


def check_native(stage, role, p, preparation_path, expected_sha):
    case=Path(stage)/role; path=case/'verification.json'
    require(bind(path)['sha256'] == expected_sha, 'external native-proof anchor mismatch')
    run=json.loads(path.read_text()); require(run['role'] == role and run['state'].startswith('PASS'), 'complete exact native role')
    require(run['counters'] == counters_for(role), 'all actual GP0 counters exact/nonsaturated')
    require(run['admission'] == bind(case/'admission.json'), 'fixed native admission path')
    ad=json.loads((case/'admission.json').read_text())
    require(ad['preparation'] == bind(preparation_path) and ad['model'] == p['model'] and ad['program'] == p['program'], 'native exact approved inputs')
    require(ad['schema'] == 'retained-capacity1792-stream-native-v1' and ad['role'] == role, 'new native schema')
    require(ad['reader'] == p['reader'] and ad['compiled_sources'] == p['compiled_sources'], 'native reader/source identity')
    expected=[bind(case/name) for name in ('prog.riscv','prog.nbf','run.log','process.json','trace.fst')]
    require(run['files'] == expected, 'native fixed file paths and hashes')
    require(ad['elf'] == bind(case/'prog.riscv') and ad['nbf'] == bind(case/'prog.nbf'), 'actual loaded inputs')
    program=json.loads(Path(p['program']['path']).read_text())
    require(ad['elf']['sha256'] == program['elf']['sha256'] and ad['nbf']['sha256'] == program['cases'][role]['nbf']['sha256'], 'loaded fixture bytes')
    require(json.loads(Path(ad['runtime_sources']['path']).read_text()) == p['runtime_sources'] and ad['runtime_sources'] == bind(Path(stage)/'runtime-sources.json'), 'exact runtime snapshot')
    return run


def verify_audit(stage, role, p, preparation_path, expected_sha):
    out=Path(stage)/(role+'-audit'); accepted=out/'acceptance.json'
    require(bind(accepted)['sha256'] == expected_sha, 'external audit acceptance anchor mismatch')
    receipt=json.loads(accepted.read_text())
    require(receipt['schema'] == 'retained1792-stream-acceptance-v1' and receipt['role'] == role, 'new exact audit role')
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
