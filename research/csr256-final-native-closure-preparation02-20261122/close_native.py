#!/usr/bin/env python3
"""ROOT-only final oldCSR256 reservation closure; no producers, cleanup or codec."""
import argparse,gzip,hashlib,importlib.util,json,os,shutil,stat,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
LITERAL=Path('/home/coyang/fpga-artifacts/context-resume/csr256-final-native-closure-preparation-20261122/literal_receipts.py')
if hashlib.sha256(LITERAL.read_bytes()).hexdigest()!='f84bae297b2eab93b7f3535539fcfc2b23d1d8bbdc67b1333a16e9e204987357':raise ValueError('pinned pure literal verifier changed')
sys.path.insert(0,str(LITERAL.parent))
import literal_receipts as literal
HERE=Path(__file__).resolve().parent
OUT=Path('/home/coyang/fpga-artifacts/context-resume/reservation-closures-20261122/csr256-final01')
POOL=Path('/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01');COHORT=POOL/'all256-csr01'
PREP=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fullcore-preparation-20261122')
HELPERS=[PREP,Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-allslots-preparation-20261122'),Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-allslots-preparation02-20261122'),Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-observation-preparation-20261122'),Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-regression-preparation-20261122'),Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-allslots-delta-preparation-20261122'),Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-allslots-delta-preparation02-20261122')]
BASE_HOME=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fullcore-20261122');DELTA_HOME=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-allslots-delta-20261122')
FAMILIES={'POOL':([POOL],1024**3),'HELPERS':(HELPERS,1024**2),'BASE_HOME':([BASE_HOME],32*1024**2),'DELTA_HOME':([DELTA_HOME],16*1024**2)}
ROLES=['d-enabled','d-off','i-enabled'];META_CAP=2*1024**2
need=literal.require;bind=literal.bind
def read(p):return json.loads(Path(p).read_text())
def verify(r):need(bind(r['path'])==r,'exact prerequisite/source drift '+r['path'])
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def size(root):return sum(p.lstat().st_size for p in root.rglob('*') if p.is_file() or p.is_symlink()) if root.exists() else 0
def terminal(a):
 verify(a['ROOT_actual_terminal_nochildren']);q=read(a['ROOT_actual_terminal_nochildren']['path']);need(q['ROOT_verified'] is True and q['all_owned_children_absent'] is True and q['global_vendor_absent'] is True,'actual final terminal/no-orphan prerequisite')
 names={'vivado','vivado_lab','xelab','xsim','xsimk','xvlog','xsc','planahead','launch_synthesis.sh','run_vivado_2024_2.sh'};found=[]
 for p in Path('/proc').glob('[0-9]*'):
  try:
   comm=(p/'comm').read_text().strip();argv=(p/'cmdline').read_bytes().split(b'\0')
   if comm in names or any(s.decode(errors='replace').rsplit('/',1)[-1] in names for s in argv):found.append(int(p.name))
  except (FileNotFoundError,ProcessLookupError):pass
 need(not found,'vendor/launcher is active: '+str(found))
def guard(a,started):
 need(time.monotonic()-started<=600,'fixed600s final closure bound')
 verify(a['_authority'])
 need(size(HERE)<=32768 and size(OUT)<=META_CAP,'new32KiB source/2MiB metadata only caps')
 verify(a['ROOT_resource_preflight']);p=read(a['ROOT_resource_preflight']['path']);need(p['all_other_charged_reserves_included'] is True,'same current OTHER/native/CAD reservations priced until closure')
 need(shutil.disk_usage(HERE).free>=p['required_HOME_free_without_final_remaining']+max(0,META_CAP-size(OUT)),'all current reserves plus prospective final metadata remaining')
 need(shutil.disk_usage('/run/user/1001').free>=p['required_RUN_free_bytes'] and shutil.disk_usage('/dev/shm').free>=p['required_SHM_free_bytes'],'all current RAM reservations still charged')
 for r in a['inputs']:verify(r)

