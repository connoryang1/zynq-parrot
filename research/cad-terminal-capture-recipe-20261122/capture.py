#!/usr/bin/env python3
"""ROOT-only lossless terminal capture; identities/resources come from reviewed JSON."""
import argparse,hashlib,json,os,resource,shutil,stat,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
ARCHIVE_CAP=256*1024**2
OUTPUT_CAP=288*1024**2
FLAGS=dict(BP_RETAINED_BUFFER=1,BP_RETAINED_I_LINES=256,BP_RETAINED_D_LINES=256,BP_RETAINED_SETS=256,BP_RETAINED_OBSERVE=1,BP_AXI_RESPONSE_DELAY=0,BP_CACHE_MISS_TRACE=0)
DEADLINE=None
LAST=0

def need(v,m):
 if not v:raise ValueError(m)
def write(p,v):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.replace(p)
def sha(p,check=None):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):
   h.update(b)
   if check:check()
 return h.hexdigest()
def bind(p,check=None):
 p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p,check))
def exact(r,check=None):
 need(bind(r['path'],check)==r,'binding drift: '+r['path']);return json.loads(Path(r['path']).read_text())
def amount(root):
 if not root.exists():return 0
 logical=allocated=0
 for p in root.rglob('*'):
  if p.is_file() or p.is_symlink():
   s=p.lstat();logical+=s.st_size;allocated+=s.st_blocks*512
 return max(logical,allocated)
def absent(a):
 names={'vivado','vivado_lab','xelab','xvlog','xsim','xsimk','xsc','planahead','launch_synthesis.sh','run_vivado_2024_2.sh'}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   comm=(p/'comm').read_text().strip();argv=[x.decode(errors='replace') for x in (p/'cmdline').read_bytes().split(b'\0') if x]
   need(comm not in names and not any(x.rsplit('/',1)[-1] in names for x in argv),'vendor/launcher exists; refuse capture')
  except (FileNotFoundError,ProcessLookupError):pass
 p=Path('/proc')/str(a['worker']['pid'])
 try:
  s=(p/'stat').read_text();parts=s[s.rfind(')')+2:].split();need(int(parts[19])!=a['worker']['startticks'],'exact worker still exists')
 except (FileNotFoundError,ProcessLookupError):pass
 return dict(global_vendor_absent=True,exact_worker_absent=True)
def guard(a,force=False):
 global LAST
 now=time.monotonic()
 if DEADLINE is not None:need(now<DEADLINE,'fixed phase deadline exceeded; no extension')
 if not force and now-LAST<.5:return
 LAST=now
 out=Path(a['output']);used=amount(out);need(used<=OUTPUT_CAP,'fixed output family cap')
 q=a['ROOT_terminal_resources'];need(q['ROOT_approved'] is True and q['all_other_charged_reserves_included'] is True,'unfunded output: ROOT terminal resource review required')
 need(q['HOME_floor_bytes']==1879048192 and q['logging_future_bytes']==128*1024**2,'prospective floor/logging reserve')
 need(q['required_HOME_free_excluding_new_output_remaining']>=q['HOME_floor_bytes']+q['logging_future_bytes'],'missing floor/logging price')
 need(q['original_CAD_future_remainder_fully_priced'] is True,'no silent original192MiB future release')
 need(shutil.disk_usage(out.parent).free>=max(q['required_HOME_free_excluding_new_output_remaining']+max(0,OUTPUT_CAP-used),q['active_native_HOME_required_upper_bound_bytes']),'full HOME remaining/output/logging/native/OTHER reserve')
 for volume,key in [('/run/user/1001','required_RUN_free_bytes'),('/dev/shm','required_SHM_free_bytes')]:need(shutil.disk_usage(volume).free>=q[key],'RAM volume reserves')
 mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
 need(mem>=q['required_MemAvailable_bytes'] and q['required_MemAvailable_bytes']>=1024**3,'RAM reserves include1GiB encoder')
