#!/usr/bin/env python3
"""ROOT-only two-phase retirement of exact old generated compiler caches."""
import argparse,hashlib,json,os,re,shutil,stat,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
HELPER_ROOT=HERE.parent
PRODUCER_UID=1001
OUT=Path('/home/coyang/fpga-artifacts/context-resume/legacy-native-cache-retirement-20261122')
REQUIRED=5988765106 # unchanged1GiB current +2.5GiB CAD +1GiB floor +full OTHER
RECEIPT_CAP=4*1024**2
START=None

def require(v,m):
 if not v:raise ValueError(m)
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def bind(p):
 p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=digest(p))
def size(root):return sum(p.lstat().st_size for p in root.rglob('*') if p.is_file() or p.is_symlink()) if root.exists() else 0
def write(p,v):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.replace(p)
def guard(a):
 require(time.monotonic()-START<=600,'fixed600s total audit/retirement phase')
 require(size(OUT)<=RECEIPT_CAP and size(HELPER_ROOT)<=65536,'4MiB complete receipts/64KiB helper caps')
 r=a['ROOT_resource_preflight'];require(bind(r['path'])==r,'ROOT resource preflight drift')
 q=json.loads(Path(r['path']).read_text());require(q['all_other_charged_reserves_included'] is True and q['cache_retirement_HOME_remaining_reserved_bytes']>=RECEIPT_CAP-size(OUT),'explicit new receipt allocation inside global HOME budget')
 require(shutil.disk_usage(HERE).free>=q['required_HOME_free_without_retirement_receipts']+max(0,RECEIPT_CAP-size(OUT)),'HOME existing reserves+new remaining')
 for r in a['active_protected_bindings']:require(bind(r['path'])==r,'active CSR basis drift')

def proc_identity(p):
 s=(p/'stat').read_text();fields=s[s.rfind(')')+2:].split();return dict(pid=int(p.name),startticks=int(fields[19]),state=fields[0],ppid=int(fields[1]),pgid=int(fields[2]),sid=int(fields[3]))
def owner_scan(roots):
 patterns=[re.compile(re.escape(str(p))+r'(?=/|\s|$|[\"\x27])') for p in roots];matches=[];races=[];skipped=[]
 def hit(value):return any(pattern.search(value) for pattern in patterns)
 for p in Path('/proc').glob('[0-9]*'):
  try:
   before=proc_identity(p);status=(p/'status').read_text();uids=next(l.split()[1:] for l in status.splitlines() if l.startswith('Uid:'));euid=int(uids[1])
   if euid!=PRODUCER_UID:
    skipped.append(dict(pid=int(p.name),startticks=before['startticks'],comm=(p/'comm').read_text().strip(),euid=euid));continue
   evidence=[]
   for name in ('cwd','exe'):
    try:v=os.readlink(p/name)
    except FileNotFoundError:continue
    if hit(v):evidence.append(dict(kind=name,value=v))
   args=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
   if hit(args):evidence.append(dict(kind='argv',value=args))
   for f in (p/'fd').iterdir():
    try:v=os.readlink(f)
    except FileNotFoundError:continue
    if hit(v):evidence.append(dict(kind='fd',value=v))
   for line in (p/'maps').read_text().splitlines():
    if hit(line):evidence.append(dict(kind='maps',value=line))
   after=proc_identity(p)
   require(before['startticks']==after['startticks'],'PID reuse during ownership scan')
   if evidence:matches.append(dict(identity=after,evidence=evidence))
  except (FileNotFoundError,ProcessLookupError):races.append(int(p.name))
  except PermissionError:raise ValueError('cannot prove UID1001 producer absence due /proc permissions: '+p.name)
 require(not matches,'old pool still has active user: '+json.dumps(matches[:3]))
 return dict(state='PASS no current UID1001 old-pool argv/cwd/exe/fd/maps users; other UIDs out of scope',producer_euid=PRODUCER_UID,not_global_all_UID_absence=True,matches=matches,exited_during_scan=races,other_UID_processes_skipped=skipped)

