import sys,json,hashlib,os,resource,time,shutil,datetime,stat
from pathlib import Path
sys.dont_write_bytecode=True
H=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr1536-opt-whole-cad-preparation03-20261122');sys.path.insert(0,str(H))
import software_owned_v2 as owned
from budget import violations
R=Path(__file__).parent;P=Path('/home/coyang/zynq-parrot-retained-metadata/research/csr1536-capacity-semantic-adapter-20261122')
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
 assert size(P)<=128*1024,'semantic source128KiB cap; actual paid HOME and metadata reserve retained'
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

refs=json.loads((R/'references.json').read_text());inputs=[bind(R/'worker.py'),bind(R/'references.json')]
handoff=json.loads((P/'handoff.json').read_text())
for r in handoff['files']:assert bind(Path(r['path']))==r;inputs.append(r)
for row in refs:inputs.extend([row['acceptance'],row['proof'],row['counters']])
tools=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-joint-build-preparation-20261122/static_tools.py');assert bind(tools)['sha256']=='5af0b737ab6327eeb8d0287c26f0d192f43b6b5a9020fd1d155586581e71a56c'
a=dict(ROOT_approved=True,action='metadata-constructors-only',inputs=inputs,static_tools=bind(tools),resources=dict(metadata_cap_bytes=128*1024,metadata_subset_existing_4MiB=True,worker_AS_bytes=256*1024**2,wall_seconds=120),CAD_admission=bind(A/'admission.FINAL.json'),initial_resources=guard())
wr(R/'authority.json',a);wr(R/'authority-binding.json',bind(R/'authority.json'))
def limits():
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024,128*1024));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
r=dict(state='RUNNING semantic constructor metadata check',authority=bind(R/'authority.json'),supervisor=bind(Path(__file__)),no_model_or_FST_or_board=True)
try:
 with (R/'worker.log').open('xb') as log:r['ownership']=owned.run(['/usr/bin/python3','-B',R/'worker.py'],R,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,120,guard,limits)
 assert r['ownership']['returncode']==0 and r['ownership']['failure'] is None and not r['ownership']['owned_group_remaining']
 r.update(state='PASS metadata prequalification only; no dynamic1536/FPGA claim',result=bind(R/'result.json'),final_resources=guard())
except BaseException as e:r.update(state='FAIL preserved semantic metadata prequalification',error=repr(e),ownership=getattr(e,'owned_receipt',r.get('ownership')));raise
finally:wr(R/'session.json',r)
print(json.dumps(r,indent=2))
