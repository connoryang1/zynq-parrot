#!/usr/bin/env python3
"""Two-phase ROOT-only coverage review/unused RUN-write stop; KEEP all pool files."""
import argparse,gzip,hashlib,json,os,resource,shutil,signal,stat,tarfile,time
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import owner_scan
import transport_role
HERE=Path(__file__).resolve().parent
OUT=Path('/home/coyang/fpga-artifacts/context-resume/obsolete-native-RUN-freeze-20261123-03')
GROUPS={
 'matched':dict(roots=['/run/user/1001/zp-retained256-fullcore-20261122-02','/run/user/1001/zp-retained256-fullcore-20261122-01'],charge=329830081),
 'scratch':dict(roots=['/run/user/1001/zp-retained-scratch-trace0-fullcore-20261122-02','/run/user/1001/zp-retained-scratch-trace0-fullcore-20261122-01'],charge=397346275),
 'borrow1792':dict(roots=['/run/user/1001/zp-retained-borrow-trace0-fullcore-20261122-01','/run/user/1001/zp-retained-borrow-trace0-fullcore-20261122-02','/run/user/1001/zp-retained-borrow-trace0-fullcore-20261122-03'],charge=396196110)}
ROOTS=[Path(p)for g in GROUPS.values()for p in g['roots']]
EXPECTED_ABSENT=[Path('/run/user/1001/zp-retained-borrow-trace0-fullcore-20261122-01'),Path('/run/user/1001/zp-retained-borrow-trace0-fullcore-20261122-02')]
PRIOR_FAILURE=dict(path='/home/coyang/fpga-artifacts/context-resume/obsolete-native-RUN-freeze-20261123-02/prepare-session.json',bytes=437,sha256='5c2c6a72001d639a0e6e0e06ea71993a6adf80184420d577c528360d0a740fb2')
ALLOW=[dict(pid=12456,startticks=67838353,ppid=12455,comm='(sd-pam)',euid=1001),dict(pid=164612,startticks=78172576,ppid=12455,comm='gnome-keyring-d',euid=1001)]
META=8*1024**2;DELTA=64*1024**2;SOURCE=128*1024;DEADLINE=600
A=None;START=None;LAST=0

def require(v,m):
 if not v:raise ValueError(m)
def used(directory):return sum(p.lstat().st_size for p in directory.rglob('*')if not stat.S_ISDIR(p.lstat().st_mode))if directory.exists()else 0
def guard(force=False):
 global LAST
 now=time.monotonic();require(now-START<=DEADLINE,'fixed600s phase deadline')
 if not force and now-LAST<0.25:return
 LAST=now
 meta=used(OUT)-((OUT/'uncovered.tar.gz').stat().st_size if (OUT/'uncovered.tar.gz').exists()else 0)
 delta=(OUT/'uncovered.tar.gz').stat().st_size if (OUT/'uncovered.tar.gz').exists()else 0
 source=used(HERE);require(meta<=META and delta<=DELTA and source<=SOURCE,'8MiB metadata/64MiB uncovered/128KiB source caps')
 q=A['resources'];require(shutil.disk_usage(HERE).free>=q['required_HOME_free_without_SELF']+META-meta+DELTA-delta+SOURCE-source,'HOME floor+ALL_OTHER+full remaining SELF')
 require(shutil.disk_usage('/run/user/1001').free>=q['required_RUN_free_bytes'],'unchanged RUN reserve before accepted stop')
 require(shutil.disk_usage('/dev/shm').free>=q['required_SHM_free_bytes'],'unchanged SHM reserve')
 mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines()if l.startswith('MemAvailable:'));require(mem>=q['required_MemAvailable_bytes'],'ROOT-priced host-memory headroom')
def digest_stream(stream):
 h=hashlib.sha256();n=0
 while True:
  b=stream.read(1024**2)
  if not b:break
  n+=len(b);h.update(b);guard()
 return n,h.hexdigest()
def bind(p):
 p=Path(p)
 with p.open('rb')as f:n,h=digest_stream(f)
 return dict(path=str(p),bytes=n,sha256=h)
