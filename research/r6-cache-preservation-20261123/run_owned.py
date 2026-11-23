from pathlib import Path
import sys,json,hashlib,os,shutil,stat
sys.dont_write_bytecode=True
H=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr1280-native-preparation-20261122')
sys.path.insert(0,str(H))
import software_owned_v2 as owned
O=Path(__file__).parent
def bind(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def size(p):
 if not p.exists():return 0
 ss=[x.lstat() for x in p.rglob('*') if not x.is_symlink()]
 return max(sum(s.st_size for s in ss if stat.S_ISREG(s.st_mode)),sum(s.st_blocks*512 for s in ss)+p.stat().st_blocks*512)
assert bind(H/'software_owned_v2.py')['sha256']=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5'
r=json.loads((O/'ROOT-scope-review.json').read_text());assert r['ROOT_approved']
assert bind(O/'pack.py')['sha256']==r['packer_sha256'] and bind(O/'manifest.json')['sha256']==r['manifest_sha256']
P=Path(r['profile']['path']);assert bind(P)['sha256']==r['profile']['sha256'];q=json.loads(P.read_bytes())
BASE=Path('/run/user/1001/zp-csr-unmasked1280-fullcore-20261122-01');D=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked1280-fullcore-20261122')
def guard():
 run,home,own=size(BASE),size(D),size(O)
 assert run<=1024**3 and home<=32*1024**2 and own<=66*1024**2
 needRUN=q['RUN_floor_bytes']+1024**3-run+q['other_RUN_bytes']
 needHOME=q['HOME_floor_bytes']+32*1024**2-home+q['other_HOME_bytes']+66*1024**2-own
 assert shutil.disk_usage(BASE).free>=needRUN
 assert shutil.disk_usage(O).free>=needHOME
 assert shutil.disk_usage('/dev/shm').free>=q['SHM_floor_bytes']+q['other_SHM_bytes']
 mem=next(int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:'));assert mem>=q['required_MemAvailable_bytes']
 return dict(RUN=run,baseHOME=home,own=own,requiredRUN=needRUN,requiredHOME=needHOME,MemAvailable=mem)
receipt=dict(state='RUNNING ROOT owned inactive RTD preservation',scope=bind(O/'ROOT-scope-review.json'),initial=guard())
try:
 with (O/'pack.log').open('xb') as log: receipt['ownership']=owned.run(['/usr/bin/python3','-B',O/'pack.py'],O,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,185,guard,lambda:None)
 assert receipt['ownership']['returncode']==0 and receipt['ownership']['failure'] is None and not receipt['ownership']['owned_group_remaining']
 receipt.update(state='PASS bounded RTD archive/readback/reclaim; all bytes recoverable',complete=bind(O/'complete.json'),final=guard())
except BaseException as e:
 receipt.update(state='FAIL preserved cache-pack attempt',error=repr(e),ownership=getattr(e,'owned_receipt',receipt.get('ownership')));raise
finally:
 (O/'ROOT-owned-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
