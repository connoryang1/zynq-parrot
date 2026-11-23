#!/usr/bin/env python3
"""ROOT-only review then selected archived old02 RTD retirement; no global busy test."""
import argparse,hashlib,json,lzma,os,stat,sys,tarfile,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=Path('/run/user/1001/zp-linux-csr-opt1536-trace0-cad-20261122-02')
CLOSED=Path('/home/coyang/fpga-artifacts/context-resume/csr-opt1536-fpga-preparation-20261122/closed-cancel02')
OUT=Path('/home/coyang/fpga-artifacts/context-resume/csr1536-old02-rtd-retirement-20261123/review01')
PINS={'inventory.json':'e7db04d8691ce053cb47ea53b041f6cb1c3500159bd35f4d6c85cc5a57ac1067','full-cancelled-work-source.tar.xz':'0c06c3e50a6bb5c9b69a966840dea372328498f6d92e697c2d2395f4f8a9b6e8','ROOT-cancelled-closure.json':'cd1377a808b9699b35724f020336414df70c6b8037f6fbedfbae87824a2b871b'}
START=0;CAP=2*1024**2
def need(v,m):
 if not v:raise ValueError(m)
def tick():need(time.monotonic()-START<180,'fixed180s worker deadline; preserve partial receipt')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b);tick()
 return h.hexdigest()
def bind(p):p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def write(p,q):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(q,indent=2)+'\n');t.replace(p)
def metadata(p):
 s=p.lstat();return dict(bytes=s.st_size,mode=stat.S_IMODE(s.st_mode),inode=s.st_ino,device=s.st_dev,nlink=s.st_nlink,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,uid=s.st_uid,gid=s.st_gid)
def source_bindings(a):
 for r in a['inputs']:need(bind(r['path'])==r,'helper/authority input drift')
 for name,wanted in PINS.items():need(sha(CLOSED/name)==wanted,'exact old archive/inventory/ROOT closure '+name)
 c=json.loads((CLOSED/'ROOT-cancelled-closure.json').read_text());need(c['ROOT_verified'] is True and c['all_originals_preserved'] is True,'historical complete ROOT recovery proof')
def select():
 raw=(CLOSED/'inventory.json').read_bytes();c=json.loads(raw)
 need(c['schema']=='csr1536-cancelled-cad-lossless-inventory-v1' and c['roots']['WORK']==str(ROOT),'literal archived inventory schema/root')
 rows=[]
 for r in c['members']:
  if not r['member'].startswith('WORK/') or not r['path'].endswith('.rtd'):continue
  p=Path(r['path']);need(r['kind']=='file' and r['nlink']==1 and not(r['mode']&0o111),'only regular nonexec nlink1 archived RTD')
  need(p.is_absolute() and ROOT in p.parents and r['member']=='WORK/'+p.relative_to(ROOT).as_posix(),'exact old root/member mapping')
  need(p.resolve()==p,'no symlink in selected old path')
  rows.append(r)
 need(len(rows)==172 and sum(r['bytes'] for r in rows)==398135690,'exact fixed172 RTDs/398135690 raw bytes, not a new census')
 need(len({r['path'] for r in rows})==172,'unique originals')
 return raw,c,rows
def check_one(r):
 p=Path(r['path']);before=metadata(p);need(stat.S_ISREG(p.lstat().st_mode),'regular original')
 need(before=={k:r[k] for k in before},'selected original archived identity/stat changed '+str(p))
 need(sha(p)==r['sha256'] and metadata(p)==before,'selected original SHA/stat changed during read '+str(p));return before
def check_all(rows):
 for r in rows:check_one(r)

