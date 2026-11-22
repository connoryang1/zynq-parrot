#!/usr/bin/env python3
"""ROOT per-VM one-job CAD worker, never an atomic/global lock or board owner."""
import argparse,collections,datetime,hashlib,json,os,re,resource,shutil,signal,socket,sys,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
FAMILY=Path('/dev/shm/zp-csr-snapshot-production-contract-20261122-01')
OUT=FAMILY/'mapping02'
A=HERE/'admission.json'
WRAPPER=Path('/home/coyang/zynq-parrot/codex-skills/bp-fpga-synthesis/scripts/run_vivado_2024_2.sh')
CAP=64*1024**2
FLOOR=2684354560
HOME_CAP=8*1024**2
HOME_FAMILY=HERE.parent
RAM_FLOOR=512*1024**2
CASES=['baseline-single-source','resetless-single']
SETTINGS=dict(top='csr_snapshot_consumer_wrapper',consumer='exact cache/resident restore selection and reset-priority full-image envelope',device='xc7z020clg400-1',Vivado='2024.2',max_threads=2,contexts=4,image_bits=1666,producer_gates='exact complementary T/notT same current owner',data='common save-bank-selected wire',read_ports=1,valid_vector_bits=4,clock_period_ns=50,clock_waveform_ns=[0,25],input_output_delay_ns=0,synthesis_directive='AreaOptimized_high',global_retiming='on',control_set_opt_threshold=1,out_of_context=True,implementation_or_route=False)
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
 require(not (folder/'blackboxes.txt').read_text().strip(),'synthesis blackbox')
 clocks=(folder/'clocks.tsv').read_text().splitlines()
 require(clocks==['owning_clock\t50.000\t{0.000 25.000}'] or (len(clocks)==1 and clocks[0].split('\t')[0]=='owning_clock' and [float(x) for x in clocks[0].split('\t')[1:2]]==[50.0] and [float(x) for x in clocks[0].split('\t')[2].strip('{}').split()]==[0.0,25.0]),'actual owning50nsclock')
 for f in ['ports.tsv','payload-drivers.tsv','utilization.rpt','timing-summary.rpt','timing-paths.rpt','control-sets.rpt','primitives.tsv','storage-properties.tsv','used-ref-properties.tsv','synthesized.dcp','functional.v']:
  require((folder/f).is_file() and (folder/f).stat().st_size>0,'required artifact '+f)
 ports={row.split('\t')[0]:int(row.split('\t')[2]) for row in (folder/'ports.tsv').read_text().splitlines()[1:]}
 require(ports.get('restored_image_o')==1666 and ports.get('prior_image_i')==1666 and ports.get('restore_v_o')==1 and ports.get('restore_reset_o')==1 and ports.get('valid_vector_o')==4 and ports.get('bank0_data_i')==1666 and ports.get('bank1_data_i')==1666 and len(ports)==28,'all exact live interface widths')
 text=(folder/'utilization.rpt').read_text();m=re.search(r'^\| csr_snapshot_consumer_wrapper\s*\|\s*\(top\)\s*\|([^\n]+)\|$',text,re.M);require(m is not None,'exact resource row')
 v=[int(x.strip().replace(',','')) for x in m[1].split('|')];require(len(v)==8,'eight resource columns')
 resources=dict(zip(['LUT','logic_LUT','LUTRAM','SRL','FF','RAMB36','RAMB18','DSP'],v))
 log=(folder/'console.log').read_text();require(log.count('CSR_SNAPSHOT_MAPPING_COMPLETE '+arm)==1 and 'ACTUAL_TOOL_VERSION 2024.2' in log and 'ACTUAL_MAX_THREADS 2' in log,'native complete settings')
 return dict(resources=resources,scope='standalone post-synthesis component resource/timing; no mapped functional, routed, fullCPU, or removable whole-device saving claim')

