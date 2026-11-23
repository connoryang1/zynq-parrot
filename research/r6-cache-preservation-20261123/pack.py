from pathlib import Path
import hashlib,json,os,resource,tarfile,time
OUT=Path(__file__).resolve().parent
M=json.loads((OUT/'manifest.json').read_text());ROWS=M['rows']
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
resource.setrlimit(resource.RLIMIT_FSIZE,(67108864,67108864))
resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
START=time.monotonic()
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def check(r):
 p=Path(r['path']);s=p.lstat()
 assert (s.st_size,s.st_mode,s.st_dev,s.st_ino,s.st_mtime_ns)==tuple(r[k]for k in ['bytes','mode','device','inode','mtime_ns'])
 assert digest(p)==r['sha256']
 assert time.monotonic()-START<180
# Only these previously identified nonbuild desktop processes may have an
# unreadable FD namespace. No other process, metadata operation, or identity
# change is exempt; unreadable FDs are recorded rather than claimed scanned.
KNOWN_DESKTOP_FD_IDENTITIES={12456:('(sd-pam)',67838353),164612:('gnome-keyring-d',78172576)}
def known_desktop_fd_denial(proc,error):
 try:
  pid=int(proc.name);expected=KNOWN_DESKTOP_FD_IDENTITIES.get(pid)
  if expected is None or error.errno not in {1,13} or error.filename is None:return None
  filename=os.fsdecode(error.filename);fdroot=str(proc/'fd')
  if filename!=fdroot and not(filename.startswith(fdroot+'/')and filename[len(fdroot)+1:].isdigit()):return None
  if os.getuid()!=1001 or proc.stat().st_uid!=1001:return None
  def identity():
   raw=(proc/'stat').read_text();end=raw.rfind(')');fields=raw[end+2:].split()
   if int(raw.split(' ',1)[0])!=pid:return None
   return (raw[raw.find('(')+1:end],int(fields[19]))
  before=identity()
  if before!=expected or (proc/'comm').read_text().strip()!=expected[0]:return None
  if identity()!=before or proc.stat().st_uid!=1001:return None
  return dict(pid=pid,comm=expected[0],startticks=expected[1],uid=1001,denied_fd_path=filename,errno=error.errno,scope='Known desktop FD permission exception only; contents not inspected')
 except (FileNotFoundError,ProcessLookupError,PermissionError):return None
targets={r['path']for r in ROWS};denied=[];desktop_fd_exceptions=[]
for proc in Path('/proc').glob('[0-9]*'):
 try:
  if proc.stat().st_uid!=os.getuid():continue
  comm=(proc/'comm').read_text().strip()
  assert comm not in {'make','gmake','ninja','gcc','g++','cc1','cc1plus','ar','verilator','verilator_bin'},(str(proc),comm)
  for fd in (proc/'fd').iterdir():
   try:assert os.readlink(fd)not in targets,('open cache',str(fd))
   except FileNotFoundError:pass
 except (FileNotFoundError,ProcessLookupError):pass
 except PermissionError as error:
  exception=known_desktop_fd_denial(proc,error)
  if exception is None:denied.append(str(proc))
  else:desktop_fd_exceptions.append(exception)
assert not denied,denied
for r in ROWS:check(r)
archive=OUT/'caches.tar.xz';assert not archive.exists()
with tarfile.open(archive,'w:xz',preset=1)as tar:
 for r in ROWS:tar.add(r['path'],arcname=r['relative'],recursive=False)
assert archive.stat().st_size<=67108864
expected={r['relative']:r for r in ROWS};seen=set()
with tarfile.open(archive,'r:xz')as tar:
 for member in tar:
  assert member.name in expected and member.name not in seen;seen.add(member.name);r=expected[member.name]
  assert member.isfile()and member.size==r['bytes']and member.mode==(r['mode']&4095)
  f=tar.extractfile(member);h=hashlib.sha256()
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
  assert h.hexdigest()==r['sha256']
assert seen==set(expected)
for r in ROWS:check(r)
receipt=dict(state='PASS all archive bytes/modes/member identities and stable originals; authorized inactive cache reclamation follows',archive_bytes=archive.stat().st_size,archive_sha256=digest(archive),cache_files=len(ROWS),original_bytes=M['total_bytes'],all_bytes_recoverable=True,fd_permission_exceptions=desktop_fd_exceptions,elapsed_seconds=time.monotonic()-START)
(OUT/'verified-before-reclaim.json').write_text(json.dumps(receipt,indent=2)+'\n')
for r in ROWS:Path(r['path']).unlink()
assert all(not Path(r['path']).exists()for r in ROWS)
receipt.update(state='PASS inactive generated caches packed and reclaimed; every byte recoverable',net_reclaimed_bytes=M['total_bytes']-sum(p.stat().st_size for p in OUT.iterdir()if p.is_file()),elapsed_seconds=time.monotonic()-START)
(OUT/'complete.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