def verify(r):require(bind(r['path'])=={k:r[k]for k in ('path','bytes','sha256')},'binding drift '+r['path'])
def read(r):verify(r);return json.loads(Path(r['path']).read_text())
def write(p,v):
 raw=(json.dumps(v,separators=(',',':'))+'\n').encode();current=used(OUT)-((OUT/'uncovered.tar.gz').stat().st_size if (OUT/'uncovered.tar.gz').exists()else 0)
 require(current+len(raw)<=META,'metadata cap before write')
 t=p.with_name(p.name+'.tmp')
 with t.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
 t.replace(p);fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
 guard(True)
def rowstat(p):
 s=p.lstat();return dict(path=str(p),mode=s.st_mode,device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,nlink=s.st_nlink,bytes=s.st_size,allocated_bytes=s.st_blocks*512,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
def root_presence():
 require(A['ROOT_expected_absent_roots']==list(map(str,EXPECTED_ABSENT)),'only exact ROOT-declared borrow01/02 may be absent')
 parent=Path('/run/user/1001');expected=A['ROOT_absent_real_parent_identity']
 require(set(expected)=={'path','device','inode'}and expected['path']==str(parent),'exact ROOT parent identity fields')
 def parent_check():
  q=parent.lstat();require(stat.S_ISDIR(q.st_mode)and dict(path=str(parent),device=q.st_dev,inode=q.st_ino)==expected,'real parent device/inode differs')
 parent_check();result=[]
 for root in ROOTS:
  if root in EXPECTED_ABSENT:
   parent_check()
   try:root.lstat()
   except FileNotFoundError:pass
   else:raise ValueError('ROOT expected-absent path exists or is a symlink: '+str(root))
   parent_check()
   try:root.lstat()
   except FileNotFoundError:pass
   else:raise ValueError('ROOT expected-absent path appeared: '+str(root))
   result.append(dict(path=str(root),presence='ROOT-expected-absent; repeated lstat ENOENT',real_parent_identity=expected))
  else:
   q=root.lstat();require(stat.S_ISDIR(q.st_mode),'exact existing real old ROOT pool')
   result.append(dict(path=str(root),presence='present-real-directory',device=q.st_dev,inode=q.st_ino,mode=q.st_mode))
 parent_check();return result

def inventory():
 presence=root_presence();rows=[]
 for root in ROOTS:
  if root in EXPECTED_ABSENT:continue
  require(root.is_dir()and not root.is_symlink(),'exact existing old ROOT pool')
  todo=[root]
  while todo:
   p=todo.pop();r=rowstat(p)
   if stat.S_ISLNK(r['mode']):r.update(kind='symlink',target=os.readlink(p));r['sha256']=hashlib.sha256(os.fsencode(r['target'])).hexdigest()
   elif stat.S_ISDIR(r['mode']):r['kind']='directory';todo.extend(sorted(p.iterdir(),reverse=True))
   else:
    require(stat.S_ISREG(r['mode']),'unexpected special old pool member')
    b=bind(p);require(rowstat(p)==r,'file changed during full SHA read');r.update(kind='file',sha256=b['sha256'])
   rows.append(r);require(len(rows)<=100000,'bounded inventory records');guard()
 require(root_presence()==presence,'root presence changed during inventory')
 return sorted(rows,key=lambda x:x['path'])
def scan():
 presence=root_presence()
 proof=read(A['ROOT_transport_role_proof']);worker=next(r for r in A['source_inputs']if r['path']==str(HERE/'freeze_run.py'))
 before=transport_role.check(proof,worker['sha256'],str(OUT));extra=transport_role.allow_identity()
 result=owner_scan.owner_scan(ROOTS,ALLOW+[extra])
 after=transport_role.check(proof,worker['sha256'],str(OUT))
 require(before==after,'authenticated transport role changed during qualified scan')
 skipped=result['ROOT_exact_nonproducer_services_skipped'];found=[r for r in skipped if r['identity']==extra]
 require(len(found)==1,'exact transport exception actually accounted')
 result['ROOT_exact_nonproducer_services_skipped']=[r for r in skipped if r['identity']!=extra]
 result['ROOT_authenticated_transport_nonproducer']=dict(proof=A['ROOT_transport_role_proof'],before=before,after=after,scope='Exact ROOT-declared established PTY to tmux attachment; not FD/maps inspection',uninspected_views=['transport cwd','transport exe','transport fd','transport maps','root parent nonmetadata views'],all_other_user_processes_scanned_normally=True)
 require(root_presence()==presence,'root presence changed during owner scan');result['root_presence']=presence
 return result
def add(index,r,origin):
 require(type(r['bytes'])is int and r['bytes']>=0 and len(r['sha256'])==64,'durable content schema')
 index.setdefault((r['bytes'],r['sha256']),[]).append(dict(path=r['path'],origin=origin))
def safe_archive(r):
 require(any(str(r['path']).startswith('/home/coyang/fpga-artifacts/context-resume/'+p+'/')for p in ['retained256-qualification-20261122','retained-scratch-trace0-fullcore-20261122','retained-borrow-trace0-fullcore-20261122']),'fixed durable archive families only')
 verify(r)
def tar_read(record,entries,index):
 safe_archive(record);expected={r['member']:r.get('original',r)for r in entries};require(len(expected)==len(entries),'unique archived names');seen=set()
 with tarfile.open(record['path'],'r|gz')as tar:
  for m in tar:
   require(m.name in expected and m.name not in seen,'unknown/duplicate archived member');seen.add(m.name);r=expected[m.name]
   if m.isdir():require(r.get('type')=='directory','directory type');continue
   require(m.isfile(),'only indexed regular archived contents supported')
   with tar.extractfile(m)as f:n,h=digest_stream(f)
   require(n==r['bytes']and h==r['sha256'],'archived member data mismatch '+m.name)
   if 'mode'in r:require(m.mode==r['mode'],'archive mode differs')
   add(index,r,dict(container=record,member=m.name));guard()
 require(seen==set(expected),'incomplete archive EOF/member set');verify(record)
def gzip_read(record,original,index):
 safe_archive(record)
 with gzip.open(record['path'],'rb')as f:n,h=digest_stream(f)
 require((n,h)==(original['bytes'],original['sha256']),'single raw model/FST/program mismatch')
 add(index,original,dict(container=record,raw_single=True));verify(record)
def durable():
 cat=read(A['catalog']);require(cat['schema']=='obsolete-native-durable-catalog-v1','catalog schema');verify(cat['scanner_origin']);index={};verified=[]
 for record in cat['base']:
  q=read(record);require(q['state'].startswith('PASS')and all(a['roundtrip']is True for a in q['archives']),'closed base readback declarations')
  for archive in q['archives']:
   if 'members'in archive:tar_read(archive['archive'],archive['members'],index)
   else:gzip_read(archive['archive'],archive['original'],index)
  verified.append(record)
 record=cat['cohort'];q=read(record);require(q['state']=='PASS OLD256 complete lossless closure; prior operational failures preserved','closed complete RO04')
 tar_read(q['archive'],q['inventory'],index);verified.append(record)
 q=read(cat['scope']);review=read(cat['scope_review']);require(review['state']=='PASS independent hash/lossless-model/five-literal-domain review'and review['scoped_model_sha256']==q['model']['sha256'],'actual qualified historical clone')
 gzip_read(q['gzip'],q['model'],index);verify(q['qualified_rawFST']);add(index,q['qualified_rawFST'],dict(raw_durable=q['qualified_rawFST']));safe_archive(q['copied_source_archive']);verified.extend([cat['scope'],cat['scope_review']])
 retired=read(cat['retirement_prepared']);require(retired['no_future_release']is True and retired['rebuild_recipe'],'old cache origin, never a future release')
 containers={q['copied_source_archive']['path']:q['copied_source_archive']}
 for hits in index.values():
  for hit in hits:
   origin=hit['origin'];row=origin.get('container',origin.get('raw_durable'))
   if row:containers[row['path']]=row
 return index,dict(manifests=verified,containers=list(containers.values()),verified_content_count=sum(map(len,index.values())),rebuild_recipe=retired['rebuild_recipe'],cache_origin=cat['retirement_prepared'])
def classify(rows,index):
 result=[]
 for r in rows:
  v=dict(path=r['path'],kind=r['kind'])
  if r['kind']=='directory':v['class']='directory-metadata-retained'
  elif r['kind']=='symlink':v.update(classification='uncovered-symlink',target=r['target']);v['class']='uncovered'
  else:
   hits=index.get((r['bytes'],r['sha256']),[]);exact=[x for x in hits if x['path']==r['path']]
   if hits:v.update(**{'class':'durable-exact-path'if exact else'durable-identical-content'},durable=(exact or hits)[0])
   elif Path(r['path']).suffix in ('.o','.a','.gch','.d')and any(t in r['path']for t in ['/verilator/obj_dir/','/scoped01/build/obj/']):v.update(**{'class':'derived-candidate-ROOT-review-required'},bytes=r['bytes'],sha256=r['sha256'])
   else:v.update(**{'class':'uncovered'},bytes=r['bytes'],sha256=r['sha256'])
  result.append(v)
 return result
class LimitWriter:
 def __init__(self,f):self.f=f
 def write(self,b):
  require(self.f.tell()+len(b)<=DELTA,'64MiB compressed delta cap');n=self.f.write(b);guard();return n
 def flush(self):return self.f.flush()
 def tell(self):return self.f.tell()
class CheckedReader:
 def __init__(self,f):self.f=f;self.h=hashlib.sha256();self.n=0
 def read(self,n):
  b=self.f.read(n);self.h.update(b);self.n+=len(b);guard();return b
def capture(rows):
 path=OUT/'uncovered.tar.gz';members=[]
 with path.open('xb')as raw,gzip.GzipFile(filename='',mode='wb',fileobj=LimitWriter(raw),mtime=0,compresslevel=1)as gz,tarfile.open(fileobj=gz,mode='w|')as tar:
  for r in rows:
   name='pool/'+r['path'][len('/run/user/1001/'):] ;h=tarfile.TarInfo(name);h.mode=stat.S_IMODE(r['mode']);h.uid=r['uid'];h.gid=r['gid'];h.mtime=r['mtime_ns']//10**9
   if r['kind']=='symlink':h.type=tarfile.SYMTYPE;h.linkname=r['target'];tar.addfile(h)
   else:
    h.size=r['bytes']
    with Path(r['path']).open('rb')as f:
     reader=CheckedReader(f);tar.addfile(h,reader);require(reader.n==r['bytes']and reader.h.hexdigest()==r['sha256'],'changed uncovered data')
   members.append(dict(member=name,original=r));guard()
 # Verify every captured member including link definitions without extraction.
 byname={v['member']:v['original']for v in members};seen=set()
 with tarfile.open(path,'r|gz')as tar:
  for m in tar:
   require(m.name in byname and m.name not in seen,'delta unknown/duplicate member');seen.add(m.name);r=byname[m.name];require(m.mode==stat.S_IMODE(r['mode']),'delta mode')
   if r['kind']=='symlink':require(m.issym()and m.linkname==r['target'],'delta link')
   else:
    require(m.isfile(),'delta file type')
    with tar.extractfile(m)as f:n,h=digest_stream(f)
    require((n,h)==(r['bytes'],r['sha256']),'delta readback bytes')
 require(seen==set(byname),'complete delta readback EOF');return dict(archive=bind(path),members=members,roundtrip=True)
def main():
 global A,START
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--admission',type=Path,required=True);ap.add_argument('--admission-sha256',required=True);ap.add_argument('--prepare',action='store_true');ap.add_argument('--execute',action='store_true');ap.add_argument('--review-sha256');ap.add_argument('--approval',type=Path);ap.add_argument('--approval-sha256');x=ap.parse_args();require(x.prepare!=x.execute,'one explicit ROOT phase');START=time.monotonic();raw=x.admission.read_bytes();require(hashlib.sha256(raw).hexdigest()==x.admission_sha256,'external ROOT authority SHA');A=json.loads(raw)
 require(A['schema']=='obsolete-native-RUN-freeze-authority-v3'and A['ROOT_approved']is True and A['ROOT_old_pools_obsolete_no_new_producers']is True,'DRAFT cannot run')
 require(os.geteuid()==1001 and A['ROOT_no_other_UID_old_producers']is True and A['ROOT_inaccessible_nonproducer_allowlist']==ALLOW,'same qualified UID/exact service exceptions')
 require(A['roots']==list(map(str,ROOTS))and A['caps']==dict(source=SOURCE,metadata=META,proof_delta=DELTA,seconds=DEADLINE),'exact seven-root/fixed cap scope')
 require(A['old_BASE_RUN_bytes']==1156926898 and A['pending_Iarea_bytes_still_charged']==33554432 and A['current_canonical_component_unchanged']is True,'no pending reservation transfer')
 q=A['resources'];require(q['ROOT_approved']is True and q['all_OTHER_and_current_reservations_included']is True and q['old_BASE_RUN_still_charged_bytes']==1156926898,'fresh global budget, old charge stays until acceptance')
 require(q['required_HOME_free_without_SELF']>=1792*1024**2 and q['required_RUN_free_bytes']>=1024**3 and q['required_SHM_free_bytes']>=512*1024**2 and q['required_MemAvailable_bytes']>=512*1024**2,'floors and explicit host memory')
 require(A['forbidden_current_roots']and '/run/user/1001/zp-csr-unmasked768-fullcore-20261123-01'in A['forbidden_current_roots'],'current768 excluded')
 require(A['current_canonical_component_roots']and all(p in A['forbidden_current_roots']for p in A['current_canonical_component_roots']),'explicit current canonical component exclusion')
 require(q['basis_records']and Path(owner_scan.__file__).resolve()==HERE/'owner_scan.py'and Path(transport_role.__file__).resolve()==HERE/'transport_role.py','actual basis and qualified local scanner')
 for new in A['forbidden_current_roots']:
  n=Path(new);require(n.is_absolute()and all(n!=r and n not in r.parents and r not in n.parents for r in ROOTS),'current/old root overlap')
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
 def interrupted(sig,frame):raise RuntimeError('caught termination '+str(sig))
 for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP,signal.SIGALRM):signal.signal(sig,interrupted)
 signal.setitimer(signal.ITIMER_REAL,DEADLINE)
 guard(True)
 expected={str(HERE/n)for n in ['freeze_run.py','owner_scan.py','catalog.json','transport_role.py']};require(expected<=set(r['path']for r in A['source_inputs']),'all executable/catalog sources bound')
 require(A['prior_failed_prepare']==PRIOR_FAILURE,'exact failed02 provenance')
 for r in A['source_inputs']+A['resources']['basis_records']+[A['ROOT_transport_role_proof'],PRIOR_FAILURE]:verify(r)
 require(A['catalog']==next(r for r in A['source_inputs']if r['path']==str(HERE/'catalog.json')),'fixed source catalog, no arbitrary redirect')
 if x.prepare:require(not OUT.exists()and not OUT.is_symlink(),'fresh review prefix');OUT.mkdir()
 else:require(OUT.is_dir()and not OUT.is_symlink()and not(OUT/'completion.json').exists(),'fresh explicit continuation only')
 state=dict(schema='obsolete-native-RUN-freeze-completion-v3',state='RUNNING coverage/stop review',admission=dict(path=str(x.admission),bytes=len(raw),sha256=x.admission_sha256),no_pool_deletion_or_mode_change=True,no_cleanup=True)
 try:
  presence=root_presence();state.update(root_presence=presence,prior_failed_prepare=PRIOR_FAILURE);before=scan();index,proof=durable();rows=inventory();require(inventory()==rows,'full double SHA/mode/link/membership inventory mismatch');after=scan();classification=classify(rows,index)
  for r in proof['manifests']+proof['containers']+[proof['cache_origin']]:verify(r)
  if x.prepare:
   write(OUT/'inventory-before.json',rows);write(OUT/'inventory-after.json',rows)
   review=dict(schema='obsolete-native-RUN-freeze-review-v3',root_presence=presence,state='PREPARED ROOT coverage/classification review required; no RUN future withdrawn',output_identity=dict(device=OUT.stat().st_dev,inode=OUT.stat().st_ino),admission=state['admission'],inventory=bind(OUT/'inventory-before.json'),second_inventory=bind(OUT/'inventory-after.json'),classifications=classification,derived_candidates=[v for v in classification if v['class']=='derived-candidate-ROOT-review-required'],uncovered=[v for v in classification if v['class']=='uncovered'],durable=proof,owner_before=before,owner_after=after,no_future_release=True)
   require(root_presence()==presence,'preparation phase-end root presence changed');write(OUT/'review.json',review);state.update(state='PASS preparation only; ROOT classification review pending, no future withdrawal',review=bind(OUT/'review.json'));print(json.dumps(state['review']));return
  review_record=bind(OUT/'review.json');require(review_record['sha256']==x.review_sha256,'external reviewed preparation SHA');review=json.loads((OUT/'review.json').read_text());require(review['root_presence']==presence and review['admission']==state['admission']and read(review['inventory'])==rows and read(review['second_inventory'])==rows and review['classifications']==classification,'reviewed exact current oldpool state')
  require(review['output_identity']==dict(device=OUT.stat().st_dev,inode=OUT.stat().st_ino),'same prepared output directory identity')
  approval_record=bind(x.approval);require(approval_record['sha256']==x.approval_sha256,'external ROOT approval SHA');approval=json.loads(x.approval.read_text());require(approval['ROOT_verified']is True and approval['review']==review_record and approval['authorize_stop_only_after_all_checks']is True,'actual ROOT classification/stop decision')
  require(approval['prepare_session']['path']==str(OUT/'prepare-session.json'),'fixed prepared lifecycle receipt')
  prepared=read(approval['prepare_session']);require(prepared['state']=='PASS preparation only; ROOT classification review pending, no future withdrawal'and prepared['review']==review_record and prepared['admission']==state['admission'],'prepare actual complete source/coverage lifecycle')
  approved=approval['derived_candidates'];require(type(approved)is list and all(v in review['derived_candidates']for v in approved)and len({v['path']for v in approved})==len(approved),'only exact reviewed derivable candidates')
  required=review['uncovered']+[v for v in review['derived_candidates']if v not in approved]
  require(approval['uncovered_capture']==required and approval['ROOT_rebuild_origins_reviewed']is True and approval['cache_origin']==proof['cache_origin'],'all nonapproved data captured, explicit rebuild origins')
  wanted={v['path']for v in required};delta=capture([r for r in rows if r['path']in wanted]);write(OUT/'proof-delta.json',delta)
  require(inventory()==rows,'all pool files/dirs unchanged after capture');last=scan()
  for r in A['source_inputs']+A['resources']['basis_records']+[A['ROOT_transport_role_proof'],PRIOR_FAILURE]+proof['manifests']+proof['containers']+[proof['cache_origin']]:verify(r)
  require(root_presence()==presence,'phase-end root presence changed');require(x.admission.read_bytes()==raw,'authority unchanged');verify(approval_record);verify(approval['prepare_session']);guard(True)
  state.update(state='PASS ROOT-approved unused RUN writes stopped; all actual files kept and coverage classified',ROOT_verified=True,review=review_record,approval=approval_record,durable=proof,proof_delta=bind(OUT/'proof-delta.json'),owner_before=before,owner_after=last,protected_members=len(rows),families={k:dict(roots=v['roots'],original_cap_bytes=768*1024**2,closed_fixed_future_charge_bytes=v['charge'],new_future_RUN_bytes=0)for k,v in GROUPS.items()},unused_fixed_RUN_future_withdrawn_bytes=1123372466,old_BASE_RUN_bytes=1156926898,new_BASE_RUN_bytes=33554432,pending_Iarea_bytes_still_charged=33554432,current768_and_canonical_unchanged=True,all_current_actual_bytes_still_charged=True,physical_bytes_reclaimed=0,original_caps_unchanged=True,new_writes_need_fresh_admission=True,scope='Operational future-write stop only; no new functional/fit/performance or full allmember archival claim; derived objects stay RAM with ROOT-reviewed rebuild origin',seconds=time.monotonic()-START)
 except BaseException as e:state.update(state='FAIL preserved; no RUN withdrawal accepted',error=repr(e));raise
 finally:
  target=OUT/('prepare-session.json'if x.prepare else'completion.json')
  try:write(target,state)
  except BaseException as final_error:
   # A failed final publication/resource check cannot leave an accepted PASS.
   state.update(state='FAIL final publication/resource check; no RUN withdrawal accepted',final_error=repr(final_error))
   try:
    payload=(json.dumps(state,separators=(',',':'))+'\n').encode()
    meta=used(OUT)-((OUT/'uncovered.tar.gz').stat().st_size if (OUT/'uncovered.tar.gz').exists()else 0)
    old=target.stat().st_size if target.exists()else 0
    if len(payload)<1024**2 and meta-old+len(payload)<=META:
     with target.open('wb')as f:f.write(payload);f.flush();os.fsync(f.fileno())
   except OSError:pass
   raise
if __name__=='__main__':main()