# Exact identity-bound exceptions copied from the reviewed pack03 protocol.
# No other metadata/FD permission denial is accepted or called inspected.
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
def owner_scan(rows):
 targets={r['path'] for r in rows};inodes={(r['device'],r['inode']) for r in rows};exceptions=[];scanned=0;other_uid=0
 for proc in Path('/proc').glob('[0-9]*'):
  tick()
  try:
   if proc.stat().st_uid!=os.getuid():other_uid+=1;continue
   scanned+=1
   if int(proc.name)==1553164:
    s=(proc/'stat').read_text();need(int(s[s.rfind(')')+2:].split()[19])!=100315010,'old worker identity still exists')
   argv=[x.decode(errors='replace') for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
   for token in argv:
    value=token.split('=',1)[-1];need(not(value==str(ROOT) or value.startswith(str(ROOT)+'/')),'process explicitly uses frozen old WORK '+proc.name)
   for fd in (proc/'fd').iterdir():
    try:
     target=os.readlink(fd);s=fd.stat();need(target not in targets and (s.st_dev,s.st_ino) not in inodes,'open selected RTD descriptor '+str(fd))
    except (FileNotFoundError,ProcessLookupError):pass
  except (FileNotFoundError,ProcessLookupError):pass
  except PermissionError as error:
   exception=known_desktop_fd_denial(proc,error);need(exception is not None,'unqualified process/FD permission denial '+str(proc));exceptions.append(exception)
 return dict(uid=os.getuid(),same_uid_processes_scanned=scanned,other_uid_processes_not_inspected=other_uid,selected_FDs_absent=True,old_WORK_process_references_absent=True,desktop_FD_exceptions=exceptions,no_global_compiler_or_vendor_busy_filter=True)
def full_readback(raw,c):
 expected={r['member']:r for r in c['members']};need(len(expected)==len(c['members']),'unique complete archived members');seen=set();n=0
 with lzma.open(CLOSED/'full-cancelled-work-source.tar.xz','rb') as stream:
  with tarfile.open(fileobj=stream,mode='r|') as tar:
   for t in tar:
    tick();need(t.name not in seen,'duplicate tar member');seen.add(t.name)
    if t.name=='__inventory__.json':need(tar.extractfile(t).read()==raw,'literal full embedded inventory');continue
    need(t.name in expected,'unexpected tar member');r=expected[t.name];need(t.mode==r['mode'],'tar mode')
    if r['kind']=='directory':need(t.isdir(),'tar directory')
    elif r['kind']=='symlink':need(t.issym() and t.linkname==r['target'],'tar link')
    else:
     need(t.isfile() and t.size==r['bytes'],'tar regular size');h=hashlib.sha256();size=0;f=tar.extractfile(t)
     for b in iter(lambda:f.read(1024*1024),b''):h.update(b);size+=len(b);tick()
     need(size==r['bytes'] and h.hexdigest()==r['sha256'],'full member SHA '+t.name);n+=size
  for b in iter(lambda:stream.read(1024*1024),b''):need(not any(b),'nonzero trailing tar data');tick()
 need(seen==set(expected)|{'__inventory__.json'},'complete archive member seen set')
 return dict(all_members=len(expected),raw_file_bytes=n,mode_link_type_and_SHA_PASS=True,no_extraction=True)
def guard(a):
 q=json.loads(Path(a['ROOT_resource_profile']['path']).read_text());need(q['ROOT_approved'] is True and q['all_other_charged_reserves_included'] is True,'ROOT funded phase profile required')
 need(bind(a['ROOT_resource_profile']['path'])==a['ROOT_resource_profile'],'fixed ROOT profile')
 need(q['HOME_floor_bytes']==1879048192 and q['output_cap_bytes']==CAP,'same1.75GiB floor/small2MiB proof cap')
 used=sum(max(p.lstat().st_size,p.lstat().st_blocks*512) for p in OUT.rglob('*') if p.is_file()) if OUT.exists() else 0
 need(used<=CAP,'fixed2MiB retirement proof family');free=os.statvfs('/home/coyang');need(free.f_bavail*free.f_frsize>=q['required_HOME_free_excluding_own_remaining']+max(0,CAP-used),'all HOME reserves')
 for root,key in [('/run/user/1001','required_RUN_free_bytes'),('/dev/shm','required_SHM_free_bytes')]:s=os.statvfs(root);need(s.f_bavail*s.f_frsize>=q[key],'all other RAM reserves')
 need(time.monotonic()-START<180,'phase deadline');return q
def main():
 global START
 START=time.monotonic();p=argparse.ArgumentParser(description=__doc__);p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);p.add_argument('--phase',choices=['review','retire'],required=True);p.add_argument('--review-sha256');p.add_argument('--ROOT-review-approval',type=Path);p.add_argument('--ROOT-review-approval-sha256');x=p.parse_args()
 a=json.loads(x.admission.read_text());need(sha(x.admission)==x.admission_sha256 and a['ROOT_approved'] is True and x.phase in a['actions'],'exact ROOT phase authority');need(a['old_WORK']==str(ROOT) and a['selected_files']==172 and a['selected_raw_bytes']==398135690 and a['ROOT_old_WORK_permanently_no_writers'] is True,'fixed target scope/ROOT permanent no-writer boundary')
 source_bindings(a);guard(a);raw,c,rows=select();selection_sha=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest();review=OUT/'review.json'
 if x.phase=='review':
  need(not OUT.exists(),'fresh review output');before=owner_scan(rows);check_all(rows);decoded=full_readback(raw,c);check_all(rows);after=owner_scan(rows);source_bindings(a);guard(a);OUT.mkdir(parents=True)
  write(review,dict(state='PASS complete old archive readback and exact selected original/owner pre-post; ROOT REVIEW REQUIRED BEFORE UNLINK',admission=bind(x.admission),selection_sha256=selection_sha,selected=rows,selected_files=172,selected_raw_bytes=398135690,archive=dict(path=str(CLOSED/'full-cancelled-work-source.tar.xz'),sha256=PINS['full-cancelled-work-source.tar.xz']),old_ROOT_closure_sha256=PINS['ROOT-cancelled-closure.json'],readback=decoded,owner_before=before,owner_after=after,elapsed_seconds=time.monotonic()-START,no_unlink=True));guard(a);print('PASS REVIEW ONLY; no file removed');return
 need(review.exists() and sha(review)==x.review_sha256,'exact complete review receipt');r=json.loads(review.read_text());need(r['selection_sha256']==selection_sha and r['selected']==rows and r['admission']==bind(x.admission),'same full selected scope/admission')
 need(x.ROOT_review_approval is not None and sha(x.ROOT_review_approval)==x.ROOT_review_approval_sha256,'separate exact ROOT review-before-unlink approval')
 approval=json.loads(x.ROOT_review_approval.read_text());need(approval['ROOT_verified'] is True and approval['review']==bind(review) and approval['selection_sha256']==selection_sha and approval['authorized_action']=='unlink-only-these-172-archived-old02-RTDs' and approval['old_WORK_permanently_no_writers'] is True,'ROOT approved immutable recovery and no-writer boundary')
 need(not(OUT/'retirement.json').exists(),'one retirement attempt only');check_all(rows);before=owner_scan(rows);rec=dict(state='RUNNING narrow RTD retirement',review=bind(review),ROOT_approval=bind(x.ROOT_review_approval),selection_sha256=selection_sha,archive=r['archive'],old_ROOT_closure_sha256=PINS['ROOT-cancelled-closure.json'],owner_before=before,removed=[],intent=None)
 try:
  for row in rows:
   guard(a);check_one(row);owner_scan([row]);rec['intent']=dict(path=row['path'],member=row['member'],sha256=row['sha256']);write(OUT/'retirement.json',rec)
   Path(row['path']).unlink();need(not Path(row['path']).exists(),'unlink absent');rec['removed'].append(rec['intent']);rec['intent']=None;write(OUT/'retirement.json',rec)
  after=owner_scan(rows);source_bindings(a);need(all(not Path(v['path']).exists() for v in rows),'all172 absent after retirement');rec.update(state='PASS only172 fully recoverable old02 RTDs removed; historical closure unchanged',owner_after=after,removed_raw_bytes=398135690,all_nonselected_untouched_by_operation=True,old_closure_is_historical_not_rewritten=True,requires_layered_disposition=True,elapsed_seconds=time.monotonic()-START)
 except BaseException as e:rec.update(state='FAIL partial retirement preserved; recover from original complete archive',error=repr(e));raise
 finally:write(OUT/'retirement.json',rec)
 guard(a);print(rec['state'])
if __name__=='__main__':main()
