from pathlib import Path
import sys,json,hashlib,os,shutil,stat
sys.dont_write_bytecode=True
H=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr1280-opt-whole-cad-preparation-20261123')
sys.path.insert(0,str(H))
import software_owned_v2 as owned
O=Path(__file__).parent
A=Path('/home/coyang/fpga-artifacts/context-resume/csr-opt1280-fpga-preparation-20261123/preparation01/admission.FINAL.json')
def bind(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def size(p):
 if not p.exists():return 0
 total=logical=0
 for base,dirs,files in os.walk(str(p),followlinks=False):
  for name in dirs+files:
   try:s=(Path(base)/name).lstat()
   except FileNotFoundError:continue
   if stat.S_ISLNK(s.st_mode):continue
   total+=s.st_blocks*512
   if stat.S_ISREG(s.st_mode):logical+=s.st_size
 return max(total+p.stat().st_blocks*512,logical)
assert bind(A)['sha256']=='bc473480db6890a8602d28cc25d258b46be93415825871a9edbed63f64cb96b4'
d=json.loads(A.read_bytes());L=d['resources'];C=d['configuration']
assert bind(H/'software_owned_v2.py')['sha256']=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5'
r=json.loads((O/'ROOT-scope-review02.json').read_bytes());assert r['ROOT_approved']
assert bind(O/'pack02.py')['sha256']==r['packer_sha256'] and bind(O/'manifest.json')['sha256']==r['manifest_sha256']
def guard():
 source,work=size(Path(C['prepared_source_root'])),size(Path(C['work_root']))
 evidence=sum(size(Path(p))for p in C['evidence_roots']);own=size(O)
 assert source<=L['source_cap_bytes'] and work<=L['work_cap_bytes'] and evidence<=L['evidence_cap_bytes'] and own<=34*1024**2
 runNeed=L['work_floor_bytes']+max(0,L['source_cap_bytes']-source)+max(0,L['work_cap_bytes']-work)+L['other_work_future_bytes']
 homeNeed=L['home_floor_bytes']+max(0,L['evidence_cap_bytes']-evidence)+L['other_home_future_bytes']+max(0,34*1024**2-own)
 assert shutil.disk_usage('/run/user/1001').free>=runNeed
 assert shutil.disk_usage(O).free>=homeNeed
 assert shutil.disk_usage('/dev/shm').free>=L['shm_floor_bytes']+L['other_shm_future_bytes']
 mem=next(int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines()if s.startswith('MemAvailable:'));assert mem>=8*1024**3
 return dict(source=source,work=work,evidence=evidence,own=own,RUN_required=runNeed,HOME_required=homeNeed,MemAvailable=mem)
rec=dict(state='RUNNING ROOT scoped old1536 cache preservation; currentCAD funded unchanged',scope=bind(O/'ROOT-scope-review02.json'),initial=guard())
try:
 with (O/'pack.log').open('xb') as log:rec['ownership']=owned.run(['/usr/bin/python3','-B',O/'pack02.py'],O,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,125,guard,lambda:None)
 assert rec['ownership']['returncode']==0 and rec['ownership']['failure'] is None and not rec['ownership']['owned_group_remaining']
 rec.update(state='PASS byte-recoverable147 old1536 caches packed/reclaimed; current1280/CAD unchanged',complete=bind(O/'complete.json'),final=guard(),unused_cachepack_HOME_future_bytes=0)
except BaseException as e:
 rec.update(state='FAIL preserved cachepack; no cap extension',error=repr(e),ownership=getattr(e,'owned_receipt',rec.get('ownership')));raise
finally:(O/'ROOT-owned-receipt.json').write_text(json.dumps(rec,indent=2)+'\n')
print(json.dumps(rec))
