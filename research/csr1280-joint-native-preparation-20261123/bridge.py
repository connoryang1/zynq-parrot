"""Current1280 immutable lineage and fresh standalone namespace; no authority by import."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ORIGINAL_POOL=Path('/run/user/1001/zp-csr-unmasked1280-fullcore-20261122-01')
SOURCE=ORIGINAL_POOL/'source'
COHORT=Path('/run/user/1001/zp-csr1280-joint-native-20261123-01')
POOL=COHORT
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked1280-fullcore-20261122')
OTHER_HELPERS=()
ORIGINAL_SHA='95699e2ab8c4b3ef7fa8999688d2908dffa65a396c51f63aee522bbf4156a742'
SCOPED_SHA='bc6f17f4be2140071df2a23b9efcbdc75b30ce41d48b39c76b80019942e1e445'
BASE_MANIFEST_SHA='bdbb63471a8b5ee735d72ad9dd0b0769f31275b6f9f26018ea3e401ac4e460ff'
BASE_ARCHIVE_SHA='344536b19857b239210e358406048c420598d65db8b0d4ff60a98d74b7dff320'
FREEZE_SHA='743fac7665a8748ebcb07a34b971650ac80a35491607b3f86873f9c1d93a9798'


def require(v,m):
    if not v:raise ValueError(m)


def bind(p):
    p=Path(p).resolve();h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def verify(row):require(bind(row['path'])=={k:row[k]for k in ('path','bytes','sha256')},'frozen input changed '+row['path'])


def read(row,context):
    verify(row);a=json.loads(Path(row['path']).read_text())
    require(a['schema']=='csr1280-joint-root-authority-v1' and a['ROOT_approved']is True,'UNADMITTED source-only packet')
    require(a['source_plan']==bind(HERE/'source-plan.json'),'exact source packet')
    require(a['semantic_context']==bind(context),'ROOT explicit semantic context')
    require(a['stage']==str(COHORT) and a['model']['sha256']==SCOPED_SHA,'current scoped model/fresh stage')
    require(a['base_closure']['sha256']==BASE_MANIFEST_SHA and a['base_archive']['sha256']==BASE_ARCHIVE_SHA,'actual complete1280 base closure/archive')
    require(a['native_freeze']['sha256']==FREEZE_SHA,'actual original full pool future freeze, not new run authority')
    for key in ('base_closure','base_archive','native_freeze'):verify(a[key])
    return a