def verify_completed(a):
 # This owns only literal validation; it never imports a frozen producer.
 verify(a['base_closure']);verify(a['delta_closure']);base=read(a['base_closure']['path']);delta=read(a['delta_closure']['path'])
 need(base['state']=='PASS lossless base full+clone+STD archival; all256 delta pending','actual accepted base closure')
 need(delta['state']=='PASS complete lossless new CSR256 three-role delta; final double-pool freeze still required','actual accepted16MiB delta closure')
 for m in [base,delta]:
  verify(m['archive']);need([r.get('action',r.get('phase')) for r in m['commands']]==['compress','roundtrip'],'complete exact encode+roundtrip phases')
  for c in m['commands']:
   life=c.get('owned',c.get('ownership'));need(life['returncode']==0 and life['failure'] is None and life['owned_group_remaining'] is False,'all archival phase groups closed')
 # Independent complete byte/mode/link readback anchors must predate finalizer.
 need(len(a['ROOT_independent_readbacks'])==2,'two independent complete payload readback anchors required')
 for r,m in zip(a['ROOT_independent_readbacks'],[base,delta]):
  verify(r);proof=read(r['path']);need(proof['ROOT_verified'] is True and proof['state'].startswith('PASS') and proof['archive']==m['archive'],'independent exact archive verification')
  need(proof['all_payload_members_verified'] is True and proof['all_modes_and_links_verified'] is True and proof['payload_members_verified']==m['members'],'hash-only container check is insufficient')
 done=read(COHORT/'ROOT-cohort-complete.json');need(bind(COHORT/'ROOT-cohort-complete.json')['sha256']=='a5ab8e3636a9ac890effac410823af5059c2900dd493004f23b1035e7bc5ca01','literal closed six anchors')
 verify(done['preparation']);p=read(done['preparation']['path']);need(p['schedule']==ROLES and p['model']['sha256']==done['model_sha256']=='9473086b6efb79a562c9f27882f435a6eaa558b0d363b1ce8184f19d02124a71','exact completed new model/order')
 need(len(p['runtime_sources'])==43 and read(COHORT/'runtime-sources.json')==p['runtime_sources'],'original literal43set; no sys.modules expansion')
 for r in p['runtime_sources']:verify(r)
 literal.FOUNDATION=p['runtime_sources']+[read(COHORT/(role+'-audit/counter-words.json'))['auditor'] for role in ROLES]
 for r in literal.FOUNDATION:verify(r)
 for role in ROLES:
  r=done['roles'][role];verify(r['native']);verify(r['audit'])
  literal.check_native(COHORT,role,p,done['preparation']['path'],r['native']['sha256']);literal.verify_audit(COHORT,role,p,done['preparation']['path'],r['audit']['sha256'])
  full=read(COHORT/(role+'-audit/verification.json'));need(full['archive']['full_stream']==r['stream'],'all complete167digest/EOF/projection gates unchanged')
 return dict(base=a['base_closure'],delta=a['delta_closure'],independent_readbacks=a['ROOT_independent_readbacks'],cohort=bind(COHORT/'ROOT-cohort-complete.json'),literal43=p['runtime_sources'],six_phase_anchors={role:{k:v for k,v in done['roles'][role].items() if k in ['native','audit']} for role in ROLES})
def owners(a):
 verify(a['qualified_owner_guard']);spec=importlib.util.spec_from_file_location('final_UID_owner',a['qualified_owner_guard']['path']);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 roots=[root for family in FAMILIES.values() for root in family[0]]
 return m.owner_scan(roots,[dict(pid=12456,startticks=67838353,ppid=12455,comm='(sd-pam)',euid=1001),dict(pid=164612,startticks=78172576,ppid=12455,comm='gnome-keyring-d',euid=1001)])
