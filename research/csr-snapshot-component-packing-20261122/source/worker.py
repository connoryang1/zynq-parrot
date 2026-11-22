#!/usr/bin/env python3
"""ROOT per-VM one-job CAD worker, never an atomic/global lock or board owner."""
import argparse,collections,datetime,hashlib,json,os,re,resource,shutil,signal,socket,sys,time,uuid,tarfile,zipfile,io
from pathlib import Path
sys.dont_write_bytecode=True
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
FAMILY=Path('/run/user/1001/zp-csr-snapshot-component-packing-20261122-01')
OUT=FAMILY/'run01'
A=HERE/'admission.FINAL.json'
DRAFT=HERE/'admission.DRAFT.json'
WRAPPER=Path('/home/coyang/zynq-parrot/codex-skills/bp-fpga-synthesis/scripts/run_vivado_2024_2.sh')
CAP=256*1024**2
FLOOR=2684354560
HOME_CAP=8*1024**2
HOME_FAMILY=HERE.parent
RAM_FLOOR=1024**3
SHM_FLOOR=512*1024**2
CASES=['baseline04','unmasked05']
SETTINGS=dict(device='xc7z020clg400-1',Vivado='2024.2',max_threads=2,clock_period_ns=50,clock_waveform_ns=[0,25],input_output_delay_ns=0,out_of_context=True,opt_directive='Default',place_directive='Default',synthesis=False,physical_optimization=False,routing=False)
VENDOR_NAMES={'vivado','vivado_lab','xelab','xsim','xsimk','xsimk.exe','xvlog','xsc','vitis_hls','v++','planahead'}
VENDOR_LAUNCHERS={'run_vivado_2024_2.sh','launch_synthesis.sh'}
class ForeignJob(RuntimeError):pass
class Deferred(RuntimeError):pass

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def save(p,o):
 tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(o,indent=2)+'\n');tmp.replace(p)
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def usage(p):return sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) if p.exists() else 0
def stat_row(pid):
 p=Path('/proc')/str(pid);text=(p/'stat').read_text();end=text.rfind(')');fields=text[end+2:].split()
 return dict(pid=int(pid),comm=text[text.find('(')+1:end],ppid=int(fields[1]),pgid=int(fields[2]),state=fields[0],startticks=int(fields[19]))
def process_rows():
 rows=[]
 for p in Path('/proc').glob('[0-9]*'):
  try:
   rec=stat_row(p.name);cmd=(p/'cmdline').read_bytes().split(b'\0');rec['argv']=[x.decode(errors='replace') for x in cmd if x]
   if stat_row(p.name)['startticks']!=rec['startticks']:continue
   rows.append(rec)
  except (FileNotFoundError,ProcessLookupError):continue
  except PermissionError:
   # Kernel process identity remains the basic global vendor check. Never
   # expose unrelated inaccessible command lines or search credentials.
   try:rec=stat_row(p.name);rec['argv']=[];rec['cmdline_unreadable']=True;rows.append(rec)
   except (FileNotFoundError,ProcessLookupError):continue
 return rows

def is_vendor(row):
 if row['comm'].lower() in VENDOR_NAMES:return True
 if row['comm'].lower() in ('pgrep','ps','grep'):return False
 return any(str(arg).split('/')[-1].lower() in VENDOR_NAMES|VENDOR_LAUNCHERS for arg in row.get('argv',[]))
def vendor_inventory(rows,allowed_pgid=None):
 result=[]
 for r in rows:
  if not is_vendor(r) or (allowed_pgid is not None and r['pgid']==allowed_pgid):continue
  item={k:r[k] for k in ('pid','comm','ppid','pgid','state','startticks')}
  item['executable']=r.get('argv',[''])[0] if r.get('argv') else None
  item['argv_sha256']=hashlib.sha256('\0'.join(r.get('argv',[])).encode()).hexdigest();result.append(item)
 return result
def empty_inventory():
 rows=vendor_inventory(process_rows());
 if rows:raise Deferred('global vendor/launcher inventory busy: '+json.dumps(rows,sort_keys=True))
 return dict(utc=utc(),vendor_processes=[])
def validate_ack(record,identity,admission_sha,claim=None):
 for k in ('hostname','pid','startticks','pgid','nonce'):
  require(record.get(k)==identity[k],'ROOT ownership receipt identity changed '+k)
 require(record.get('admission_sha256')==admission_sha and record.get('linux_claim_state')=='ACK','ROOT Linux CAD claim revoked/changed')
 if claim is not None:require(record.get('linux_claim')==claim,'current ACK Linux claim changed')
 require(record.get('basis')=='coordinator conditional release + ROOT perVM onejobprotocol','ownership basis changed')

