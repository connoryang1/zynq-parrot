"""R9 closure-only helpers. No old full/native budget checker or tool calls."""
import ast
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tarfile

ADAPTER = Path('/home/coyang/fpga-artifacts/context-resume/borrow256-fpga-preparation-20261122/preparation01/adapter02')
API = Path('/home/coyang/zynq-parrot-linux-host-observer/research/retained256-qualification-20261122/close256.py')
POLICY = Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/retained-borrow256-shared-budget-preparation-20261122/policy.json')
MARKER = Path('/home/coyang/fpga-artifacts/context-resume/reservation-closures-20261122/r8-freeze-complete.json')
CAD = Path('/run/user/1001/zp-linux-borrow256-trace0-cad-20261122-01')

def require(ok, message):
    if not ok:
        raise ValueError(message)

def bind(path, guard=lambda: None):
    p = Path(path); h = hashlib.sha256(); size = 0
    with p.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            guard(); h.update(block); size += len(block)
    return dict(path=str(p.resolve()), bytes=size, sha256=h.hexdigest())

def load(name):
    spec = importlib.util.spec_from_file_location('R9_closure_' + name, ADAPTER / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def check_policy():
    # Only the sealed fixed-policy parser; never call an old live budget.
    load('reservation').check_policy(load('budget').LIMITS)

def allocated_tree(root):
    root = Path(root)
    if not root.exists():
        return 0
    return sum(p.lstat().st_blocks * 512 for p in root.rglob('*') if p.is_file() or p.is_symlink())

def resources(work_bytes, evidence_bytes, extra_home=0, check_shared=True):
    if check_shared:
        check_policy()
    b = load('budget'); volumes = {}
    for name, path in [('work', CAD.parent), ('home', Path('/home/coyang')), ('shm', Path('/dev/shm'))]:
        volumes[name] = dict(device=path.stat().st_dev, free_bytes=shutil.disk_usage(path).free, observed_path=str(path))
    r = dict(volumes=volumes, work_allocated_bytes=work_bytes, evidence_allocated_bytes=evidence_bytes)
    # External receipt preparation remains a new allocation, not evidence cap growth.
    limits = dict(b.LIMITS)
    limits['other_home_future_bytes'] += extra_home
    violations = b.violations(r, None, limits)
    require(not violations, 'original R9 own caps + fixed OTHER actual-volume reserve: ' + repr(violations))
    return dict(resources=r, limits=limits, violations=violations)

def vendor_processes():
    predicate = load('identity').vendor_process
    rows = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            text = (p / 'stat').read_text(); fields = text[text.rfind(')') + 2:].split()
            row = dict(pid=int(p.name), comm=(p / 'comm').read_text().strip(), state=fields[0], startticks=int(fields[19]),
                       argv_tokens=[os.fsdecode(x) for x in (p / 'cmdline').read_bytes().split(b'\0') if x])
            if predicate(row) or row['comm'].lower() == 'rdi_program':
                rows.append(row)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return rows

def archive_api():
    """Extract exact qualified API bodies, avoiding its unrelated old imports."""
    require(bind(API)['sha256'] == '9827b75a4c10e1010f665d35ad243d382c34e12cc5c9f4b7235bd6fc9069e61c', 'exact qualified archive API')
    source = API.read_text(); tree = ast.parse(source)
    wanted = {'CheckedReader', 'archive_group'}
    parts = [ast.get_source_segment(source, node) for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in wanted]
    require(len(parts) == 2, 'exact API extraction; no unrelated import/budget calls')
    namespace = dict(Path=Path, gzip=gzip, tarfile=tarfile, hashlib=hashlib, bind=bind, require=require)
    exec(compile('\n\n'.join(parts), str(API) + ':extracted-exact', 'exec'), namespace)
    return type('QualifiedArchiveAPI', (), {'archive_group': staticmethod(namespace['archive_group'])})