def inventory(a,started):
 result={};last=time.monotonic()
 for label,(roots,cap) in FAMILIES.items():
  rows=[];logical=allocated=0
  for root in roots:
   need(root.is_dir() and not root.is_symlink(),'exact retained root '+str(root))
   for p in sorted([root]+list(root.rglob('*'))):
    if time.monotonic()-last>.5:guard(a,started);last=time.monotonic()
    s=p.lstat();r=dict(path=str(p),bytes=s.st_size,mode=stat.S_IMODE(s.st_mode),inode=s.st_ino,device=s.st_dev,nlink=s.st_nlink,uid=s.st_uid,gid=s.st_gid,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,allocated_bytes=s.st_blocks*512)
    if p.is_symlink():
     b=os.fsencode(os.readlink(p));r.update(kind='symlink',target=os.readlink(p),sha256=hashlib.sha256(b).hexdigest());logical+=len(b)
    elif p.is_dir():r['kind']='directory'
    else:
     need(p.is_file(),'special input cannot be omitted '+str(p));r.update(kind='file',sha256=bind(p)['sha256']);logical+=s.st_size
    allocated+=s.st_blocks*512;rows.append(r)
  charged=max(logical,allocated);cap_used=logical if label=='HELPERS' else charged
  need(cap_used<=cap,'original cap metric unchanged '+label)
  result[label]=dict(roots=list(map(str,roots)),files=rows,logical_bytes=logical,allocated_bytes=allocated,actual_closed_charged_bytes=charged,cap_metric='logical' if label=='HELPERS' else 'max(logical,allocated)',cap_used_bytes=cap_used,original_allocation_bytes=cap,unused_allocation_bytes=cap-cap_used,unused_logical_bytes=cap-logical,future_growth_reserved_bytes=0)
 return result
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);p.add_argument('--execute',action='store_true',required=True);x=p.parse_args();started=time.monotonic();a=read(x.admission);ab=bind(x.admission);need(ab['sha256']==x.admission_sha256 and a['ROOT_approved'] is True,'DRAFT cannot execute')
 need(a['ROOT_no_privileged_or_other_UID_old_producers'] is True,'qualified UID1001 producer ownership scope required; not all-UID absence')
 a['_authority']=ab;guard(a,started);terminal(a);need(not OUT.exists(),'fresh final closure, preserve any failed attempt')
 anchors=verify_completed(a);before_owner=owners(a);first=inventory(a,started);need(verify_completed(a)==anchors,'literal source/phase anchors changed before second inventory');second=inventory(a,started);need(first==second,'whole byte/mode/link/mtime/ctime/inode double inventory mismatch');after_owner=owners(a);terminal(a)
 OUT.mkdir(parents=True);record=dict(state='RUNNING final metadata publication only',admission=ab);write(OUT/'attempt.json',record)
 try:
  raw=json.dumps(first,sort_keys=True,separators=(',',':')).encode();one=gzip.compress(raw,compresslevel=1,mtime=0);two=gzip.compress(json.dumps(second,sort_keys=True,separators=(',',':')).encode(),compresslevel=1,mtime=0)
  need(gzip.decompress(one)==raw==gzip.decompress(two),'both complete metadata snapshots roundtrip')
  (OUT/'inventory-before.json.gz').write_bytes(one);(OUT/'inventory-after.json.gz').write_bytes(two);guard(a,started);need(verify_completed(a)==anchors,'final literal six anchors/source43 unchanged');terminal(a)
  complete=dict(schema='csr256-final-native-reservation-closure-v1',state='PASS exact base+delta/readback and complete double pool/helper/durable inventories; unused future0 only',ROOT_verified=True,TOP='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd',BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa',model_sha256='9473086b6efb79a562c9f27882f435a6eaa558b0d363b1ce8184f19d02124a71',anchors=anchors,inventory_before=bind(OUT/'inventory-before.json.gz'),inventory_after=bind(OUT/'inventory-after.json.gz'),inventory_uncompressed_sha256=hashlib.sha256(raw).hexdigest(),pool_double_inventory_equal=True,delta_verified=True,no_cleanup=True,all_current_bytes_still_charged=True,original_caps_unchanged=True,new_writes_to_frozen_families_require_new_admission=True,unused_future_only=True,metadata_family_original_allocation_bytes=META_CAP,old_families={label:{k:v for k,v in row.items() if k!='files'} for label,row in first.items()},future_native_POOL_bytes=0,future_native_HELPER_bytes=0,future_native_BASE_HOME_bytes=0,future_native_DELTA_HOME_bytes=0,previous_CAD_conservative_native_charge_bytes=1024**3,new_native_future_charge_bytes=0,physical_free_bytes_reclaimed=0,owner_before=before_owner,owner_after=after_owner,owner_scope='EUID1001 recorded producers, exact two ROOT-proved system-service exemptions, no global allUID absence claim',elapsed_seconds=time.monotonic()-started)
  for r in a['inputs']:verify(r)
  pending=OUT/'complete.pending.json';write(pending,complete);guard(a,started);need(verify_completed(a)==anchors,'last exact sources/phase/readback endcheck');terminal(a);pending.replace(OUT/'complete.json');print(json.dumps(bind(OUT/'complete.json'),indent=2))
 except BaseException as e:
  record.update(state='FAIL no release authority; preserve final metadata attempt',error=repr(e));write(OUT/'attempt.json',record);raise
if __name__=='__main__':main()