def terminal(a):
 need(a['ROOT_approved'] is True and a['schema']=='cad-terminal-capture-v1','ROOT exact terminal admission required')
 old=exact(a['final_admission']);cfg=old['configuration']
 need(old['top']==a['TOP'] and old['bp']==a['BP'] and cfg['expected_defines']==FLAGS,'exact source/seven static flags')
 need(cfg['work_root']==a['roots']['WORK'] and cfg['prepared_source_root']==a['roots']['SOURCE'] and cfg['log_root']==a['roots']['LOGS'],'exact source/work/log namespaces')
 need(a['job'].endswith('-'+a['TOP'][:9]),'exact job source suffix')
 t=exact(a['terminal']);need(t.get('status') in ('PASS','FAIL','CANCELLED'),'actual terminal status required, never RUNNING')
 release=exact(a['ROOT_terminal_release']);need(release['ROOT_verified'] is True and release['job']==a['job'] and release['worker']==a['worker'] and release['all_owned_children_absent'] is True and release['global_vendor_absent'] is True,'ROOT exact terminal disappearance receipt')
 need(a['archive_cap_bytes']==ARCHIVE_CAP and a['output_family_cap_bytes']==OUTPUT_CAP,'prospective capture caps, no runtime changes')
 need(a['no_reservation_release'] is True and a['no_cleanup'] is True,'capture never releases or deletes')
 for r in a['inputs']:exact_or_file(r)
 absent(a);guard(a,True)
def exact_or_file(r):need(bind(r['path'])==r,'frozen helper/authority drift')
def refs(a):
 for x in a['opaque_references']:
  q=exact(x['manifest'],lambda:guard(a));need(str(q['state']).startswith('PASS') and q['all_originals_unchanged'] is True,'prior complete verified opaque preservation')
  need(q['archive']==x['archive'] and q['all_members']==x['members'],'exact opaque archive/member coverage')
  need(all(c['ownership']['returncode']==0 and c['ownership']['failure'] is None and not c['ownership']['owned_group_remaining'] for c in q['commands']),'prior roundtrip/ownership proof')
  need(bind(x['archive']['path'],lambda:guard(a))==x['archive'],'durable referenced bytes unchanged')
  need(bind(q['inventory']['path'],lambda:guard(a))==q['inventory'],'prior exact member inventory unchanged')
def row(p,label,root,a):
 s=p.lstat();r=dict(path=str(p),member=label+'/'+p.relative_to(root).as_posix() if p!=root else label,mode=stat.S_IMODE(s.st_mode),inode=s.st_ino,device=s.st_dev,nlink=s.st_nlink,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,uid=s.st_uid,gid=s.st_gid)
 if p.is_symlink():
  target=os.readlink(p);r.update(kind='symlink',target=target,bytes=len(os.fsencode(target)),sha256=hashlib.sha256(os.fsencode(target)).hexdigest())
 elif p.is_dir():r.update(kind='directory',bytes=0,sha256=hashlib.sha256(b'').hexdigest())
 else:
  need(p.is_file(),'special file refused');r.update(kind='file',bytes=s.st_size,sha256=sha(p,lambda:guard(a)))
  matches=[i for i,x in enumerate(a['opaque_references']) if str(p)==x['archive']['path']]
  if matches:
   need(len(matches)==1 and r['bytes']==a['opaque_references'][matches[0]]['archive']['bytes'] and r['sha256']==a['opaque_references'][matches[0]]['archive']['sha256'],'opaque reference exact path/bytes/hash')
   r.update(preservation='external',reference=matches[0])
 return r
def inventory(a):
 result=[];out=Path(a['output'])
 for label,name in a['roots'].items():
  need(label.isidentifier(),'safe archive namespace');root=Path(name);need(root.is_dir() and not root.is_symlink(),'explicit actual input directory')
  need(root!=out and root not in out.parents and out not in root.parents,'output outside input roots, no capture recursion')
  for p in [root]+sorted(root.rglob('*')):guard(a);result.append(row(p,label,root,a))
 for i,name in enumerate(a['additional_authority_files']):
  p=Path(name);need(p.is_file() and not p.is_symlink(),'explicit ROOT authority regular file');result.append(row(p,'AUTHORITY_'+str(i),p,a))
 need(len({r['member'] for r in result})==len(result),'duplicate archive namespace')
 for name in a['required_gitadmin_paths']:
  gp=Path(name);need(gp.exists(),'private Gitadmin missing')
  need(any(gp==Path(r) or Path(r) in gp.parents for r in a['roots'].values()),'Gitadmin outside preserved roots: add explicit ROOT-reviewed root')
 return result
