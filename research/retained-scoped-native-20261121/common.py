"""Frozen inputs and bounded filesystem helpers for observation-only qualification."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NATURAL = ROOT / 'research/retained-natural-control-20261121'
PROPOSAL = ROOT / 'research/retained-scoped-trace-proposal-20261121/proposal.json'
PROPOSAL_SHA = '52bf582ead5183e973527033082231990f90a81e674ff960be3ace69519533b3'
MODEL_SHA = 'ef0c7c4c9e84e97d4b71d6c80e6c118d5670411be3a3b16e5469cb89239b5f5d'
PREFIX = 'Vbsg_nonsynth_zynq_testbench'
SYMS = PREFIX + '__Syms'
CAP = 150 * 1024 * 1024
NATIVE_SECONDS = 1800
HOST_SECONDS = 1980


def require(value, message):
    if not value:
        raise ValueError(message)


def bind(path):
    p = Path(path).resolve()
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return dict(path=str(p), bytes=p.stat().st_size, sha256=h.hexdigest())


def verify(record):
    require(bind(record['path']) == record, 'frozen file changed: ' + record['path'])


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def proposal():
    require(bind(PROPOSAL)['sha256'] == PROPOSAL_SHA, 'reviewed proposal changed')
    p = json.loads(PROPOSAL.read_text())
    leaves = p['filter_leaves']
    require(len(leaves) == len({r['path'] for r in leaves}) == 252,
            'wrong reviewed leaf union')
    require(p['model']['sha256'] == MODEL_SHA, 'wrong original model')
    return p


def fresh_home(path):
    path = Path(path).absolute()
    require(not path.exists() and not path.is_symlink(), 'output must be fresh')
    path = path.resolve()
    require(str(path).startswith('/home/coyang/'), 'output must be isolated HOME path')
    return path


def tree(path):
    result = {}
    for p in sorted(Path(path).rglob('*')):
        require(not p.is_symlink(), 'generated tree contains symlink')
        if p.is_file() and p.suffix != '.gch':
            result[str(p.relative_to(path))] = bind(p)
    return result


def identities(records):
    return {k: (v['bytes'], v['sha256']) for k, v in records.items()}
