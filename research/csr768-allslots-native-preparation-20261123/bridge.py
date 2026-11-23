"""Current768 immutable lineage and fresh standalone namespace; no authority by import."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ORIGINAL_POOL=Path('/run/user/1001/zp-csr-unmasked768-fullcore-20261123-01')
SOURCE=ORIGINAL_POOL/'source'
COHORT=Path('/run/user/1001/zp-csr768-allslots-native-20261123-01')
POOL=COHORT
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked768-fullcore-20261123')
OTHER_HELPERS=()
HOST_ACCOUNTING={'interval_s': 1, 'scan_duration_limit_s': 2, 'poll_gap_limit_s': 5, 'snapshot_age_limit_s': 5, 'initial_snapshot_limit_s': 5, 'teardown_bound_s': 5}
ORIGINAL_SHA='8762ddb27740970892245ca7c067fcfff4c89da8dbbce392f2407979dbc5f964'
SCOPED_SHA='1f192b69fb95fce8919d7fbbe6a4c2c594fc8983982e7e2822821e74f2b75fef'
BASE_MANIFEST_SHA='5fd654e008fd9311ff4f3d3dd022233765612fb1d03fa62ade8bcacb24d5be33'
BASE_ARCHIVE_SHA='bd5cfd6aad726b3c91c529c967a50c2f7b4aa887368b4c725c3a8aa6b92ff4b5'
FREEZE_SHA='4714a03cbc1e4694d514439f3b23c6247a372ae6ffbe003dd8a5d243e218227c'


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
    require(a['schema']=='csr768-allslots-root-authority-v1' and a['ROOT_approved']is True,'UNADMITTED source-only packet')
    require(a['source_plan']==bind(HERE/'source-plan.json'),'exact source packet')
    require(a['host_accounting']==HOST_ACCOUNTING,'ROOT explicit03 host cadence only')
    require(a['semantic_context']==bind(context),'ROOT explicit semantic context')
    require(a['stage']==str(COHORT) and a['model']['sha256']==SCOPED_SHA,'current scoped model/fresh stage')
    require(a['base_closure']['sha256']==BASE_MANIFEST_SHA and a['base_archive']['sha256']==BASE_ARCHIVE_SHA,'actual complete768 base closure/archive')
    require(a['native_freeze']['sha256']==FREEZE_SHA,'actual original full pool future freeze, not new run authority')
    for key in ('base_closure','base_archive','native_freeze'):verify(a[key])
    return a