def validate_inputs(a,sha,allow_pending=False):
 require(bind(A)['sha256']==sha,'exact ROOT-reviewed admission')
 require(a['schema']=='csr-snapshot-consumer-mapping-v2' and a['settings']==SETTINGS,'fixed source/settings schema')
 require(a['cases']==CASES,'fixed matched two arms only')
 if not allow_pending:
  require(a['launchable'] is True and a['ROOT_terminal_release'] is not None,'current wholeCAD terminal release required; draft cannot launch')
  r=a['ROOT_terminal_release'];require(bind(r['path'])==r,'exact ROOT terminal/release binding')
  release=json.loads(Path(r['path']).read_text())
  require(release.get('current_CAD_job')=='20261122T084853Z-1008854d3' and release.get('terminal_verified') is True and release.get('allow_component_mapping') is True,'explicit ROOT terminal/release, not implicit idle')
 for r in a['inputs']:require(bind(r['path'])==r,'frozen matched producer-consumer source/functional input drift')
 gate=json.loads(Path(a['component_gate']['path']).read_text())
 require(bind(a['component_gate']['path'])==a['component_gate'] and gate['state'].startswith('PASS production-contract component') and len(gate['cases'])==2,'actual completed exact source component gate')
 require(len(gate['commands'])==6 and all(x['owned']['returncode']==0 and not x['owned']['owned_group_remaining'] for x in gate['commands']),'all component commands and own groups complete')
 require(a['ownership']['basis']=='coordinator conditional release + ROOT perVM onejobprotocol','perVM basis')
 require(a['limits']==dict(per_arm_native_seconds=580,per_arm_parent_seconds=600,batch_seconds=1250,shared_component_stage_bytes=CAP,new_HOME_source_durable_bytes=HOME_CAP,HOME_floor_bytes=FLOOR,RAM_floor_bytes=RAM_FLOOR,attempts_per_arm=1,retries=0,extensions=0),'fixed prospective limits')

def budget():
 used=usage(FAMILY);home=usage(HOME_FAMILY)
 require(sum(x.stat().st_size for x in FAMILY.rglob('*.fst'))<=4*1024**2,'original component aggregate FST cap')
 require(used<=CAP and home<=HOME_CAP,'shared component64MiB or newHOME8MiB cap')
 require(shutil.disk_usage('/dev/shm').free>=RAM_FLOOR+CAP-used,'512MiB RAM floor plus shared stage remaining')
 require(shutil.disk_usage(HERE).free>=FLOOR+HOME_CAP-home,'active2.5GiB HOME floor plus8MiB evidence remaining')
 return dict(shared_component_stage_bytes=used,new_HOME_bytes=home)

def vendor_command(arm):
 require(arm in CASES,'fixed vendor arm')
 # -tclargs consumes all following arguments, so it must be LAST.
 return [str(WRAPPER),'-mode','batch','-source',str(HERE/'probe.tcl'),'-log','vivado.log','-journal','vivado.jou','-tclargs',arm]

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--inventory',action='store_true');parser.add_argument('--preflight',action='store_true');parser.add_argument('--admission-sha256');args=parser.parse_args()
 require(sum([args.execute,args.inventory,args.preflight])==1,'one explicit action')
 a=json.loads(A.read_text());sha=bind(A)['sha256'];validate_inputs(a,args.admission_sha256 or sha,allow_pending=args.preflight)
 if args.preflight:
  print(json.dumps(dict(state='PASS source and prospective local resource preflight only; no vendor',budget=budget(),admission_sha256=sha,launchable=a['launchable']),indent=2));return
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
 budget();require(FAMILY.is_dir(),'existing ROOT component stage required')
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
  budget()
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
  validate_inputs(a,sha);guard();state['state']='PASS matched CSR snapshot component mapping; no wholeCPU/fit or mapped-function claim'
 except BaseException as e:
  state.update(state='DEFERRED/ABORTED preserved; no retries or foreign signaling',error=repr(e));raise
 finally:
  for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,signal.SIG_IGN)
  arm_armed=False
  try:
   validate_inputs(a,sha);require(bind(WRAPPER)['sha256']==a['tool_wrapper']['sha256'],'tool wrapper drift');state['source_endcheck']='PASS'
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
if __name__=='__main__':main()
