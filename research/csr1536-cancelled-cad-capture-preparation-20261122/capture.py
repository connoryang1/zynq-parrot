#!/usr/bin/env python3
"""ROOT-only complete canceled1536-CAD capture. No cleanup/reservation release."""
import argparse,gzip,hashlib,importlib.util,json,os,resource,shutil,stat,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
ART=Path('/home/coyang/fpga-artifacts/context-resume/csr-opt1536-fpga-preparation-20261122')
LOG=Path('/home/coyang/fpga-logs-linux-csr-opt1536-trace0-02');NEWLOG=Path('/home/coyang/fpga-logs-linux-csr-opt1536-trace0-03');OUT=ART/'closed-cancel02'
WORK=Path('/run/user/1001/zp-linux-csr-opt1536-trace0-cad-20261122-02');SOURCE=Path('/run/user/1001/zp-linux-csr-opt1536-fpga-source-20261122-02')
HELPER_BASE=Path('/home/coyang/zynq-parrot-linux-host-observer/research')
JOB='20261122T224219Z-a8fbd5fa6';CAP=192*1024**2
ROOTS={'WORK':WORK,'SOURCE':SOURCE,'LOGS':LOG,'ART':ART,'HELPER01':HELPER_BASE/'csr1536-opt-whole-cad-preparation-20261122','HELPER02':HELPER_BASE/'csr1536-opt-whole-cad-preparation02-20261122','CAPTUREHELPER':HERE}
OPS=Path('/home/coyang/zynq-parrot-csr-opt-ops-20261122/codex-skills')
for name in ['launch_synthesis.sh','check_build_ready.sh','run_vivado_2024_2.sh','accept_vivado_build.sh','summarize_vivado.sh','select_vivado_report.sh','check_vivado_timing.sh']:
 ROOTS['OPS-'+name]=OPS/'bp-fpga-synthesis/scripts'/name
ROOTS['OPS-farm_synthesis.sh']=OPS/'bp-synthesis-farm/scripts/farm_synthesis.sh'

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def bind(p):p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def write(p,v):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.replace(p)
def files(root):return sorted([root]+list(root.rglob('*')))
def footprint(roots):
 logical=allocated=0
 for root in roots:
  if not root.exists():continue
  for p in root.rglob('*'):
   if p.is_file() or p.is_symlink():s=p.lstat();logical+=s.st_size;allocated+=s.st_blocks*512
 return max(logical,allocated)
def idle():
 bad=[];names={'vivado','vivado_lab','xelab','xvlog','xsim','xsimk','xsc','planahead','launch_synthesis.sh','run_vivado_2024_2.sh'}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   comm=(p/'comm').read_text().strip();argv=[q.decode(errors='replace') for q in (p/'cmdline').read_bytes().split(b'\0') if q]
   if comm in names or any(v.rsplit('/',1)[-1] in names for v in argv):bad.append(dict(pid=int(p.name),comm=comm,argv=argv))
  except (FileNotFoundError,ProcessLookupError):pass
 need(not bad,'vendor/launcher present; no capture or retirement '+json.dumps(bad[:2]))
 p=Path('/proc/1553164')
 try:
  s=(p/'stat').read_text();v=s[s.rfind(')')+2:].split();need(int(v[19])!=100315010,'exact old worker still exists')
 except (FileNotFoundError,ProcessLookupError):pass
 return dict(all_owned_children_absent=True,global_vendor_absent=True,old_worker=dict(pid=1553164,startticks=100315010,absent_by_identity=True))
def terminal(a):
 for r in (a['old_admission'],a['terminal'],a['post_cancel'],a['ROOT_no_orphans']):need(bind(r['path'])==r,'frozen canceled-job prerequisite drift')
 t=json.loads(Path(a['terminal']['path']).read_text());need(t['status']=='CANCELLED' and t['cause']==[dict(kind='allocation_cap',name='work',actual=598560768,maximum=536870912)],'exact resource-only cancellation')
 p=json.loads(gzip.decompress(Path(a['post_cancel']['path']).read_bytes()));need(p['job']==JOB and p['worker'] is None and p['all_vivado']==[] and p['global_vendor_tools']==[] and p['worker_group']==[],'old terminal disappearance snapshot')
 need(json.loads(Path(a['ROOT_no_orphans']['path']).read_text())['ROOT_verified'] is True,'ROOT separate no-orphans proof');return idle()
