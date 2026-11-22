"""New1792 prospective budget only; never imports/changes frozen256 accounting."""
from pathlib import Path
import hashlib,json,shutil
HERE=Path(__file__).resolve().parent
BASE=Path('/run/user/1001/zp-csr-unmasked1792-fullcore-20261122-01')
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked1792-fullcore-20261122')
OWN_CAP=1024**3;DURABLE_CAP=96*1024**2;HELPER_CAP=128*1024
A=None
def require(v,m):
 if not v:raise ValueError(m)
def bind(p):
 p=Path(p);h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=h.hexdigest())
def size(p):return sum(q.lstat().st_size for q in p.rglob('*') if q.is_file() or q.is_symlink()) if p.exists() else 0
def configure(path,sha):
 global A
 row=bind(path);require(row['sha256']==sha,'exact ROOT prospective admission');a=json.loads(Path(path).read_text());require(a['ROOT_approved'] is True,'DRAFT nonlaunchable')
 for r in a['inputs']:require(bind(r['path'])==r,'bound source/helper drift')
 qrow=a['ROOT_resource_profile'];require(bind(qrow['path'])==qrow,'fresh ROOT profile');q=json.loads(Path(qrow['path']).read_text());require(q['all_other_charged_reserves_included'] is True,'all oldOTHER/currentCAD/native charges explicit')
 require(q['unchanged_old_OTHER_RUN_bytes']>=1156926898,'original fixed OTHER retained, no inferred release')
 require(q['current256_native_future_bytes']>=1024**3 or q.get('ROOT_verified_current256_delta_and_doublefreeze') is True,'FULL old current native reservation until explicit delta+doublefreeze authority')
 if q['current256_native_future_bytes']<1024**3:
  r=q['current256_final_release'];require(bind(r['path'])==r and json.loads(Path(r['path']).read_text())['state'].startswith('PASS'),'formal exact current256 release receipt')
 decision=a['ROOT_lower256_disposition'];require(bind(decision['path'])==decision,'actual lower256 disposition');d=json.loads(Path(decision['path']).read_text());require(d['ROOT_verified'] is True and d['job']=='20261122T151115Z-a44c03bb7' and d['proceed_1792_native_validation'] is True,'conditional lower256 outcome and ROOT decision required')
 A=(Path(path),row,a,q);return a
def check():
 require(A is not None,'no ROOT authority configured');p,row,a,q=A;require(bind(p)==row and bind(a['ROOT_resource_profile']['path'])==a['ROOT_resource_profile'],'immutable ROOT authority/profile')
 run,home,helper=size(BASE),size(DURABLE),size(HERE);require(run<=OWN_CAP and home<=DURABLE_CAP and helper<=HELPER_CAP,'entire source/run/proof/helper caps')
 require(size(DURABLE/'base-full-clone-STD-closed01')<=32*1024**2 and size(DURABLE/'all1792-delta-closed01')<=64*1024**2,'prospective32MiB base+64MiB high-capacity delta caps')
 require(shutil.disk_usage(BASE.parent).free>=q['RUN_floor_bytes']+OWN_CAP-run+q['other_RUN_bytes'],'new source/run1GiB remaining +ALL old/native/CAD future')
 require(shutil.disk_usage(HERE).free>=q['HOME_floor_bytes']+DURABLE_CAP-home+q['other_HOME_bytes'],'new96MiB proof remaining +ALL old/native/CAD/logging charges; helper inside logging envelope')
 require(shutil.disk_usage('/dev/shm').free>=q['SHM_floor_bytes']+q['other_SHM_bytes'],'other SOURCE/SHM reservations')
 mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'));require(mem>=q['required_MemAvailable_bytes'],'explicit8worker/compiler/native physical memory headroom')
 return dict(RUN=run,HOME=home,helper=helper)
