"""Fresh clean768 base capture in the ONE existing32MiB native durable family."""
from pathlib import Path
import hashlib,json,shutil
HERE=Path(__file__).resolve().parent
BASE=Path('/run/user/1001/zp-csr-unmasked768-fullcore-20261123-01')
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked768-fullcore-20261123')
OWN_CAP=1024**3;DURABLE_CAP=32*1024**2;HELPER_CAP=64*1024
A=None
def require(v,m):
 if not v:raise ValueError(m)
def bind(p):
 p=Path(p);h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())
def size(p):
 if not p.exists():return 0
 ss=[f.lstat() for f in p.rglob('*') if f.is_file() or f.is_symlink()]
 return max(sum(s.st_size for s in ss),sum(s.st_blocks*512 for s in ss))
def configure(path,sha):
 global A
 row=bind(path);require(row['sha256']==sha,'exact ROOT authority');a=json.loads(Path(path).read_text())
 require(a['schema']=='csr768-base32-archive-v1' and a['ROOT_approved'] is True,'fresh ROOT capture approval')
 require(a['TOP']=='1b24c915ed628f6d47a382b3aa89fb662884e1a1' and a['BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','exact clean768 source')
 require(a['scope']=='768-base-clean-full-clone-STD-only; all768 delta pending','complete initial base scope only')
 require(a['representation']=='same-accepted-raw-FST-backed-canonical-format' and a['limits']==dict(raw_corpus_bytes=512*1024**2,per_file_bytes=128*1024**2,existing_HOME_bytes=DURABLE_CAP,helper_HOME_bytes=HELPER_CAP,prepare_seconds=120,compress_seconds=600,roundtrip_seconds=180,total_codec_seconds=780,codec_AS_bytes=1024**3),'fixed32MiB whole family/representation; no second allowance')
 for r in a['inputs']:require(bind(r['path'])==r,'bound helper/proof drift')
 pr=a['ROOT_resource_profile'];require(bind(pr['path'])==pr,'ROOT exact fresh profile');q=json.loads(Path(pr['path']).read_text())
 require(q['schema']=='csr768-base32-capture-resource-profile-v1' and q['ROOT_approved'] is True and q['all_other_charged_reserves_included'] is True,'all OTHER explicitly priced')
 require(q['caps']==dict(RUN_pool=OWN_CAP,base_HOME=DURABLE_CAP,helper_HOME=HELPER_CAP),'unchanged1GiB/32MiB; helper inside logging')
 require(q['RUN_floor_bytes']==1024**3 and q['HOME_floor_bytes']==1879048192 and q['SHM_floor_bytes']==512*1024**2,'fixed floors')
 require(q['existing_native32_charged_once'] is True and q['OTHER_excludes_this_same_RUN_pool_and_base32'] is True and q['logging128MiB_in_OTHER_HOME'] is True,'no silent release/double pool/base/log omission')
 require(q['other_HOME_bytes']>=128*1024**2,'explicit ongoing128MiB logging')
 require(all(type(q[k]) is int and q[k]>=0 for k in ('other_RUN_bytes','other_HOME_bytes','other_SHM_bytes')),'fixed full OTHER sums')
 for r in q['basis_records']:require(bind(r['path'])==r,'ROOT current reservation/disposition basis')
 A=(Path(path),row,a,q);return a
def check():
 require(A is not None,'ROOT profile not configured');p,row,a,q=A
 require(bind(p)==row and bind(a['ROOT_resource_profile']['path'])==a['ROOT_resource_profile'],'frozen authority/profile')
 run,home,helper=size(BASE),size(DURABLE),size(HERE)
 require(run<=OWN_CAP and home<=DURABLE_CAP and helper<=HELPER_CAP,'whole native pool/whole32MiB family/helper caps')
 require(shutil.disk_usage(BASE.parent).free>=q['RUN_floor_bytes']+max(0,OWN_CAP-run)+q['other_RUN_bytes'],'same1GiB pool remains charged until later separate freeze')
 require(shutil.disk_usage(HERE).free>=q['HOME_floor_bytes']+max(0,DURABLE_CAP-home)+q['other_HOME_bytes'],'existing32MiB remaining charged ONCE plus all OTHER/logging/floor')
 require(shutil.disk_usage('/dev/shm').free>=q['SHM_floor_bytes']+q['other_SHM_bytes'],'SHM all future/floor')
 return dict(RUN=run,HOME=home,helper=helper)
