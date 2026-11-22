"""Fresh CSR profile only: no obsolete native/CAD reservation imports."""
import hashlib,json,os,shutil,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
HELPER_ROOT=HERE.parent
BASE=Path('/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01')
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fullcore-20261122')
OWN_CAP=1024**3;DURABLE_CAP=32*1024**2;HELPER_CAP=1024**2
A=None

def require(v,m):
 if not v:raise ValueError(m)
def bind(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def size(p):
 return sum(q.lstat().st_size for q in Path(p).rglob('*') if q.is_file() or q.is_symlink()) if Path(p).exists() else 0
def configure(path,sha):
 global A
 p=Path(path);b=bind(p);require(b['sha256']==sha,'exact ROOT admission');a=json.loads(p.read_text());require(a.get('ROOT_approved') is True,'DRAFT cannot execute or allocate')
 require(a['limits']==dict(RUN=OWN_CAP,HOME=DURABLE_CAP,helper=HELPER_CAP,FST=150*1024**2,RUN_floor=1024**3,HOME_floor=2415919104,SHM_floor=512*1024**2),'fixed fullcore/clone total limits')
 for r in a['inputs']:require(bind(r['path'])==r,'frozen input drift '+r['path'])
 rp=a['ROOT_resource_profile'];require(bind(rp['path'])==rp,'fresh ROOT resource profile');profile=json.loads(Path(rp['path']).read_text());require(profile['all_other_charged_reserves_included'] is True,'all other reserves required')
 for k in ('other_HOME_bytes','other_RUN_bytes','other_SHM_bytes'):require(type(profile[k]) is int and profile[k]>=0,'explicit other volume reserve')
 for r in profile['basis_records']:require(bind(r['path'])==r,'resource basis drift')
 A=(p,b,a,profile);return a

def check():
 require(A is not None,'ROOT profile not configured');p,b,a,profile=A;require(bind(p)==b and bind(a['ROOT_resource_profile']['path'])==a['ROOT_resource_profile'],'admission/profile drift')
 run,home,helper=size(BASE),size(DURABLE),size(HELPER_ROOT)
 require(run<=OWN_CAP and home<=DURABLE_CAP and helper<=HELPER_CAP,'entire fresh RUN/durable/helper caps')
 require(shutil.disk_usage(BASE.parent).free>=1024**3+OWN_CAP-run+profile['other_RUN_bytes'],'RUN floor + remaining + OTHER')
 require(shutil.disk_usage(HERE).free>=2415919104+DURABLE_CAP-home+HELPER_CAP-helper+profile['other_HOME_bytes'],'HOME floor + both remaining + OTHER')
 require(shutil.disk_usage('/dev/shm').free>=512*1024**2+profile['other_SHM_bytes'],'SHM floor + OTHER')
 return dict(RUN=run,HOME=home,helper=helper)
