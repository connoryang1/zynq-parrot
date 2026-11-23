"""New1280 prospective budget only; never imports/changes frozen256 accounting."""
from pathlib import Path
import hashlib,json,shutil
HERE=Path(__file__).resolve().parent
BASE=Path('/run/user/1001/zp-csr-unmasked1280-fullcore-20261122-01')
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked1280-fullcore-20261122')
OWN_CAP=1024**3;DURABLE_CAP=32*1024**2;HELPER_CAP=128*1024
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
 qrow=a['ROOT_resource_profile'];require(bind(qrow['path'])==qrow,'fresh ROOT profile');q=json.loads(Path(qrow['path']).read_text());require(q['schema']=='csr1280-native-resource-profile-v1' and q['ROOT_approved'] is True and q['all_other_charged_reserves_included'] is True,'all oldOTHER/currentCAD/native charges explicitly ROOT priced')
 require(q['caps']==dict(RUN=OWN_CAP,base_HOME=DURABLE_CAP,helper_HOME=HELPER_CAP,program_inside_RUN=8*1024**2),'exact fresh1GiB/32MiB/128KiB scope')
 require(q['TOP']=='88ab04dfcc508176cc977096ca0c132299a8a460' and q['BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','fresh1280 resource/source scope')
 require(q['RUN_floor_bytes']>=1024**3 and q['HOME_floor_bytes']>=1792*1024**2 and q['SHM_floor_bytes']>=512*1024**2 and q['required_MemAvailable_bytes']>=8*1024**3,'preserve established floors/8worker physical headroom')
 require(all(type(q[k]) is int and q[k]>=0 for k in ('other_RUN_bytes','other_HOME_bytes','other_SHM_bytes')),'explicit ALL_OTHER prospective charges')
 for basis_row in q['basis_records']:require(bind(basis_row['path'])==basis_row,'actual ROOT resource basis/terminal/native freeze')
 decision=a['ROOT_capacity_selection'];require(bind(decision['path'])==decision,'actual ROOT capacity decision');d=json.loads(Path(decision['path']).read_text());require(d['ROOT_verified'] is True and d['proceed_1280_native_validation'] is True and d['TOP']==q['TOP'] and d['BP']==q['BP'],'ROOT selected fixed1280 validation, no automatic execution from old fit')
 A=(Path(path),row,a,q);return a
def check():
 require(A is not None,'no ROOT authority configured');p,row,a,q=A;require(bind(p)==row and bind(a['ROOT_resource_profile']['path'])==a['ROOT_resource_profile'],'immutable ROOT authority/profile')
 run,home,helper=size(BASE),size(DURABLE),size(HERE);require(run<=OWN_CAP and home<=DURABLE_CAP and helper<=HELPER_CAP,'entire source/run/proof/helper caps')
 require(size(DURABLE)<=32*1024**2,'base-only32MiB; future all1280 delta64MiB UNADMITTED separately')
 require(shutil.disk_usage(BASE.parent).free>=q['RUN_floor_bytes']+OWN_CAP-run+q['other_RUN_bytes'],'new source/run1GiB remaining +ALL old/native/CAD future')
 require(shutil.disk_usage(HERE).free>=q['HOME_floor_bytes']+DURABLE_CAP-home+q['other_HOME_bytes'],'new32MiB base proof remaining +ALL old/native/CAD/logging charges; helper inside logging envelope')
 require(shutil.disk_usage('/dev/shm').free>=q['SHM_floor_bytes']+q['other_SHM_bytes'],'other SOURCE/SHM reservations')
 mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'));require(mem>=q['required_MemAvailable_bytes'],'explicit8worker/compiler/native physical memory headroom')
 return dict(RUN=run,HOME=home,helper=helper)