def guard(a):
 used=footprint([ART,LOG,NEWLOG]);need(used<=CAP,'UNCHANGED192MiB FAMILY_ART+oldLOG+newLOG union; no per-attempt second cap')
 source=footprint([HERE]);need(source<=128*1024,'prospective128KiB capture-helper inside existing metadata/logging reserve')
 r=a['ROOT_resource_preflight'];need(bind(r['path'])==r,'fresh capture resource preflight drift');q=json.loads(Path(r['path']).read_text())
 need(q['ROOT_approved'] is True and q['all_other_charged_reserves_included'] is True and q['HOME_floor_bytes']==1879048192 and q['logging_growth_reserve_bytes']==134217728,'ROOT fresh capture1.75GiB floor/logging/all OTHER authority')
 need(q['old512MiB_bound_violation_preserved'] is True and q['new_CAD_launch_reserved'] is False,'capture-only; old598560768>512MiB failure preserved; future clean retry separate')
 need(shutil.disk_usage(ART).free>=q['required_HOME_free_excluding_this_family_remaining']+max(0,CAP-used),'HOME floor+logging+OTHER+entire shared192 remainder')
 need(shutil.disk_usage('/run/user/1001').free>=q['required_RUN_free_bytes'] and shutil.disk_usage('/dev/shm').free>=q['required_SHM_free_bytes'],'unchanged OTHER/native/source/current actual RAM ownership')
 mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'));need(mem>=q['required_MemAvailable_bytes'],'physical memory includes1GiB encoder allowance and all RAM reservations')
 for r in a['protected_current_bindings']:need(bind(r['path'])==r,'current resource basis drift')
 return idle()

