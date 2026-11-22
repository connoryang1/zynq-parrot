#!/usr/bin/env python3
"""Inventory the CLOSED matched borrowing256 FST only; never build or run a model."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PREP = Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/retained-borrow256-trace0-preparation-20261122')
QUALIFIED = HERE.parent/'retained256-qualification-20261122/software_owned_v2.py'
ARCHIVE = Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow256-trace0-fullcore-20261122/closed01/archive.json')
ARCHIVE_SHA = '9918f125af54570e183d249d22eef995f8da1d826d4992fcf24e568721669c59'
TEMPLATE = Path('/home/coyang/fpga-artifacts/context-resume/retained-canonical-scoped-20261121/proposal.json')
PAIR = Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow-matched-source-20261122/comparison02.json')
PAIR_SHA = '97a2bea7bb2712f08e81d60b7effe5a8bb73509893051d916387d1e9ebed7785'
ORIGINAL = Path('/run/user/1001/zp-retained-borrow256-trace0-fullcore-20261122-01/full01')
OUTPUT = ORIGINAL.parent/'scoped-inventory01'
PLAN = HERE/'inventory-plan.json'
OUT_CAP = 20*1024**2  # prior actual full hierarchy14,549,952B; RAM only
PREP_CAP = 1024**2


def require(ok, why):
    if not ok:
        raise ValueError(why)


def bind(path):
    path = Path(path).resolve(); h = hashlib.sha256()
    with path.open('rb') as stream:
        for raw in iter(lambda: stream.read(1024**2), b''):
            h.update(raw)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=h.hexdigest())


def verify(row):
    require(bind(row['path']) == {k:row[k] for k in ('path','bytes','sha256')}, 'frozen bytes changed: '+row['path'])
    stat=Path(row['path']).stat()
    for key in ('inode','mtime_ns','ctime_ns'):
        if key in row:
            require(getattr(stat, 'st_ino' if key=='inode' else 'st_'+key)==row[key], 'frozen metadata changed: '+row['path'])


def size(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file())


def domains(template):
    result = copy.deepcopy(template['domains'])
    require({k: len(v) for k,v in result.items()} == dict(core252=252, observer_and_geometry=45, SP_strict162=162, actual_geometry16=16, capacity167=167), 'exact old five selection domains')
    old = result.pop('actual_geometry16')
    roots = [r['path'].rsplit('.', 1)[0] for r in old if r['path'].endswith('.num_threads_p')]
    require(len(roots) == 1, 'one actual core parameter root')
    added = dict(path=roots[0]+'.core_minimal.cache_miss_trace_p', width=1)
    result['actual_geometry17'] = old+[added]
    union = {}
    for part in result.values():
        for row in part:
            require(row['path'] not in union or union[row['path']]['width'] == row['width'], 'consistent shared leaf width')
            union[row['path']] = row
    require(len(union) == 415 and any(k.endswith('.dcache_retained_maintenance_v') for k in union), '415 exact leaves including raw maintenance')
    require(not any('retained_hit_data_r' in k for k in union), 'no removed hit-data register assumption')
    return result, [union[k] for k in sorted(union)]


def parse_listing(text, required):
    lines = text.splitlines()
    require(lines and lines[-1] == '#END' and lines.count('#END') == 1, 'complete unique hierarchy EOF')
    declared = {}
    for line in lines:
        if line.startswith('#VAR\t'):
            fields = line.split('\t'); require(len(fields) == 4, 'hierarchy row shape')
            _, width, handle, name = fields
            require(name not in declared and int(width)>0 and int(handle)>0, 'unique valid hierarchy declaration')
            declared[name] = int(width)
        else:
            require(line == '#END' or line.startswith('#'), 'unexpected hierarchy text')
    for row in required:
        require(declared.get(row['path']) == row['width'], 'missing/wrong actual leaf: '+row['path'])
    return declared


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def seal():
    require(not PLAN.exists(), 'fresh immutable inventory plan')
    require(bind(ARCHIVE)['sha256'] == ARCHIVE_SHA and bind(PAIR)['sha256'] == PAIR_SHA, 'closed archive and matched source bridge')
    template = json.loads(TEMPLATE.read_text()); parts, leaves = domains(template)
    reader = template['reader']; verify(reader)
    require(reader['sha256'] == 'a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541', 'qualified existing reader')
    require(bind(QUALIFIED)['sha256'] == '52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5', 'qualified ownership guard')
    inputs = [Path(__file__), QUALIFIED, ARCHIVE, PAIR, TEMPLATE, *sorted(PREP.glob('*.py'))]
    plan = dict(schema='borrow256-closed-hierarchy-inventory-v1', state='PREPARED ROOT-only list; no clone/model/target',
                inputs=[bind(p) for p in inputs], reader=reader, domains=parts, writer_leaves=leaves,
                source_TOP='1008854d30e5d923c86c3232fc22af039467d552', source_BP='bb575a764c200f07c6f3259a179bdc861dd7593f',
                model_sha='695e53dccdf418dac6e40ec1c652752e82fb7187c834dbd689ac80233445a80c',
                output=str(OUTPUT), reader_seconds=60, teardown_seconds=5, output_cap=OUT_CAP, prep_cap=PREP_CAP,
                scope='Actual path/width inventory only. No clone qualification or all-slot/FPGA/application acceptance.')
    with PLAN.open('x') as stream: json.dump(plan,stream,indent=2); stream.write('\n')
    print(json.dumps(bind(PLAN)))


def execute(expected_sha):
    require(bind(PLAN)['sha256'] == expected_sha, 'ROOT externally reviewed plan SHA')
    plan = json.loads(PLAN.read_text())
    for row in plan['inputs']+[plan['reader']]: verify(row)
    archive = json.loads(ARCHIVE.read_text())
    for row in archive['archives']: verify(row['archive'])
    verify(archive['composite']); verify(archive['model']); verify(archive['actual_source_list'])
    require(archive['model']['sha256'] == plan['model_sha'], 'exact matched model')
    trace = ORIGINAL/'advisory/trace.fst'
    matches = [r for r in archive['groups']['singles'] if r['path'] == str(trace)]
    require(len(matches) == 1, 'unique closed advisory FST'); verify(matches[0])
    producer = json.loads((ORIGINAL/'session.json').read_text())
    require(producer['state'].startswith('PASS'), 'actual completed fullcore producer')
    sys.path.insert(0,str(PREP)); budget = load(PREP/'budget.py', 'borrow256_inventory_budget')
    owned = load(QUALIFIED, 'borrow256_inventory_owned')
    before = budget.check()
    require(not OUTPUT.exists() and not OUTPUT.is_symlink(), 'fresh inventory output, no retry')
    OUTPUT.mkdir()
    start = time.monotonic(); record = dict(state='FAIL', plan=bind(PLAN), archive=bind(ARCHIVE), trace=matches[0], budget_before=before)
    last = [0.0]
    def guard():
        require(time.monotonic()-start < 90, 'fixed outer inventory deadline')
        used = size(OUTPUT); prep = size(HERE)
        require(used <= OUT_CAP and prep <= PREP_CAP, 'inventory output20MiB RAM/prep1MiB HOME caps')
        if time.monotonic()-last[0]>=1:
            state = budget.check()
            require(shutil.disk_usage(HERE).free >= budget.source.budget()['required_free_bytes']+budget.DURABLE_CAP-budget.source.size(budget.DURABLE)+PREP_CAP-prep,
                    'HOME existing full reservations plus new1MiB prep')
            require(state['own_bytes'] <= budget.OWN_CAP, 'inventory is inside original768MiB allocation')
            last[0]=time.monotonic()
    try:
        with (OUTPUT/'hierarchy.tsv').open('x') as stream:
            receipt = owned.run([plan['reader']['path'], str(trace), '--list'], ORIGINAL, os.environ.copy(), stream, 60, guard, None)
        record['owned'] = receipt; require(receipt['returncode'] == 0, 'reader actual zero exit')
        listing = (OUTPUT/'hierarchy.tsv').read_text()
        actual = parse_listing(listing, plan['writer_leaves'])
        guard()
        for row in plan['inputs']+[plan['reader'], matches[0], archive['model']]: verify(row)
        record.update(state='PASS exact415 actual path/widths; clone remains pending', hierarchy=bind(OUTPUT/'hierarchy.tsv'),
                      declarations=len(actual), domains={k:len(v) for k,v in plan['domains'].items()}, required_count=len(plan['writer_leaves']), budget_after=budget.check())
    except BaseException as error:
        record.update(error=repr(error), owned=getattr(error,'owned_receipt',record.get('owned'))); raise
    finally:
        record['elapsed_seconds']=time.monotonic()-start
        with (OUTPUT/'session.json').open('x') as stream: json.dump(record,stream,indent=2); stream.write('\n')
    print(json.dumps(bind(OUTPUT/'session.json')))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__); action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--seal',action='store_true'); action.add_argument('--execute-inventory',metavar='REVIEWED_PLAN_SHA')
    args=parser.parse_args()
    if args.seal: seal()
    else: execute(args.execute_inventory)