def analyze(folder,arm):
 for name in ['loaded-constraints.xdc','design-properties.tsv','input-utilization.rpt','post-opt-utilization.rpt','placed-utilization.rpt','placed-flat-utilization.rpt','control-sets.rpt','timing-summary.rpt','timing-paths.rpt','occupied-sites.tsv','slice-summary.tsv','placed.dcp']:
  require((folder/name).is_file() and (folder/name).stat().st_size>0,'required placed artifact '+name)
 vals={x.split('\t')[0]:int(x.split('\t')[1]) for x in (folder/'slice-summary.tsv').read_text().splitlines()}
 sites={x.split('\t')[0]:x.split('\t')[1] for x in (folder/'occupied-sites.tsv').read_text().splitlines()[1:]}
 require(vals['SLICEL']==sum(t=='SLICEL' for t in sites.values()) and vals['SLICEM']==sum(t=='SLICEM' for t in sites.values()) and vals['total']==vals['SLICEL']+vals['SLICEM']>0,'actual unique occupied-site counts')
 log=(folder/'console.log').read_text();require(log.count('CSR_COMPONENT_PACKING_COMPLETE '+arm)==1 and 'ACTUAL_TOOL_VERSION 2024.2' in log and 'ACTUAL_MAX_THREADS 2' in log,'placed complete/version marker')
 return dict(occupied_slices=vals,scope='Default-opt/place isolated OOC component actual sites/estimated timing only; no route, wholeCPU subtraction, or physical/application claim')

def validate_inputs(a,sha,allow_pending=False):
 require(bind(DRAFT if allow_pending else A)['sha256']==sha,'exact selected admission')
 require(a['schema']=='csr-component-packing-v1' and a['settings']==SETTINGS and a['cases']==CASES,'fixed source/strategy/twoDCP arms')
 for r in a['inputs']:require(bind(r['path'])==r,'bound input drift')
 if not allow_pending:
  draft=json.loads(DRAFT.read_text());require(a.get('immutable_draft')==bind(DRAFT),'immutable draft')
  draft.update(launchable=True,ROOT_terminal_release=a['ROOT_terminal_release'],resource_profile=a['resource_profile'],immutable_draft=bind(DRAFT))
  require(a==draft,'promotion may add only exact release/profile bindings')
  require(a['launchable'] and a['ROOT_terminal_release'] is not None and a['resource_profile'] is not None,'ROOT release/resource missing')
  for r in [a['ROOT_terminal_release'],a['resource_profile']]:require(bind(r['path'])==r,'ROOT release/resource drift')
  release=json.loads(Path(a['ROOT_terminal_release']['path']).read_text())
  require(release.get('allow_component_packing') is True and release.get('prior_mapping05_terminal_sha256')=='2ed7df458f1be2da9033a41da2d0a294047f56054b0b9183ac8d73bfd4020a85','closed05 and ROOT packing admission')
  profile=json.loads(Path(a['resource_profile']['path']).read_text())
  require(profile.get('schema')=='csr-component-packing-resource-v1' and profile.get('all_other_charged_reserves_included') is True and len(profile.get('basis_records',[]))>0,'explicit complete global reserve profile')
  for r in profile['basis_records']:require(bind(r['path'])==r,'resource basis drift')
  for k in ['other_HOME_bytes','other_RUN_bytes','other_SHM_bytes']:require(type(profile[k]) is int and profile[k]>=0,'nonnegative separately charged reserves')
 require(a['limits']==dict(per_arm_native_seconds=580,per_arm_parent_seconds=600,batch_seconds=1250,fresh_RUN_stage_bytes=CAP,new_HOME_source_durable_bytes=HOME_CAP,HOME_floor_bytes=FLOOR,RUN_floor_bytes=RAM_FLOOR,SHM_floor_bytes=SHM_FLOOR,attempts_per_arm=1,retries=0,extensions=0),'fixed caps')
 require(a['ownership']['basis']=='coordinator conditional release + ROOT perVM onejobprotocol','perVM basis')

