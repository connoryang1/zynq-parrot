from pathlib import Path
import json,hashlib,stat,os,time
O=Path(__file__).parent
BASE=Path('/run/user/1001/zp-csr-unmasked1280-fullcore-20261122-01')
WORK=BASE/'archive32-records01'
OUT=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked1280-fullcore-20261122/base-full-clone-std-closed01')
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def bind(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=digest(p))
def paths(root):return sorted(str(p) for p in root.rglob('*') if (p.is_file() or p.is_symlink()) and not(p==WORK or WORK in p.parents or p==OUT or OUT in p.parents))
M=OUT/'manifest.json';d=json.loads(M.read_bytes());assert d['state']=='PASS base32 lossless1280 clean full+clone+STD archival; all1280 delta pending'
assert d['originals_unchanged'] and d['no_cleanup']
assert [r['action']for r in d['commands']]==['compress','roundtrip']
for r in d['commands']:
 q=r['owned'];assert q['returncode']==0 and q['failure'] is None and not q['owned_group_remaining']
 assert all(not s['members']for s in q['group_states'])
assert bind(Path(d['archive']['path']))==d['archive']
I=WORK/'inventory.json';assert bind(I)==d['inventory'];c=json.loads(I.read_bytes())
for root,names in c['frozen_root_paths'].items():assert paths(Path(root))==names,root
count=0
for r in c['members']+c['excluded']:
 p=Path(r['path']);s=p.lstat();assert [s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_ino,stat.S_IMODE(s.st_mode)]==r['stat'],str(p)
 if r['kind']=='symlink':
  data=os.readlink(p).encode();assert os.readlink(p)==r['target'] and hashlib.sha256(data).hexdigest()==r['sha256']
 else:assert stat.S_ISREG(s.st_mode) and digest(p)==r['sha256'],str(p)
 count+=1
for pin in c['identity_pins']:
 p=Path(pin['observed']['path']);s=p.lstat();assert [s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_ino,stat.S_IMODE(s.st_mode)]==pin['observed']['stat']
 assert bind(p)=={k:pin['observed'][k]for k in ('path','bytes','sha256')}
assert len([r for r in c['members']if r['path'].endswith('.fst') and BASE in Path(r['path']).parents])==7
live=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  if p.stat().st_uid!=os.getuid() or int(p.name)==os.getpid():continue
  comm=(p/'comm').read_text().strip()
  if comm.startswith('Vbsg_') or comm in {'vivado','verilator_bin','make','gmake','cc1plus'}:live.append(dict(pid=int(p.name),comm=comm))
 except (FileNotFoundError,ProcessLookupError,PermissionError):pass
assert not live,live
q=dict(ROOT_verified=True,state='PASS complete initial1280 native-base durable preservation/readback and independent all-original rehash; explicit unused native futures finalized',TOP='88ab04dfcc508176cc977096ca0c132299a8a460',BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa',native_session_sha256='bf2a4ff4d80e7bf254b4e7a3037b9b0f5bbc40d9310ced076d91185d6a753f41',native_model_sha256='95699e2ab8c4b3ef7fa8999688d2908dffa65a396c51f63aee522bbf4156a742',scoped_model_sha256='bc6f17f4be2140071df2a23b9efcbdc75b30ce41d48b39c76b80019942e1e445',manifest=bind(M),archive=d['archive'],inventory=bind(I),all_originals_preserved=True,ROOT_rehashed_originals=count,ROOT_complete_membership_verified=True,raw_FSTs=7,external_Git_objects='Eight durable HOME common stores explicitly GC-rooted, separate from archive; one private object store included',future_RUN_bytes=0,future_HOME_bytes=0,all_current_bytes_still_charged=True,other_reservations_unchanged=True,no_model_or_vendor_workers=live,scope='Initial sparse native correctness/clone/fourSTD only; all1280 occupancy, CAD, FPGA and application qualification remain pending; later work requires separately funded output family',UTC=time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime()))
p=OUT/'ROOT-native-future-freeze.json';assert not p.exists();p.write_text(json.dumps(q,indent=2)+'\n');print(json.dumps(bind(p)))
