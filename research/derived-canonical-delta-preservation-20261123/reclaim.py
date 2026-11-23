"""Lease-protected lossless retirement of three redundant derived gzip caches."""
from pathlib import Path
import json,hashlib,os,fcntl,signal,time,stat,shutil,datetime
O=Path(__file__).parent;I=Path('/home/coyang/fpga-artifacts/context-resume/csr768-native-authority-20261123/HOME-derived-canonical-byte-diff.json');START=time.monotonic();FDS={};REMOVED=[];broken=[]
assert hashlib.sha256(I.read_bytes()).hexdigest()=='949cc40dfc7f4844a5b1a61eb0e8bdb42c3ace44bda3952d286f78685e864fd0'
entries=json.loads(I.read_text())['entries'];assert len(entries)==3 and sum(len(x['patches'])for x in entries)==6
rows={r['path']:r for e in entries for r in(e['base'],e['target'])};assert len(rows)==5
assert all(r['device']==2050 and r['nlink']==1 and len(r['sha256'])==64 for r in rows.values())
assert Path('/proc/sys/fs/lease-break-time').read_text().strip()=='45'
assert json.loads((O/'lease-test-result02.json').read_text())['all_child_groups_gone']is True
assert not(O/'manifest.json').exists()and not(O/'complete.json').exists()
def signal_abort(s,f):broken.append(s);raise RuntimeError('lease break/deadline before complete retirement')
signal.signal(signal.SIGIO,signal_abort);signal.signal(signal.SIGALRM,signal_abort);signal.alarm(30)
def digest_file(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def durable(p,v):
 raw=(json.dumps(v,indent=2)+'\n').encode();assert len(raw)<1024**2
 with p.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
 d=os.open(O,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(d)
 finally:os.close(d)
def identity(path,r,fd):
 s=Path(path).lstat();f=os.fstat(fd)
 assert stat.S_ISREG(s.st_mode)and(s.st_dev,s.st_ino)==(f.st_dev,f.st_ino)
 for key,value in dict(bytes=s.st_size,mode=stat.S_IMODE(s.st_mode),device=s.st_dev,inode=s.st_ino,nlink=s.st_nlink,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns).items():assert r[key]==value,(path,key)
 assert s.st_uid==os.getuid()
def guard():
 assert time.monotonic()-START<30 and not broken
 assert sum(p.stat().st_size for p in O.iterdir()if p.is_file())<1024**2
 assert sum(p.stat().st_size for p in O.glob('*.py'))<=32768
 assert shutil.disk_usage(O).free>=2058498048
 for path,fd in FDS.items():
  assert fcntl.fcntl(fd,fcntl.F_GETLEASE)==fcntl.F_WRLCK
  if path not in REMOVED:identity(path,rows[path],fd)
def fd_hash(fd,n):
 h=hashlib.sha256()
 for offset in range(0,n,1048576):h.update(os.pread(fd,min(1048576,n-offset),offset))
 return h.hexdigest()
rec=dict(state='RUNNING lease-protected derived-cache delta preservation',removed_paths=REMOVED,source_namespace_no_old_producer_declared_by_ROOT=True,current_768_outputs='fresh disjoint RUN scoped-csr01 namespace',whole_artifact_subcap=1048576,source_subcap=32768,funding='Inside existing4MiB metadata envelope; full native1GiB/32MiB, BASE/logging/floors retained',no_raw_trace_source_model_image_or_proof_removed=True)
try:
 assert shutil.disk_usage(O).free>=2058498048
 for path,r in rows.items():
  fd=os.open(path,os.O_RDWR|os.O_CLOEXEC|os.O_NOFOLLOW);FDS[path]=fd;identity(path,r,fd)
  fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_WRLCK)
 guard()
 for path,r in rows.items():assert fd_hash(FDS[path],r['bytes'])==r['sha256']
 # Independent full reconstruction uses64KiB chunks and compares each byte
 # with the original descriptor; the earlier producer used1MiB diff discovery.
 for e in entries:
  base,target=e['base'],e['target'];edits=dict(e['patches']);h=hashlib.sha256();seen=set()
  assert len(edits)==2
  for offset in range(0,target['bytes'],65536):
   b=bytearray(os.pread(FDS[base['path']],min(65536,target['bytes']-offset),offset))
   for pos,value in edits.items():
    if offset<=pos<offset+len(b):b[pos-offset]=value;seen.add(pos)
   actual=os.pread(FDS[target['path']],len(b),offset);assert actual==b
   h.update(b)
  assert seen==set(edits)and h.hexdigest()==target['sha256'];guard()
 manifest=dict(schema='lossless-derived-canonical-gzip-delta-v1',entries=entries,all_compressed_bytes_independently_reconstructed=True,base_files_remain_full_durable_HOME=True,retired_materializations_require_exact_restore_before_historical_replay=True,source_input=dict(path=str(I),sha256=digest_file(I)),restore_source=dict(path=str(O/'restore.py'),sha256=digest_file(O/'restore.py')),historical_proof_pins_unchanged=True)
 durable(O/'manifest.json',manifest)
 assert json.loads((O/'manifest.json').read_text())==manifest
 restorefd=os.open(O/'restore.py',os.O_RDONLY)
 try:os.fsync(restorefd)
 finally:os.close(restorefd)
 rec.update(state='VERIFIED durable exact base+delta+restore; reclamation follows',manifest_sha256=digest_file(O/'manifest.json'),whole_reconstructed_target_bytes=sum(e['target']['bytes']for e in entries),actual_exclusive_kernel_leases=5,all_original_SHA_mode_identity_checked=True)
 durable(O/'verified-before-reclaim.json',rec);guard()
 for e in entries:
  path=e['target']['path'];guard();identity(path,e['target'],FDS[path]);Path(path).unlink();REMOVED.append(path)
  # Journal each path immediately; the durable recovery payload predates all.
  tmp=O/'progress.json.tmp';tmp.write_text(json.dumps(dict(removed_paths=list(REMOVED)))+'\n');tmp.replace(O/'progress.json')
 rec.update(state='PASS exact derived-cache bytes preserved by full bases+delta; three redundant materializations retired',all_three_retired=True,no_unqualified_FD_namespace_claim=True,no_FD_permission_exception=True,scope='Only3 untracked historical derived gzip caches. Two fullbases/rawFSTs/models/source/proofs unchanged; exact restoration required before old direct path validators.')
except BaseException as e:rec.update(state='FAIL preserved delta operation; partial retirement explicitly journaled',error=repr(e));raise
finally:
 signal.alarm(0)
 # Keep notification armed as a flag until every descriptor is closed.
 signal.signal(signal.SIGIO,lambda s,f:broken.append(s))
 cleanup=[]
 for path,fd in FDS.items():
  try:
   if fcntl.fcntl(fd,fcntl.F_GETLEASE)!=fcntl.F_UNLCK:fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_UNLCK)
  except OSError as e:cleanup.append(dict(path=path,error=repr(e)))
  finally:os.close(fd)
 rec.update(removed_paths=list(REMOVED),cleanup_notes=cleanup,all_descriptors_closed=True,elapsed_seconds=time.monotonic()-START,actual_HOME_free_after_close=shutil.disk_usage(O).free,UTC=datetime.datetime.now(datetime.timezone.utc).isoformat())
 durable(O/('complete.json'if rec['state'].startswith('PASS')else'FAILED.json'),rec)
print(json.dumps(rec))
