from pathlib import Path
import json,hashlib,stat,os,time,datetime,shutil
OUT=Path('/home/coyang/fpga-artifacts/context-resume/obsolete-source-helper-HOME-freeze-20261123');OUT.mkdir(exist_ok=False)
H=Path('/home/coyang/zynq-parrot-linux-host-observer/research');D=Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research')
F={
 'matched256':([Path('/home/coyang/zp-retained256-source-20261122')],[H/'retained256-qualification-20261122']),
 'scratch':([Path('/home/coyang/zynq-parrot-linux-scratch-profile')],[H/'scratch-trace-profile-preparation-20261122',H/'scratch-trace-profile-preparation02-20261122']),
 'borrow1792':([Path('/home/coyang/zynq-parrot-linux-borrow-profile')],[D/n for n in ('retained-borrow-trace0-preparation-20261122','retained-borrow-trace0-preparation02-20261122','retained-borrow-trace0-preparation03-20261122','retained-borrow-trace0-closure-preparation-20261122')]),
 'borrow256':([Path('/home/coyang/zynq-parrot-linux-borrow256-profile')],[D/'retained-borrow256-trace0-preparation-20261122'])}
ROOTS=[p for source,helpers in F.values() for p in source+helpers];START=time.monotonic()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for x in iter(lambda:f.read(1048576),b''):h.update(x)
 return h.hexdigest()
def bind(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def absence():
 bad=[];names={'make','gmake','ninja','gcc','g++','cc1','cc1plus','verilator','verilator_bin','vivado','xelab','xvlog','xsim','xsimk','launch_synthesis.sh','run_vivado_2024_2.sh'}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   raw=(p/'stat').read_text();f=raw[raw.rfind(')')+2:].split();comm=(p/'comm').read_text().strip();argv=[s.decode(errors='replace')for s in(p/'cmdline').read_bytes().split(b'\0')if s]
   if f[0]!='Z' and (comm in names or any(any(a==str(r)or a.startswith(str(r)+'/')for r in ROOTS)for a in argv)):bad.append(dict(pid=int(p.name),startticks=int(f[19]),comm=comm,argv=argv))
  except(FileNotFoundError,ProcessLookupError):pass
 assert not bad,bad
 return dict(global_compiler_vendor_and_named_original_producers_absent=True,matches=bad)
def inventory():
 rows=[]
 for root in ROOTS:
  assert root.is_dir()and not root.is_symlink()
  for p in [root]+sorted(root.rglob('*')):
   assert time.monotonic()-START<120
   s=p.lstat();q=dict(path=str(p),mode=s.st_mode,device=s.st_dev,inode=s.st_ino,nlink=s.st_nlink,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,uid=s.st_uid,gid=s.st_gid)
   assert s.st_dev==2050,(str(p),'not HOME')
   if stat.S_ISLNK(s.st_mode):q.update(kind='symlink',target=os.readlink(p))
   elif stat.S_ISDIR(s.st_mode):q.update(kind='directory')
   else:assert stat.S_ISREG(s.st_mode);q.update(kind='file',bytes=s.st_size,sha256=sha(p))
   rows.append(q)
 return rows
before=absence();rows=inventory();assert inventory()==rows;after=absence()
def old_size(p):return sum(x.stat().st_size for x in p.rglob('*')if x.is_file())
charged={}
for label,(sources,helpers)in F.items():
 source=sum(old_size(p)for p in sources);helper=sum(old_size(p)for p in helpers)
 assert source<=4194304 and helper<=8388608,(label,source,helper)
 charged[label]=dict(source_paths=list(map(str,sources)),helper_paths=list(map(str,helpers)),original_source_cap=4194304,original_helper_union_cap=8388608,actual_source_logical_bytes=source,actual_helper_logical_bytes=helper,unused_future_write_bytes_closed=(4194304-source)+(8388608-helper),new_unused_future_bytes=0)
release=sum(q['unused_future_write_bytes_closed']for q in charged.values());assert 0<release<=36260188
inv=OUT/'inventory.json';inv.write_text(json.dumps(dict(roots=list(map(str,ROOTS)),members=rows),indent=2)+'\n')
authority=D/'retained-borrow256-trace0-preparation-20261122/materialize.py'
r=dict(ROOT_verified=True,state='PASS explicit stop/freeze of four obsolete HOME source/helper families; all original HOME bytes/modes/links/membership preserved',original_budget_authority=bind(authority),inventory=bind(inv),families=charged,old_BASE_HOME_bytes=36260188,unused_HOME_future_write_bytes_closed=release,new_BASE_HOME_bytes=36260188-release,RUN_future_unchanged_bytes=1156926898,logging_future_unchanged_bytes=134217728,metadata_future_unchanged_bytes=4194304,no_deletion_or_repack=True,all_current_actual_bytes_remain_charged=True,original_caps_and_historical_receipts_unchanged=True,before=before,after=after,seconds=time.monotonic()-START,scope='Only unused writes into these named obsolete source/helper roots stop. Future changes need new priced authority. No durable-family/RUN, physical correctness or performance acceptance inferred.',UTC=datetime.datetime.now(datetime.timezone.utc).isoformat())
p=OUT/'ROOT-unused-HOME-future-freeze.json';p.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(receipt=bind(p),closed=release,new_BASE_HOME=r['new_BASE_HOME_bytes'],members=len(rows)),indent=2))