def budget(profile=None):
 used=usage(FAMILY);home=usage(HOME_FAMILY)
 require(used<=CAP and home<=HOME_CAP,'new RUN256MiB/HOME8MiB cap')
 other=profile or dict(other_HOME_bytes=0,other_RUN_bytes=0,other_SHM_bytes=0)
 require(shutil.disk_usage('/run/user/1001').free>=RAM_FLOOR+CAP-used+other['other_RUN_bytes'],'1GiB RUNfloor+remaining256MiB+ALLotherRUNcharges')
 require(shutil.disk_usage('/dev/shm').free>=SHM_FLOOR+other['other_SHM_bytes'],'512MiB SHMfloor+ALLotherSHMcharges')
 require(shutil.disk_usage(HERE).free>=FLOOR+HOME_CAP-home+other['other_HOME_bytes'],'2.5GiB HOMEfloor+remaining8MiB+ALLotherHOMEcharges')
 return dict(RUN_bytes=used,HOME_bytes=home,profile_applied=profile is not None)

def extract_inputs(a):
 dest=FAMILY/'inputs';dest.mkdir()
 for arm in CASES:
  r=a['DCP_inputs'][arm]
  require(bind(r['archive']['path'])==r['archive'],'source archive')
  with tarfile.open(r['archive']['path'],'r:gz') as arc:
   raw=arc.extractfile(r['member']).read()
  require(len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'],'exact source DCP')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   xml=z.read('dcp.xml').decode();require('<OutOfContext Name="1"/>' in xml and '<DisableAutoIOBuffers Name="1"/>' in xml and '<Part Name="xc7z020clg400-1"/>' in xml,'actual OOC/part metadata')
  (dest/(arm+'.dcp')).write_bytes(raw)

def vendor_command(arm):
 require(arm in CASES,'fixed packing arm')
 return [str(WRAPPER),'-mode','batch','-source',str(HERE/'pack.tcl'),'-log','vivado.log','-journal','vivado.jou','-tclargs',arm,str(FAMILY/'inputs'/(arm+'.dcp'))]

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--inventory',action='store_true');parser.add_argument('--preflight',action='store_true');parser.add_argument('--admission-sha256');args=parser.parse_args()
 require(sum([args.execute,args.inventory,args.preflight])==1,'one explicit action')
 selected=DRAFT if args.preflight else A
 a=json.loads(selected.read_text());sha=bind(selected)['sha256'];validate_inputs(a,args.admission_sha256 or sha,allow_pending=args.preflight)
 if args.preflight:
  print(json.dumps(dict(state='SOURCE CHECKED; GLOBAL RESERVE PROFILE PENDING; no vendor',local_only_budget=budget(),admission_sha256=sha,launchable=a['launchable']),indent=2));return
 if args.inventory:
  print(json.dumps(dict(hostname=socket.gethostname(),utc=utc(),vendor_inventory=vendor_inventory(process_rows()),basis=a['ownership']['basis']),indent=2));return
 require(args.admission_sha256==sha,'execute needs exact reviewed SHA')
 require(socket.gethostname()==a['target_hostname'],'wrong actual VM hostname')
 require(bind(WRAPPER)['sha256']==a['tool_wrapper']['sha256'],'actual tool wrapper source')
 require(not OUT.exists(),'fresh one-shot remote output')
 # This read/publish protocol is deliberately not described as an atomic lock.
 # A concurrent appearance is detected while running and aborts only our PG.
 try:initial=empty_inventory()
 except Deferred as e:
  print(json.dumps(dict(state='DEFER before any vendor launch',hostname=socket.gethostname(),admission_sha256=sha,reason=str(e),vendor_attempts=0),sort_keys=True),flush=True);raise SystemExit(75)
 profile=json.loads(Path(a['resource_profile']['path']).read_text());budget(profile);require(not FAMILY.exists(),'fresh packing stage only');FAMILY.mkdir();extract_inputs(a)
 OUT.mkdir();identity=stat_row(os.getpid());identity=dict(hostname=socket.gethostname(),pid=os.getpid(),startticks=identity['startticks'],pgid=os.getpgrp(),nonce=uuid.uuid4().hex)
 receipt=dict(schema='bp1-root-pervm-cad-ownership-receipt-v1',**identity,utc=utc(),admission_sha256=sha,linux_claim_state='ACK',linux_claim=a['ownership']['linux_claim'],basis=a['ownership']['basis'],all_vendor_inventory_empty=initial,atomic_global_lock=False)
 receipt_path=OUT/'ROOT-ownership.json';save(receipt_path,receipt);save(OUT/'ROOT-ownership-initial.json',receipt);print('ROOT_CAD_ACK '+json.dumps(receipt,sort_keys=True),flush=True)
 state=dict(state='RUNNING ROOT perVM mapping protocol',admission=bind(A),ownership_receipt=bind(OUT/'ROOT-ownership-initial.json'),ownership_current_path=str(receipt_path),ownership_identity=identity,arms=[],foreign_inventory_events=[],no_board_operations=True)
 started=time.monotonic();active=None;arm_armed=False
 def interrupted(sig,frame):raise RuntimeError('ROOT worker signal '+str(sig))
 for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,interrupted)
 def guard():
  nonlocal active
  require(time.monotonic()-started<1250,'fixed batch1250s deadline')
  budget(profile)
  require(bind(A)['sha256']==sha,'reviewed admission changed during acquisition')
  validate_ack(json.loads(receipt_path.read_text()),identity,sha,a['ownership']['linux_claim'])
  rows=process_rows()
  if arm_armed and active is None:
   children=[r for r in rows if r['ppid']==os.getpid() and r['pgid']==r['pid']]
   require(len(children)<=1,'unexpected simultaneous ROOT child groups')
   if children:active={k:children[0][k] for k in ('pid','pgid','startticks')}
  leader=next((r for r in rows if active and r['pid']==active['pid'] and r['startticks']==active['startticks']),None)
  allowed=active['pgid'] if leader else None
  foreign=vendor_inventory(rows,allowed)
  if foreign:
   state['foreign_inventory_events'].append(dict(utc=utc(),rows=foreign))
   if active is None:raise Deferred('foreign owner/job before owned vendor group creation; no new launch')
   raise ForeignJob('foreign vendor/launcher appeared; stop only ownedPG')
 try:
  for arm in CASES:
   validate_inputs(a,sha);guard();idle=empty_inventory()
   folder=OUT/arm;folder.mkdir();row=dict(arm=arm,prelaunch_global_idle=idle,argv=vendor_command(arm));state['arms'].append(row);save(OUT/'session.json',state)
   active=None;arm_armed=True
   def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP))
   with (folder/'console.log').open('wb') as log:
    try:row['owned_receipt']=owned.run(row['argv'],folder,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,580,guard,limits)
    except BaseException as e:row['owned_receipt']=getattr(e,'owned_receipt',dict(owned_pgid=None,returncode=None,failure=repr(e),owned_group_remaining=False,scope='prePopen refusal'));raise
   arm_armed=False
   require(row['owned_receipt']['returncode']==0,'native Vivado arm failed')
   if active:require(row['owned_receipt']['owned_pgid']==active['pgid'],'discovered owner group differs from actual lifecycle')
   active=None;guard();empty_inventory();row['analysis']=analyze(folder,arm)
   row['artifacts']=[bind(p) for p in sorted(folder.rglob('*')) if p.is_file()];save(OUT/'session.json',state)
  validate_inputs(a,sha);guard();state['state']='PASS matched isolated OOC component Default packing; no wholeCPU/fit or mapped-function claim'
 except BaseException as e:
  state.update(state='DEFERRED/ABORTED preserved; no retries or foreign signaling',error=repr(e));raise
 finally:
  for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,signal.SIG_IGN)
  arm_armed=False
  try:
   validate_inputs(a,sha);require(bind(WRAPPER)['sha256']==a['tool_wrapper']['sha256'],'tool wrapper drift');
   for arm in CASES:
    r=a['DCP_inputs'][arm];require(bind(FAMILY/'inputs'/(arm+'.dcp'))['sha256']==r['sha256'],'staged DCP changed')
   state['source_endcheck']='PASS'
  except BaseException as e:state.update(state='FAIL source-endcheck, preserved',source_endcheck_error=repr(e))
  remaining=any(r.get('owned_receipt',{}).get('owned_group_remaining',False) for r in state['arms'])
  if active and owned.group_state(active['pgid']):remaining=True
  final=dict(receipt,linux_claim_state='HELD_OWNED_GROUP_REMAINS' if remaining else 'RELEASED',release_utc=utc(),outcome=state['state'],owned_group_remaining=remaining)
  # Never replace a receipt that someone else revoked or reassigned.
  try:
   current=json.loads(receipt_path.read_text())
   if all(current.get(k)==identity[k] for k in identity) and current.get('linux_claim_state')=='ACK':save(receipt_path,final)
   else:save(OUT/'ROOT-ownership-final.json',final)
  except BaseException as e:state['ownership_release_error']=repr(e)
  if remaining:state['state']='FAIL owned group remains; CAD claim HELD, not released'
  state.update(elapsed_seconds=time.monotonic()-started,ownership_final=final)
  save(OUT/'session.json',state);print(state['state'],flush=True)
  if not state['state'].startswith('PASS matched isolated OOC component Default packing'):raise SystemExit(1)
if __name__=='__main__':main()
