"""New clean CSR768 observation-only inputs; unchanged evaluation and cold08."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=Path('/run/user/1001/zp-csr-unmasked768-fullcore-20261123-01')
STAGE=BASE/'scoped-csr01'
ROOT=STAGE/'records'
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked768-fullcore-20261123/scoped-closed01')
PROPOSAL=ROOT/'proposal.json'
MODEL_INPUT=HERE.parent/'model-input.ROOT.json'
_MODEL=json.loads(MODEL_INPUT.read_text()) if MODEL_INPUT.exists() else None
MODEL_SHA=_MODEL['model']['sha256'] if _MODEL is not None else None
PREFIX='Vbsg_nonsynth_zynq_testbench';SYMS=PREFIX+'__Syms'
CAP=64*1024**2;NATIVE_SECONDS=180;HOST_SECONDS=360
RESERVE=1024**3;ARTIFACT_ALLOCATION=256*1024**2
SP=BASE/'source'
ORIGINAL=BASE/'full01'
BUILD=BASE/'full01'
COMPLETION=BUILD
OLD_SOURCE=Path('/home/coyang/zynq-parrot-retained-dense')
GEOMETRY_TOOL=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr768-native-preparation-20261123/geometry.py')

def require(ok,message):
    if not ok:raise ValueError(message)

def bind(path):
    path=Path(path).resolve();h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):h.update(chunk)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=h.hexdigest())

def verify(row):require(bind(row['path'])=={k:row[k] for k in ('path','bytes','sha256')},'frozen file changed: '+row['path'])
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def identities(rows):return {k:(v['bytes'],v['sha256']) for k,v in rows.items()}

def tree(path):
    result={}
    for p in sorted(Path(path).rglob('*')):
        require(not p.is_symlink(),'generated tree contains symlink')
        if p.is_file() and p.suffix!='.gch':result[str(p.relative_to(path))]=bind(p)
    return result

def fresh_home(path):
    p=Path(path).absolute();require(not p.exists() and not p.is_symlink(),'fresh output only')
    p=p.resolve();require(str(p).startswith('/home/coyang/'),'HOME output only');return p



def producer():
    from native_input import read_fullcore
    require(_MODEL is not None and _MODEL['schema']=='csr768-observation-model-input-v1' and _MODEL['state']=='ROOT-BOUND actual768 fullPASS; no clone execution authority','new model binding required; NULL/DRAFT cannot prepare')
    verify(_MODEL['fullcore']);require(_MODEL['fullcore']==bind(BUILD/'session.json'),'exact current768 producer path')
    c=read_fullcore(_MODEL['fullcore']['sha256'])
    require({k:c['model'][k]for k in ('path','bytes','sha256')}==_MODEL['model'] and c['model']['sha256']==MODEL_SHA,'new model bytes bound after actualPASS')
    return c