def stable(a,c):need(inventory(a)==c['members'],'every original input bytes/modes/links/metadata unchanged')
def limits():
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(ARCHIVE_CAP,ARCHIVE_CAP))
def main():
 global DEADLINE
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--admission',type=Path,required=True);ap.add_argument('--admission-sha256',required=True);ap.add_argument('--phase',choices=['prepare','capture','verify'],required=True);ap.add_argument('--inventory-sha256');ap.add_argument('--capture-sha256');args=ap.parse_args()
 ab=bind(args.admission);need(ab['sha256']==args.admission_sha256,'exact ROOT admission SHA');a=json.loads(args.admission.read_text());start=time.monotonic();DEADLINE=start+(1200 if args.phase=='capture' else 180)
 out=Path(a['output']);need(out.parent.is_dir(),'ROOT creates reviewed fresh output parent before admission');terminal(a);refs(a)
 ip=out/'inventory.json';mp=out/'manifest.json';archive=out/'full-terminal.tar.xz'
 if args.phase=='prepare':
  need(not out.exists(),'fresh output required');members=inventory(a);out.mkdir()
  write(ip,dict(schema='cad-terminal-lossless-inventory-v1',admission=ab,roots=a['roots'],members=members,opaque_references=a['opaque_references'],required_gitadmin_paths=a['required_gitadmin_paths'],no_excluded_original_paths=True))
  stable(a,json.loads(ip.read_text()));terminal(a);guard(a,True);print(json.dumps(dict(state='PASS prepared complete inventory only; no archive/capture/release',inventory=bind(ip),members=len(members)),indent=2));return
 need(bind(ip)['sha256']==args.inventory_sha256,'ROOT exact reviewed inventory');c=json.loads(ip.read_text());need(c['admission']==ab,'same source/terminal/resource authority');stable(a,c)
 if args.phase=='verify':
  need(bind(mp)['sha256']==args.capture_sha256,'ROOT exact completed capture');q=json.loads(mp.read_text());need(str(q['state']).startswith('PASS'),'no failed capture acceptance');need(bind(q['archive']['path'],lambda:guard(a))==q['archive'],'archive bytes');refs(a);stable(a,c);terminal(a)
  write(out/'verification.json',dict(state='PASS independent original/archive identity and prior all-member roundtrip receipts; no reservation release',capture=bind(mp),inventory=bind(ip),archive=q['archive'],originals_unchanged=True,opaque_references=a['opaque_references'],no_reservation_release=True));return
 need(not mp.exists(),'one capture attempt; preserve prior failure');rec=dict(state='RUNNING terminal preservation, no fit or future release',admission=ab,inventory=bind(ip),commands=[]);write(mp,rec)
 try:
  for action,bound in [('compress',900),('roundtrip',240)]:
   guard(a,True);entry=dict(action=action);rec['commands'].append(entry);write(mp,rec)
   try:
    with (out/(action+'.log')).open('wb') as log:entry['ownership']=owned.run([sys.executable,HERE/'codec.py','--inventory',ip,'--output',archive,'--action',action],HERE,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,min(bound,DEADLINE-time.monotonic()),lambda:guard(a),limits)
   except BaseException as e:entry['ownership']=getattr(e,'owned_receipt',None);raise
   finally:write(mp,rec)
   o=entry['ownership'];need(o['returncode']==0 and o['failure'] is None and not o['owned_group_remaining'],'complete owned codec phase')
  refs(a);stable(a,c);absence=terminal(a);guard(a,True)
  rec.update(state='PASS complete terminal capture with explicit durable opaque references; no fit interpretation or reservation release',archive=bind(archive,lambda:guard(a)),all_original_paths=len(c['members']),new_archive_payload_members=sum(r.get('preservation')!='external' for r in c['members']),opaque_reference_members=sum(r.get('preservation')=='external' for r in c['members']),opaque_references=a['opaque_references'],all_originals_unchanged=True,no_reservation_release=True,no_cleanup=True,terminal_outcome=exact(a['terminal'])['status'],elapsed_seconds=time.monotonic()-start);write(mp,rec)
 except BaseException as e:rec.update(state='FAIL preserved capture; no retry/extension/release',error=repr(e));write(mp,rec);raise
 print(rec['state'])
if __name__=='__main__':main()
