#!/usr/bin/env python3
"""ROOT-only literal completed-receipt validation and full all256 durable delta."""
import argparse,hashlib,json,os,resource,shutil,stat,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
import software_owned_v2 as owned
import literal_receipts as literal
HERE=Path(__file__).resolve().parent
ORIGINAL_HELPER=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-allslots-delta-preparation-20261122')
POOL=Path('/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01');COHORT=POOL/'all256-csr01';META=POOL/'all256-delta-records01'
OUT=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-allslots-delta-20261122/closed01')
HELPERS=[Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-allslots-preparation-20261122'),Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-allslots-preparation02-20261122')]
FULLHELPER=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fullcore-preparation-20261122')
OBS=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-observation-preparation-20261122');STD=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-regression-preparation-20261122')
ALL_HELPERS=[FULLHELPER,*HELPERS,OBS,STD,ORIGINAL_HELPER,HERE]
ORDER=['d-enabled','d-off','i-enabled'];CAP=16*1024**2
need=literal.require;bind=literal.bind

def read(p):return json.loads(Path(p).read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def size(p):return sum(q.lstat().st_size for q in p.rglob('*') if q.is_file() or q.is_symlink()) if p.exists() else 0
def verify(r):need(bind(r['path'])==r,'literal file binding drift '+r['path'])
def idle(a):
 verify(a['ROOT_CAD_terminal'])
 q=read(a['ROOT_CAD_terminal']['path']);need(q['ROOT_verified'] is True and q['job']=='20261122T151115Z-a44c03bb7' and q['all_owned_children_absent'] is True and q['global_vendor_absent'] is True,'actual CAD terminal/no-orphans prerequisite')
 names={'vivado','vivado_lab','xelab','xsim','xsimk','xvlog','xsc','planahead','launch_synthesis.sh','run_vivado_2024_2.sh'};found=[]
 for p in Path('/proc').glob('[0-9]*'):
  try:
   comm=(p/'comm').read_text().strip();argv=(p/'cmdline').read_bytes().split(b'\0')
   if comm in names or any(v.decode(errors='replace').rsplit('/',1)[-1] in names for v in argv):found.append(int(p.name))
  except (FileNotFoundError,ProcessLookupError):pass
 need(not found,'vendor/launcher still active: '+str(found))
def guard(a):
 need(size(POOL)<=1024**3 and size(OUT)<=CAP,'original1GiB pool and new16MiB delta cap')
 helpers=sum(size(p) for p in ALL_HELPERS);need(helpers<=1024**2 and size(HERE)<=128*1024,'whole helper1MiB and new source128KiB caps')
 verify(a['ROOT_resource_profile']);q=read(a['ROOT_resource_profile']['path']);need(q['all_other_charged_reserves_included'] is True,'fresh complete global resource profile')
 need(shutil.disk_usage(HERE).free>=q['required_HOME_free_excluding_delta_remaining']+max(0,CAP-size(OUT)),'HOME floor plus all other charges and entire delta remaining')
 need(shutil.disk_usage('/run/user/1001').free>=q['required_RUN_free_bytes'] and shutil.disk_usage('/dev/shm').free>=q['required_SHM_free_bytes'],'all current RAM/future reservations')
 mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'));need(mem>=q['required_MemAvailable_bytes'],'encoder physical RAM reserve')
 return dict(pool_bytes=size(POOL),delta_bytes=size(OUT),whole_helpers=helpers)
def validate(a):
 # No producer imports/load/runtime_sources(): never change the frozen consumed set.
 verify(a['base_closure']);base=read(a['base_closure']['path']);need(base['state']=='PASS lossless base full+clone+STD archival; all256 delta pending','exact lossless base prerequisite');verify(base['archive']);verify(base['embedded_inventory'])
 need(base['archive']['sha256']=='cca7058949c02b0fbefa38f61ad95ef536d972d1ca1ff1a393074315970093be','exact base model/source corpus')
 base_rows=read(base['embedded_inventory']['path'])['members'];base_data={(r['bytes'],r['sha256']):r for r in base_rows if r['kind']=='file'};base_data[(base['embedded_inventory']['bytes'],base['embedded_inventory']['sha256'])]=dict(member='__inventory__.json')
 done=read(COHORT/'ROOT-cohort-complete.json');need(bind(COHORT/'ROOT-cohort-complete.json')['sha256']=='a5ab8e3636a9ac890effac410823af5059c2900dd493004f23b1035e7bc5ca01','exact ROOT all-role terminal')
 need(done==read(ORIGINAL_HELPER/'ROOT-capacity-cohort-complete-export01.json'),'literal exported ROOT terminal')
 need(done['TOP']=='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd' and done['BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa' and done['model_sha256']=='9473086b6efb79a562c9f27882f435a6eaa558b0d363b1ce8184f19d02124a71','actual new CSR source/model, not obsolete profile')
 verify(done['preparation']);p=read(done['preparation']['path']);need(p['schema']=='csr-unmasked256-complete-allslots-v1' and p['schedule']==ORDER,'unchanged completed preparation/order')
 need(len(p['runtime_sources'])==43 and read(COHORT/'runtime-sources.json')==p['runtime_sources'],'literal original43source snapshot; no new module injection')
 for r in p['runtime_sources']:verify(r)
 for name in ['model','reader','compiled_sources','program','ROOT_authority','fixed_reservations','source_plan']:verify(p[name])
 need(p['model']['sha256']==done['model_sha256'] and (p['model']['bytes'],p['model']['sha256']) in base_data,'qualified new model in lossless base')
 compiled=read(p['compiled_sources']['path']);compiled=compiled.get('sources',compiled);need(len(compiled)>300,'complete literal compiled-source inventory')
 for row in compiled.values():
  recorded={k:row[k] for k in ('path','bytes','sha256')};verify(recorded)
  if (row['bytes'],row['sha256']) not in base_data:
   tool=dict(path='/home/coyang/zynq-parrot/install/bin/verilator_bin',bytes=13249056,sha256='e727d230bbbc7d23a88629c288e0d5c08650d907907741e5934b8e0a85e1877e')
   pins=read(base['embedded_inventory']['path'])['identity_pins']
   need(recorded==tool and any(r['category']=='installed_rebuildable_tool_or_library_identity' and {k:r['recorded'][k] for k in tool}==tool and {k:r['observed'][k] for k in tool}==tool for r in pins),'only exact installed Verilator base identity pin may replace source payload')
 program=read(p['program']['path']);need(program['elf']['sha256']=='062a3dd884d64bc1fdf7f0048f312cc5efc84280eb89006c21ef6b60f1f43ed6' and program['max_lines']==1792 and program['max_sets']==256,'unchanged runtime geometry fixture')
 literal.FOUNDATION=p['runtime_sources']+[read(COHORT/(r+'-audit/counter-words.json'))['auditor'] for r in ORDER]
 for r in literal.FOUNDATION:verify(r)
 for role in ORDER:
  anchor=done['roles'][role];verify(anchor['native']);verify(anchor['audit'])
  run=literal.check_native(COHORT,role,p,done['preparation']['path'],anchor['native']['sha256'])
  literal.verify_audit(COHORT,role,p,done['preparation']['path'],anchor['audit']['sha256'])
  full=read(COHORT/(role+'-audit/verification.json'));need(run['counters']==anchor['counter_values'] and full['archive']['full_stream']==anchor['stream'],'full-stream digest/projection/count receipt exactly ROOT accepted')
 return p,done,base,base_data

def record(p,member):
 p=Path(p);s=p.lstat();need(p.is_file() and not p.is_symlink(),'unexpected nonregular input '+str(p))
 return dict(path=str(p),member=member,kind='file',bytes=s.st_size,sha256=bind(p)['sha256'],mode=stat.S_IMODE(s.st_mode),stat=[s.st_size,s.st_ino,s.st_mtime_ns,s.st_ctime_ns,stat.S_IMODE(s.st_mode)])
def collect(a):
 start=time.monotonic();p,done,base,covered=validate(a);rows=[];extra={};base_refs=[];pins=[];seen=set()
 census=read(ORIGINAL_HELPER/'ROOT-capacity-cohort-size-export01.json');current=sorted(str(p) for p in COHORT.rglob('*') if p.is_file());need(current==sorted(r['path'] for r in census['files']),'all77 fixed cohort files, no missing/new scope')
 for r in census['files']:
  f=Path(r['path']);need(f.stat().st_size==r['bytes'] and stat.S_IMODE(f.stat().st_mode)==r['mode'],'actual ROOT metadata census drift')
  rows.append(record(f,'cohort/'+r['relative']))
 # Preserve both old01 unexecuted and actual02 source/authority trees in full.
 for root in ALL_HELPERS:
  for f in root.rglob('*'):
   if f.is_file():extra[str(f)]=f
 # Literal consumed inputs plus exact program/source/root authorities.
 direct=p['runtime_sources']+literal.FOUNDATION+[p[n] for n in ['reader','ROOT_authority','fixed_reservations','source_plan','program']]
 program=read(p['program']['path'])
 sources=program['sources']+[program['converter'],program['compiler']]
 for r in direct+sources:
  verify(r);extra[r['path']]=Path(r['path'])
 # New ROOT authority metadata may point to other source/authority JSON; preserve
 # its directly bound metadata/source pins, not a recursive historical binary DAG.
 def scan(v):
  if isinstance(v,dict):
   if isinstance(v.get('path'),str) and type(v.get('bytes')) is int and isinstance(v.get('sha256'),str) and len(v['sha256'])==64:
    f=Path(v['path']);sig=(str(f),v['bytes'],v['sha256'])
    if f.is_absolute() and sig not in seen:
     seen.add(sig)
     if (v['bytes'],v['sha256']) in covered:
      base_refs.append(dict(recorded=v,base_member=covered[(v['bytes'],v['sha256'])]['member']))
     else:
      verify({k:v[k] for k in ('path','bytes','sha256')})
      installed=any(str(f).startswith(t) for t in ('/usr/','/lib/','/lib64/','/home/coyang/zynq-parrot/install/','/home/coyang/zynq-parrot-linux-research/install/'))
      source=f.suffix in ('.py','.c','.cpp','.h','.hpp','.sv','.svh','.v','.mk','.ld','.specs','.json','.md','.tsv')
      historical=f.name.endswith(('.tar.gz','.tar.xz')) or f.suffix in ('.fst','.dcp') or f.name.startswith('Vbsg_nonsynth_zynq_testbench')
      if installed and not source or historical:pins.append(v)
      else:extra[str(f)]=f
   for z in v.values():scan(z)
  elif isinstance(v,list):
   for z in v:scan(z)
 for r in direct:
  if Path(r['path']).suffix=='.json':scan(read(r['path']))
 # Own executed archiver/admission recipe is independently declared new code.
 for f in HERE.iterdir():
  if f.is_file():extra[str(f)]=f
 for name,f in sorted(extra.items()):
  r=record(f,'executed-source/'+str(f).lstrip('/'))
  if (r['bytes'],r['sha256']) in covered:base_refs.append(dict(recorded=bind(f),mode=r['mode'],live_stat=r['stat'],base_member=covered[(r['bytes'],r['sha256'])]['member']))
  elif not any(name.startswith(t) for t in ('/usr/','/lib/','/lib64/','/home/coyang/zynq-parrot/install/','/home/coyang/zynq-parrot-linux-research/install/')) or f.suffix in ('.py','.c','.cpp','.h','.hpp','.ld','.specs'):rows.append(r)
  else:pins.append(bind(f))
  need(time.monotonic()-start<120,'fixed120s preparation deadline')
 need(len({r['member'] for r in rows})==len(rows),'unique archive member paths')
 rows.sort(key=lambda r:(not r['path'].endswith('.fst'),r['member']))
 return dict(frozen_paths={str(root):sorted(str(p) for p in root.rglob('*') if p.is_file()) for root in [COHORT,*ALL_HELPERS]},schema='csr256-allslots-lossless-delta-v1',members=rows,base_dependency=a['base_closure'],base_archive=base['archive'],base_covered=base_refs,installed_or_historical_identity_only=pins,ROOT_complete=bind(COHORT/'ROOT-cohort-complete.json'),original_frozen_sources=p['runtime_sources'],raw167_reproduction={role:dict(command=read(COHORT/(role+'-audit/reader.owned.json'))['argv'],selection=bind(COHORT/(role+'-audit/selection.tsv')),expected_full_stream=done['roles'][role]['stream'],counter_projection=bind(COHORT/(role+'-audit/gp0-counter-projection.tsv.gz')),record='Complete streamed digest/EOF, not a saved full stream; regenerate from durable raw FST+exact reader/selection, byte-compare expected SHA/size/events/EOF') for role in ORDER},all_actual_cohort_files_retained=True,future_release_authority=False)
def unchanged(c):
 for root,paths in c['frozen_paths'].items():need(sorted(str(p) for p in Path(root).rglob('*') if p.is_file())==paths,'sealed scope added/removed file '+root)
 for r in c['members']:
  s=Path(r['path']).stat();need([s.st_size,s.st_ino,s.st_mtime_ns,s.st_ctime_ns,stat.S_IMODE(s.st_mode)]==r['stat'],'delta source changed '+r['path'])
 for r in c['original_frozen_sources']:verify(r)
 for r in c['base_covered']:
  if 'live_stat' in r:
   s=Path(r['recorded']['path']).stat();need([s.st_size,s.st_ino,s.st_mtime_ns,s.st_ctime_ns,stat.S_IMODE(s.st_mode)]==r['live_stat'],'live base-covered source changed')

def main():
 x=argparse.ArgumentParser(description=__doc__);x.add_argument('--admission',type=Path,required=True);x.add_argument('--admission-sha256',required=True);x.add_argument('--prepare',action='store_true');x.add_argument('--execute',action='store_true');x.add_argument('--prepared-sha256');a0=x.parse_args();need(a0.prepare!=a0.execute,'one phase');a=read(a0.admission);need(bind(a0.admission)['sha256']==a0.admission_sha256 and a['ROOT_approved'] is True,'DRAFT cannot allocate/execute')
 for r in a['inputs']:verify(r)
 idle(a);guard(a);inv=META/'inventory.json';manifest=OUT/'manifest.json'
 if a0.prepare:
  need(not META.exists() and not OUT.exists(),'fresh after-CAD delta preparation');c=collect(a);META.mkdir();write(inv,c);unchanged(c);guard(a);print(json.dumps(dict(inventory=bind(inv),members=len(c['members']),raw_bytes=sum(r['bytes'] for r in c['members']),compressed_fit='UNKNOWN before actual fixed16MiB attempt'),indent=2));return
 need(bind(inv)['sha256']==a0.prepared_sha256 and not OUT.exists(),'exact reviewed fresh delta attempt');c=read(inv);unchanged(c);validate(a);OUT.mkdir(parents=True);record0=dict(state='RUNNING complete all256 lossless delta only',admission=bind(a0.admission),inventory=bind(inv),commands=[],future_release_authority=False);started=time.monotonic()
 def save():write(manifest,record0)
 def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP))
 try:
  for phase,bound in [('compress',600),('roundtrip',180)]:
   left=780-(time.monotonic()-started);need(left>0,'fixed780s total delta');entry=dict(phase=phase);record0['commands'].append(entry);save()
   try:
    with (OUT/(phase+'.log')).open('wb') as log:entry['ownership']=owned.run([sys.executable,HERE/'codec.py','--inventory',inv,'--output',OUT/'all-three-complete-roles.tar.xz','--action',phase],HERE,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,min(left,bound),lambda:(idle(a),guard(a)),limits)
   except BaseException as e:entry['ownership']=getattr(e,'owned_receipt',None);raise
   finally:save()
   need(entry['ownership']['returncode']==0 and entry['ownership']['failure'] is None and not entry['ownership']['owned_group_remaining'],'complete bounded archive phase')
  unchanged(c);validate(a);idle(a);guard(a);record0.update(state='PASS complete lossless new CSR256 three-role delta; final double-pool freeze still required',archive=bind(OUT/'all-three-complete-roles.tar.xz'),base_dependency=c['base_dependency'],base_archive=c['base_archive'],members=len(c['members']),raw_member_bytes=sum(r['bytes'] for r in c['members']),all_actual_cohort_files_retained=True,raw167_reproduction=c['raw167_reproduction'],original_sources_unchanged=True,no_cleanup=True,ROOT_final_double_pool_inventory_pending=True,elapsed_seconds=time.monotonic()-started);save();guard(a)
 except BaseException as e:record0.update(state='FAIL preserved; no retries/cap extension/evidence drop',error=repr(e));save();raise
 print(record0['state'])
if __name__=='__main__':main()
