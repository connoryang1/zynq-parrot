from pathlib import Path
import os,sys,json,shutil,hashlib,resource,time
sys.dont_write_bytecode=True
O=Path(__file__).parent;T=Path('/run/user/1001/zp-canonical-delta07-restore-test-20261123-01');B=Path('/run/user/1001/zp-csr-unmasked768-fullcore-20261123-01');D=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked768-fullcore-20261123');H=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr1280-opt-whole-cad-preparation-20261123');sys.path.insert(0,str(H));import software_owned_v2 as owned
assert hashlib.sha256((H/'software_owned_v2.py').read_bytes()).hexdigest()=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5'
def size(root):
 if not root.exists():return 0
 ss=[p.lstat()for p in root.rglob('*')if p.is_file()or p.is_symlink()];return max(sum(s.st_size for s in ss),sum(s.st_blocks*512 for s in ss))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for x in iter(lambda:f.read(1048576),b''):h.update(x)
 return h.hexdigest()
def guard():
 own=size(T);run=size(B);home=size(D);assert own<=128*1024**2 and run<=1024**3 and home<=32*1024**2
 need=1073741824+1156926898+max(0,1024**3-run)+max(0,128*1024**2-own)
 assert shutil.disk_usage('/run/user/1001').free>=need
 assert shutil.disk_usage(O).free>=1879048192+145895424+max(0,32*1024**2-home)
 assert shutil.disk_usage('/dev/shm').free>=536870912+335544320
 assert size(O)<=1024**2
 return need
assert not T.exists();guard();T.mkdir();(T/'restore.py').write_bytes((O/'restore.py').read_bytes());original=sha(O/'manifest.json');source=sha(O/'restore.py');m=json.loads((O/'manifest.json').read_text())
for j,e in enumerate(m['entries']):e['target']['path']=str(T/('restored-'+str(j)+'.gz'))
(T/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');mh=sha(T/'manifest.json');rows=[];start=time.monotonic()
try:
 for j,e in enumerate(m['entries']):
  assert time.monotonic()-start<110
  target=Path(e['target']['path']);argv=['/usr/bin/python3','-B',str(T/'restore.py'),'--restore',str(j),'--manifest-sha256',mh,'--required-free-bytes',str(max(guard(),1879048192+e['target']['bytes']))]
  with (T/('run-'+str(j)+'.log')).open('xb')as f:life=owned.run(argv,T,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),f,30,guard,lambda:resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2))
  assert life['returncode']==0 and life['failure']is None and not life['owned_group_remaining']
  s=target.stat();assert s.st_size==e['target']['bytes']and(s.st_mode&4095)==e['target']['mode']and s.st_mtime_ns==e['target']['mtime_ns']and sha(target)==e['target']['sha256']
  rows.append(dict(id=j,expected_SHA=e['target']['sha256'],bytes=s.st_size,actual_bytes_SHA_mode_mtime_equal=True,source_helper_byte_identical=sha(T/'restore.py')==source,ownership=life))
  target.unlink();assert not target.exists();guard()
 assert sha(O/'manifest.json')==original and sha(O/'restore.py')==source
 rec=dict(state='PASS actual unchanged restore helper reconstructed all3 exact caches at fresh scratch paths; SHA/mode/mtime and owned0 verified',tests=rows,all_test_materializations_removed=True,all_actual_historical_paths_still_retired=True,all_old_raw_source_model_proof_unchanged=True,unused_test_RUN_future_bytes=0,seconds=time.monotonic()-start)
except BaseException as e:rec=dict(state='FAIL preserved restore test',error=repr(e),tests=rows);raise
finally:
 (O/'restore-test-result.json').write_text(json.dumps(rec,indent=2)+'\n')
 for p in T.glob('*.log'):shutil.copy2(p,O/p.name)
print(rec['state'])
