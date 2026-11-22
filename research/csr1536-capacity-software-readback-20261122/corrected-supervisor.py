import sys,json,hashlib,os,resource,time,shutil,datetime,stat
from pathlib import Path
sys.dont_write_bytecode=True
H=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr1536-opt-whole-cad-preparation03-20261122');sys.path.insert(0,str(H))
import software_owned_v2 as owned
from budget import violations
R=Path(__file__).parent;P=Path('/home/coyang/fpga-artifacts/context-resume/csr1536-physical-capacity-readiness-20261122/preparation02')
A=Path('/home/coyang/fpga-artifacts/context-resume/csr-opt1536-fpga-preparation-20261122/preparation03')
def bind(p):b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def wr(p,q):
 with p.open('x') as f:json.dump(q,f,indent=2);f.write('\n')
def size(p):
 if not p.exists():return 0
 ss=[x.lstat() for x in p.rglob('*') if not x.is_symlink()]
 return max(sum(s.st_size for s in ss if stat.S_ISREG(s.st_mode)),sum(s.st_blocks*512 for s in ss)+p.stat().st_blocks*512)
q=json.loads((A/'admission.FINAL.json').read_text());assert bind(A/'admission.FINAL.json')['sha256']=='483df2736adeb04ba43af3b685913f3bbf87fefe46c7161c4c3704a3b32ebae4'
assert bind(H/'software_owned_v2.py')['sha256']=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5'
def guard():
 assert size(R)<=128*1024,'software metadata cap inside existing4MiB metadata reserve'
 assert size(P)<=64*1024,'new source successor64KiB allocated cap, subset of existing4MiB metadata reserve'
 cfg=q['configuration'];paths=dict(source=cfg['prepared_source_root'],work=cfg['work_root'],home=cfg['log_root'],shm='/dev/shm')
 volumes={}
 for k,s in paths.items():
  p=Path(s)
  while not p.exists():p=p.parent
  volumes[k]=dict(device=p.stat().st_dev,free_bytes=shutil.disk_usage(p).free)
 rs=dict(volumes=volumes,source_allocated_bytes=size(Path(paths['source'])),work_allocated_bytes=size(Path(paths['work'])),evidence_allocated_bytes=sum(size(Path(s)) for s in cfg['evidence_roots']))
 assert not violations(rs,None,q['resources']),rs
 mem=next(int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:'))
 assert mem>=5*1024**3,'5GiB physical remaining reserve incl worker256MiB+OTHER/RAMgrowth+2GiBheadroom'
 s=Path('/proc/1558674/stat').read_text();assert int(s[s.rfind(')')+2:].split()[19])==100536789
 return dict(resources=rs,MemAvailable_bytes=mem)
a=json.loads((P/'authority.DRAFT.json').read_text());a.update(ROOT_approved=True,resources_verified_by_ROOT=True,output=str(R/'result01'),ROOT_qualified_owned_wrapper=bind(H/'software_owned_v2.py'),ROOT_all_OTHER_resource_profile=bind(A/'ROOT-resource-profile.json'),resource_envelope=dict(metadata_cap_bytes=128*1024,metadata_is_subset_of_existing_4MiB_reserve=True,worker_AS_bytes=256*1024**2,worker_wall_seconds=120,minimum_MemAvailable_bytes=5*1024**3,no_new_RUN_SHM_disk_allocation=True),source_successor_allocated_cap_bytes=64*1024,source_correction=bind(P/'correction.json'),old_failure=bind(Path('/home/coyang/fpga-artifacts/context-resume/csr1536-offline-software-readback-20261122/session.json')),ROOT_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),ROOT_initial_resources=guard(),unlaunchable_reasons=['No fitted/package/physical/observer-install authority; software-only gate supplies none.'])
wr(R/'authority.FINAL.json',a)
argv=['/usr/bin/python3','-B',str(P/'prepare_software.py'),'--authority',str(R/'authority.FINAL.json'),'--authority-sha',bind(R/'authority.FINAL.json')['sha256'],'--out',str(R/'result01'),'--candidate-lines','1536']
def limits():
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024,128*1024));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
r=dict(state='RUNNING offline capacity software readback',authority=bind(R/'authority.FINAL.json'),supervisor=bind(Path(__file__)),board_actions=False,other_charges_unchanged=True)
try:
 with (R/'worker.log').open('xb') as log:r['ownership']=owned.run(argv,P,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,120,guard,limits)
 assert r['ownership']['returncode']==0 and r['ownership']['failure'] is None and not r['ownership']['owned_group_remaining']
 r.update(state='PASS offline software payload/NBF/static/46MiB-bounds readback; no dynamic/native/FPGA claim',report=bind(R/'result01/software-readback.json'),final_resources=guard())
except BaseException as e:
 r.update(state='FAIL preserved offline capacity software readback',error=repr(e),ownership=getattr(e,'owned_receipt',r.get('ownership')));raise
finally:wr(R/'session.json',r)
print(json.dumps(r,indent=2))