def statrow(p):
 s=p.lstat();return dict(bytes=s.st_size,allocated_bytes=s.st_blocks*512,mode=stat.S_IMODE(s.st_mode),inode=s.st_ino,device=s.st_dev,uid=s.st_uid,nlink=s.st_nlink,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
def inventory(a):
 rows=[];objroots=[Path(p) for p in a['allowed_object_roots']];poolroots=[Path(p) for p in a['old_pool_roots']]
 for root in poolroots:
  require(root.is_dir() and not root.is_symlink(),'exact old ROOT pool must exist')
  for p in sorted(root.rglob('*')):
   if p.is_dir() and not p.is_symlink():continue
   r=dict(path=str(p));r.update(statrow(p))
   inside=any(q in p.parents for q in objroots)
   candidate=inside and p.suffix in ('.o','.a','.gch')
   if candidate:
    require(stat.S_ISREG(p.lstat().st_mode) and not p.is_symlink() and r['nlink']==1 and r['uid']==PRODUCER_UID,'only UID1001 singly-linked regular generated cache')
    require(not any(str(p).startswith(x+'/') or str(p)==x for x in a['forbidden_current_roots']),'current CSR/evidence intersection')
    require(str(p) not in {v['path'] for v in a['active_protected_bindings']},'active input cannot be retired')
   if p.is_symlink():
    data=os.readlink(p).encode();r.update(kind='symlink',target=os.readlink(p),sha256=hashlib.sha256(data).hexdigest())
   else:require(p.is_file(),'unexpected special pool member');r.update(kind='file',sha256=digest(p))
   r['retire']=candidate;rows.append(r)
 return rows

def verify_durable(a):
 refs=[];containers={}
 for r in a['durable_prerequisites']:
  require(bind(r['path'])=={k:r[k] for k in ('path','bytes','sha256')},'durable closure drift')
  q=json.loads(Path(r['path']).read_text());require(q.get('state')==r['state'],'exact recorded closure state');refs.append(r)
  def visit(v):
   if isinstance(v,dict):
    if isinstance(v.get('path'),str) and type(v.get('bytes')) is int and isinstance(v.get('sha256'),str):
     p=Path(v['path'])
     if str(p).startswith('/home/coyang/fpga-artifacts/context-resume/') and p.name.endswith(('.gz','.xz')):containers[str(p)]={k:v[k] for k in ('path','bytes','sha256')}
    for z in v.values():visit(z)
   elif isinstance(v,list):
    for z in v:visit(z)
  visit(q)
 for r in containers.values():require(bind(r['path'])==r,'durable compressed source/model/FST/archive byte identity')
 for r in a['selected_terminal_and_model']:
  require(bind(r['path'])==r,'selected final old terminal/model drift')
  if Path(r['path']).name=='session.json':require(json.loads(Path(r['path']).read_text())['state'].startswith('PASS'),'old selected composite must be terminal PASS')
 return dict(closures=refs,checked_container_bindings=list(containers.values()),selected=a['selected_terminal_and_model'])

def main():
 global START
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);p.add_argument('--prepare',action='store_true');p.add_argument('--execute',action='store_true');p.add_argument('--manifest-sha256');x=p.parse_args();require(x.prepare!=x.execute,'one ROOT action');START=time.monotonic();ab=bind(x.admission);require(ab['sha256']==x.admission_sha256,'exact ROOT authority');a=json.loads(x.admission.read_text());require(a['ROOT_approved'] is True and a['ROOT_old_pools_obsolete_no_new_producers'] is True,'DRAFT not executable; ROOT old-producer quiescence required');require(os.geteuid()==PRODUCER_UID and a['ROOT_no_privileged_or_other_UID_old_pool_producers'] is True,'ROOT producer-UID scope declaration required');require(a['fixed_unchanged_required_RUN_free_bytes']==REQUIRED,'unchanged old/current/CAD resource terms');guard(a)
 for r in a['source_inputs']:require(bind(r['path'])==r,'retirement helper/provenance input drift')
 roots=[Path(p) for p in a['old_pool_roots']];require(roots and all(str(p).startswith('/run/user/1001/') for p in roots),'actual ROOT RUN namespace')
 prep=OUT/'retirement-manifest.json';done=OUT/'completion.json'
 if x.prepare:
  require(not OUT.exists(),'fresh retirement preparation');before=owner_scan(roots);durable=verify_durable(a);rows=inventory(a);guard(a);require(inventory(a)==rows,'double full-byte/mode/link/inode inventories differ');after=owner_scan(roots);candidates=[r for r in rows if r['retire']];require(candidates,'no candidate caches');free=shutil.disk_usage('/run/user/1001').free;logical=sum(r['bytes'] for r in candidates);allocated=sum(r['allocated_bytes'] for r in candidates)
  OUT.mkdir();m=dict(schema='legacy-native-cache-retirement-manifest-v1',state='PREPARED no deletion; ROOT exact manifest review required',admission=ab,all_members=rows,logical_cache_bytes=logical,allocated_cache_bytes=allocated,cache_files=len(candidates),protected_files=len(rows)-len(candidates),ROOT_owner_absence_before=before,ROOT_owner_absence_after=after,durable=durable,RUN_free_before=free,unchanged_required_RUN_free_bytes=REQUIRED,sufficient_if_all_candidates_reclaimed=free+allocated>=REQUIRED,rebuild_recipe=a['rebuild_recipe'],historical_freeze_receipts_unchanged=a['historical_freeze_receipts_unchanged'],no_future_release=True,no_cleanup_of_any_raw_evidence=True)
  write(prep,m);guard(a);print(json.dumps(dict(manifest=bind(prep),cache_files=len(candidates),logical_cache_bytes=logical,allocated_cache_bytes=allocated,RUN_free_before=free,projected_free_after=free+allocated,sufficient=m['sufficient_if_all_candidates_reclaimed']),indent=2));return
 require(bind(prep)['sha256']==x.manifest_sha256 and not done.exists(),'fresh explicitly reviewed prepared manifest');m=json.loads(prep.read_text());require(m['admission']==ab and m['state'].startswith('PREPARED'),'same exact ROOT authority');before=owner_scan(roots);require(inventory(a)==m['all_members'],'ALL old files changed after review');verify_durable(a);candidates=[r for r in m['all_members'] if r['retire']];free=shutil.disk_usage('/run/user/1001').free;require(free+sum(r['allocated_bytes'] for r in candidates)>=REQUIRED,'actual prospective free insufficient; no deletion')
 record=dict(state='RUNNING exact cache retirement only',admission=ab,prepared_manifest=bind(prep),owner_absence_before=before,deleted=[],protected_before_sha256=hashlib.sha256(json.dumps([r for r in m['all_members'] if not r['retire']],sort_keys=True).encode()).hexdigest(),no_future_release=True)
 try:
  for r in candidates:
   guard(a);path=Path(r['path']);now=statrow(path);require(all(now[k]==r[k] for k in now) and not path.is_symlink() and digest(path)==r['sha256'],'candidate revalidation failed');path.unlink();record['deleted'].append(r)
  owner=owner_scan(roots);remaining=inventory(a);expected=[r for r in m['all_members'] if not r['retire']];require(remaining==expected,'protected bytes/modes/links changed or unexpected new pool members');verify_durable(a);guard(a);actual_free=shutil.disk_usage('/run/user/1001').free
  for r in a['source_inputs']:require(bind(r['path'])==r,'source endcheck drift')
  record.update(state='PASS retired only exact old rebuildable compiler caches; no raw evidence/future/cap changes',owner_absence_after=owner,protected_after_sha256=hashlib.sha256(json.dumps(remaining,sort_keys=True).encode()).hexdigest(),protected_files=len(remaining),deleted_logical_bytes=sum(r['bytes'] for r in candidates),deleted_allocated_bytes=sum(r['allocated_bytes'] for r in candidates),RUN_free_after=actual_free,unchanged_required_RUN_free_bytes=REQUIRED,unchanged_maxfuture_budget_fits_now=actual_free>=REQUIRED,old_historical_markers_preserved=True,requires_new_admission_for_old_cache_rebuild=True,elapsed_seconds=time.monotonic()-START)
 except BaseException as e:record.update(state='FAIL preserved partial retirement; no other deletion or automatic continuation',error=repr(e));raise
 finally:write(done,record)
 print(record['state'])
if __name__=='__main__':main()