def row(p,label,root):
 s=p.lstat();r=dict(path=str(p),member=label+'/'+p.relative_to(root).as_posix() if p!=root else label,mode=stat.S_IMODE(s.st_mode),inode=s.st_ino,device=s.st_dev,nlink=s.st_nlink,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,uid=s.st_uid,gid=s.st_gid)
 if p.is_symlink():b=os.readlink(p).encode();r.update(kind='symlink',target=os.readlink(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 elif p.is_dir():r.update(kind='directory',bytes=0,sha256=hashlib.sha256(b'').hexdigest())
 else:need(p.is_file(),'special input '+str(p));r.update(kind='file',bytes=s.st_size,sha256=sha(p))
 return r
def inventory(a,without_work=False):
 out=[];last=time.monotonic()
 for label,root in ROOTS.items():
  if without_work and label=='WORK':continue
  need((root.is_dir() or root.is_file()) and not root.is_symlink(),'exact input root '+str(root))
  for p in files(root):
   if p==OUT or OUT in p.parents:continue
   if time.monotonic()-last>.5:guard(a);last=time.monotonic()
   out.append(row(p,label,root))
 return out
def stable(a,c,without_work=False):
 current=inventory(a,without_work);expected=[r for r in c['members'] if not without_work or not r['member'].startswith('WORK/') and r['member']!='WORK']
 # Creating OUT changes ART's directory timestamps only; preserve/check its mode.
 def compare(r):return {k:v for k,v in r.items() if not (r['member']=='ART' and k in ('mtime_ns','ctime_ns','nlink'))}
 need([compare(r) for r in current]==[compare(r) for r in expected],'ALL source/log/art/helper/input bytes/modes/links changed')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);p.add_argument('--prepare',action='store_true');p.add_argument('--capture',action='store_true');p.add_argument('--inventory-sha256');x=p.parse_args();need(sum([x.prepare,x.capture])==1,'one ROOT phase');a=json.loads(x.admission.read_text());ab=bind(x.admission);need(ab['sha256']==x.admission_sha256 and a['ROOT_approved'] is True,'exact ROOT-approved authority');need(a['TOP']=='a8fbd5fa6911160ab0845d75c6096549806af7b7' and a['BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','unchanged canceled source');need(a['aggregate_evidence_cap_bytes']==CAP,'original192MiB cap unchanged')
 for r in a['inputs']:need(bind(r['path'])==r,'source/admission prerequisite drift')
 terminal(a);guard(a);inv=OUT/'inventory.json';manifest=OUT/'manifest.json'
 if x.prepare:
  need(not OUT.exists(),'fresh capture-only output');start=time.monotonic();members=inventory(a);need(time.monotonic()-start<120,'120s entry inventory');need(sum(r['bytes'] for r in members)<=1024**3,'fixed1GiB raw corpus; no omission');need(all(r['bytes']<=128*1024**2 for r in members),'fixed128MiB per input; no omission');OUT.mkdir();c=dict(schema='csr1536-cancelled-cad-lossless-inventory-v1',admission=ab,roots={k:str(v) for k,v in ROOTS.items()},members=members,source_and_Gitadmin_included=True,all_original_WORK_bytes_included=True,operational_status='CANCELLED old WORK512MiB allocation bound; no area/fit outcome; actual598560768B preserved');write(inv,c);stable(a,c);terminal(a);guard(a);print(json.dumps(dict(inventory=bind(inv),members=len(members),raw_bytes=sum(r['bytes'] for r in members)),indent=2));return
 c=json.loads(inv.read_text());need(c['admission']==ab,'same frozen capture inventory authority')
 if x.capture:
  need(bind(inv)['sha256']==x.inventory_sha256 and not manifest.exists(),'exact reviewed one-shot capture');stable(a,c);start=time.monotonic();rec=dict(state='RUNNING canceled-CAD capture only',admission=ab,inventory=bind(inv),commands=[])
  def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(160*1024**2,160*1024**2))
  try:
   for action,cap in [('compress',600),('roundtrip',180)]:
    remaining=780-(time.monotonic()-start);need(remaining>0,'fixed780s capture batch');entry=dict(action=action);rec['commands'].append(entry);write(manifest,rec)
    try:
     with (OUT/(action+'.log')).open('wb') as log:entry['ownership']=owned.run([sys.executable,HERE/'codec.py','--inventory',inv,'--output',OUT/'full-cancelled-work-source.tar.xz','--action',action],HERE,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,min(cap,remaining),lambda:guard(a),limits)
    except BaseException as e:entry['ownership']=getattr(e,'owned_receipt',None);raise
    finally:write(manifest,rec)
    need(entry['ownership']['returncode']==0 and entry['ownership']['failure'] is None and not entry['ownership']['owned_group_remaining'],'complete owned archive phase')
   stable(a,c);absence=terminal(a);rec.update(state='PASS complete lossless canceled CAD WORK+SOURCE+Gitadmin+LOGS+ART+helpers capture; no fit result',archive=bind(OUT/'full-cancelled-work-source.tar.xz'),all_members=len(c['members']),raw_member_bytes=sum(r['bytes'] for r in c['members']),all_originals_unchanged=True,absence=absence,original_limits_unchanged=True,no_hardware_or_guest_changes=True,elapsed_seconds=time.monotonic()-start);write(manifest,rec);guard(a)
   write(OUT/'ROOT-cancelled-closure.DRAFT.json',dict(schema='csr1536-cancelled-CAD-closure-v1',ROOT_verified=False,job=JOB,TOP=a['TOP'],BP=a['BP'],terminal=a['terminal'],capture=bind(manifest),all_owned_children_absent=True,global_vendor_absent=True,no_fit_result=True,old_cap_bytes=536870912,old_observed_allocated_bytes=598560768,original_limits_unchanged=True,all_originals_preserved=True,no_automatic_reservation_release=True,no_cleanup=True));guard(a)
  except BaseException as e:rec.update(state='FAIL preserved capture; no retries/extension/retirement',error=repr(e));write(manifest,rec);raise
  print(rec['state']);return

if __name__=='__main__':main()
