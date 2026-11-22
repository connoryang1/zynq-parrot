"""Matched256 observation-only inputs; unchanged evaluation and software."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=Path('/run/user/1001/zp-retained-borrow256-trace0-fullcore-20261122-01')
STAGE=BASE/'scoped-clone01'
ROOT=STAGE/'records'
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow256-trace0-fullcore-20261122/scoped-closed01')
PROPOSAL=ROOT/'proposal.json'
MODEL_SHA='695e53dccdf418dac6e40ec1c652752e82fb7187c834dbd689ac80233445a80c'
PREFIX='Vbsg_nonsynth_zynq_testbench';SYMS=PREFIX+'__Syms'
CAP=128*1024**2;NATIVE_SECONDS=180;HOST_SECONDS=360
RESERVE=1024**3;ARTIFACT_ALLOCATION=256*1024**2
SP=Path('/home/coyang/zynq-parrot-linux-borrow256-profile')
ORIGINAL=BASE/'full01'
OLD_SOURCE=Path('/home/coyang/zynq-parrot-retained-dense')
GEOMETRY_TOOL=Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/retained-borrow256-trace0-preparation-20261122/geometry.py')

def require(ok,message):
    if not ok:raise ValueError(message)

def bind(path):
    path=Path(path).resolve();h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):h.update(chunk)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=h.hexdigest())

def verify(row):require(bind(row['path'])==row,'frozen file changed: '+row['path'])
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
