#!/usr/bin/env python3
"""ROOT-only single saved-ExploreArea placement follow-up; no optimization or synthesis."""
import argparse,hashlib,json,os,resource,shutil,signal,socket,time,uuid,zipfile
from pathlib import Path
import software_owned_v2 as owned
import ownership as own
HERE=Path(__file__).resolve().parent
SOURCE_FAMILY_BYTES=96*1024
CASES=['area1-placement-followup']
CAPS=dict(work_bytes=512*1024**2,durable_HOME_bytes=192*1024**2,HOME_floor_bytes=1879048192,RUN_floor_bytes=1024**3,SHM_floor_bytes=512*1024**2,logging_future_bytes=128*1024**2,MemAvailable_bytes=8*1024**3,AS_bytes=16*1024**3,batch_seconds=3660)
PHASES=dict(open=240,inspect=240,place=1800,physopt=180,route=900,postroute=180,reports=240,complete=180)
def need(v,m):
 if not v:raise ValueError(m)
def bind(p):
 p=Path(p);h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())
def save(p,q):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(q,indent=2)+'\n');t.replace(p)
def size(p):
 if not p.exists():return 0
 ss=[f.lstat() for f in p.rglob('*') if f.is_file() or f.is_symlink()]
 return max(sum(s.st_size for s in ss),sum(s.st_blocks*512 for s in ss))
def validate(a,row):
 need(a['schema']=='csr-post-synth-area-controls06-placement-v1' and a['ROOT_approved'] is True,'ROOT exact fresh approval required')
 need(a['source_family_cap_bytes']==SOURCE_FAMILY_BYTES,'fresh06 prospective96KiB source/admission/proof cap')
 need(a['caps']==CAPS and a['case_order']==CASES and a['phase_seconds']==PHASES,'fixed prospective order/bounds')
 need(a['TOP']=='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd' and a['BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','same frozen source')
 need(a['synth']['bytes']==81450048 and a['synth']['sha256']=='d5eeec325c1a5cbb67fcddb6445080a5042552ab00b2c3a4151f1c12be729755','exact frozen SYN')
 need(a['implementation_entry']['bytes']==22723303 and a['implementation_entry']['sha256']=='36b4f91831db0f967514046b9a0936be043ac7a0a9bf26f8287c361c623815e1','exact unoptimized implementation input')
 need(a['baseline_optimized']['bytes']==22392783 and a['baseline_optimized']['sha256']=='ba2f65800371130fc5c0699dfe093ca864db1141b2cf91e7c82b24956495bc30','same existing Explore baseline')
 need(a['clock_policy']['sha256']=='6dfc1df776c7686f519e2be825f0aba98bb03a5ea32a88cb587a027722701ea0' and a['clock_qualification_closure']['sha256']=='f19f5019830d49b30c6d45746c798c506c9bc31b4a529fd616e4f80f64970a6e','exact ROOT observed clock policy/closed proof')
 need(a['host_python']=={'path': '/usr/bin/python3', 'bytes': 5490456, 'sha256': '298a9e830ed52f36c299427565485d717d1ce0179c0597cc16560513eb780b06'} and a['host_env']=={'path': '/usr/bin/env', 'bytes': 43352, 'sha256': '5f7c7882898e9e280e93579b459e22b339c4f38cfd54a05b46b81dfb60c557cc'},'exact host Python/env identities for isolated coverage invocation')
 need(isinstance(a['replaced_controls03_closure'],dict),'ROOT closed controls03 future0 receipt required')
 need(a['resume_checkpoint']=={'path': '/run/user/1001/zp-csr256-post-synth-area-controls04-20261122-01/area1/optimized.dcp', 'bytes': 22360663, 'sha256': 'c95cdf978a14c16c42b3d514310f402a9c313bc5f6293b1c9b58fed654d52f8f'} and a['resume_opt_table']=={'path': '/run/user/1001/zp-csr256-post-synth-area-controls04-20261122-01/area1/opt/clock-sinks.tsv', 'bytes': 7857884, 'sha256': '6231021a97db06a78a9e09c5607b4fdc1d0a30d99516f026557420fb1215962a'} and a['resume_opt_coverage']=={'path': '/run/user/1001/zp-csr256-post-synth-area-controls04-20261122-01/area1/opt/coverage-gate.json', 'bytes': 636, 'sha256': 'e9eb22e87565fac59920dfe9c191e0cc806dc38d58c6bd2ab1fab7fe909d3e03'},'exact saved ExploreArea checkpoint/qualified opt table/coverage')
 need(isinstance(a['replaced_controls04_closure'],dict),'ROOT closed controls04 future0 receipt required')
 need(isinstance(a['replaced_controls05_closure'],dict),'ROOT closed controls05 future0 receipt required')
 previous=json.loads(Path(a['resume_opt_coverage']['path']).read_text());need(previous['state']=='PASS' and previous['policy_sha256']==a['clock_policy']['sha256'],'actual prior opt coverage PASS')
 for r in a['inputs']+[a['clock_policy'],a['clock_qualification_closure'],a['host_python'],a['host_env'],a['replaced_controls03_closure'],a['replaced_controls04_closure'],a['replaced_controls05_closure'],a['resume_checkpoint'],a['resume_opt_table'],a['resume_opt_coverage']]+[a['synth'],a['implementation_entry'],a['baseline_optimized'],a['tool_wrapper']]:need(bind(r['path'])==r,'exact frozen source/checkpoint '+r['path'])
 need(a['resources']['ROOT_approved'] is True and a['resources']['all_OTHER_and_current_reservations_included'] is True,'fresh fully priced resource record')
 need(a['ownership']['basis']=='coordinator conditional release + ROOT perVM onejobprotocol','unchanged perVM ownership basis')
def budget(a,w):
 need(size(HERE)<=SOURCE_FAMILY_BYTES,'fresh06 full source/admission/proof family exceeds96KiB')
 used=size(w);r=a['resources'];need(used<=CAPS['work_bytes'],'own512MiB work cap')
 need(shutil.disk_usage(w.parent).free>=CAPS['RUN_floor_bytes']+max(0,CAPS['work_bytes']-used)+r['OTHER_RUN_bytes'],'RUN floor/full remaining/OTHER')
 need(shutil.disk_usage(HERE).free>=CAPS['HOME_floor_bytes']+CAPS['logging_future_bytes']+CAPS['durable_HOME_bytes']+r['OTHER_HOME_bytes'],'HOME floor/logging/future durable/OTHER')
 need(shutil.disk_usage('/dev/shm').free>=CAPS['SHM_floor_bytes']+r['OTHER_SHM_bytes'],'SHM existing reserves')
 mem=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'));need(mem>=CAPS['MemAvailable_bytes'],'8GiB physical memory headroom')
 return dict(work_allocated=used,MemAvailable=mem)
def checkpoint_evidence(row,folder,entry):
 result=[]
 with zipfile.ZipFile(row['path']) as z:
  infos=z.infolist();xdc=[(i,x) for i,x in enumerate(infos) if x.filename.lower().endswith('.xdc')]
  if entry:need(sorted(x.file_size for i,x in xdc)==[2269,35754,57210,72855],'exact four implementation-input embeddedXDC sizes')
  need(xdc,'checkpoint has no embedded constraints')
  d=folder/'embedded-constraints';d.mkdir()
  for i,x in xdc:
   data=z.read(x.filename);dest=d/('%03d-'%i+Path(x.filename).name);dest.write_bytes(data);result.append(dict(zip_index=i,zip_member=x.filename,stored=bind(dest)))
  # Archive order is recorded, not relabeled as scope/processing order. Preserve
  # all XML metadata so native checkpoint constraint scoping/order is retained.
  metadata=[]
  for i,x in enumerate(infos):
   if x.filename.lower().endswith('.xml'):
    dest=d/('metadata-%03d-'%i+Path(x.filename).name);dest.write_bytes(z.read(x.filename));metadata.append(dict(zip_index=i,zip_member=x.filename,stored=bind(dest)))
 save(folder/'embedded-constraint-evidence.json',dict(input_checkpoint=row,XDC_archive_order=result,scope_and_processing_order_metadata=metadata,no_constraint_creation=True))
 return dict(XDC_entries=len(xdc),evidence=bind(folder/'embedded-constraint-evidence.json'))
def analyze(folder,arm,baseline):
 result=dict(line.split('\t',1) for line in (folder/'result.tsv').read_text().splitlines())
 need(result['arm']==arm and result['result'] in ['PLACE_FAILED','ROUTED_REQUIRES_ROOT_ACCEPTANCE_AND_CLEAN_REBUILD'],'exact fixed completed control')
 stages=['input']+(['placed','routed'] if result['result'].startswith('ROUTED') else ['place-failed'])
 gates=[]
 for stage in stages:
  gate=json.loads((folder/stage/'coverage-gate.json').read_text());need(gate['state']=='PASS','classified clock gate missing');gates.append(gate)
 return dict(result=result['result'],metrics=dict(line.split('\t',1) for line in (folder/'input-metrics.tsv').read_text().splitlines()),coverage=gates,scope='No fit/timing/functional acceptance; clean rebuild and ROOT final gates required')
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--admission',type=Path,required=True);ap.add_argument('--admission-sha256',required=True);ap.add_argument('--execute',action='store_true');x=ap.parse_args();row=bind(x.admission);need(row['sha256']==x.admission_sha256 and x.execute,'exact ROOT execute admission');a=json.loads(x.admission.read_text());validate(a,row)
 need(socket.gethostname()==a['target_hostname'],'exact bp1 host');w=Path(a['work']);need(w.parent.is_dir() and not w.exists(),'ROOT-created parent/fresh one-shot work');initial=own.empty_inventory();budget(a,w)
 w.mkdir();(w/'tmp').mkdir();identity=own.stat_row(os.getpid());identity=dict(hostname=socket.gethostname(),pid=os.getpid(),startticks=identity['startticks'],pgid=os.getpgrp(),nonce=uuid.uuid4().hex)
 receipt=dict(schema='bp1-root-pervm-cad-ownership-receipt-v1',**identity,utc=own.utc(),admission_sha256=row['sha256'],linux_claim_state='ACK',linux_claim=a['ownership']['linux_claim'],basis=a['ownership']['basis'],all_vendor_inventory_empty=initial,atomic_global_lock=False)
 rp=w/'ROOT-ownership.json';save(rp,receipt);save(w/'ROOT-ownership-initial.json',receipt);print('ROOT_CAD_ACK '+json.dumps(receipt),flush=True)
 state=dict(state='RUNNING one saved-ExploreArea placement follow-up',admission=row,ownership_identity=identity,arms=[],foreign_inventory_events=[],no_frontend_synthesis=True,no_board_operations=True);started=time.monotonic();active=None;armed=False;folder=None;snapshots={}
 for k in ['synth','implementation_entry','baseline_optimized','resume_checkpoint']:
  s=Path(a[k]['path']).stat();snapshots[k]=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 def interrupted(sig,frame):raise RuntimeError('ROOT worker interrupted '+str(sig))
 for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,interrupted)
 def guard():
  nonlocal active
  need(time.monotonic()-started<CAPS['batch_seconds'],'fixed3660s batch');budget(a,w);need(bind(x.admission)==row,'admission drift');own.validate_ack(json.loads(rp.read_text()),identity,row['sha256'],a['ownership']['linux_claim'])
  for k,expected in snapshots.items():
   s=Path(a[k]['path']).stat();need((s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)==expected,'input checkpoint metadata drift')
  rows=own.process_rows()
  if armed and active is None:
   children=[p for p in rows if p['ppid']==os.getpid() and p['pgid']==p['pid']];need(len(children)<=1,'unexpected simultaneous child groups')
   if children:active={k:children[0][k] for k in ['pid','pgid','startticks']}
  leader=next((p for p in rows if active and p['pid']==active['pid'] and p['startticks']==active['startticks']),None);foreign=own.vendor_inventory(rows,active['pgid'] if leader else None)
  if foreign:state['foreign_inventory_events'].append(dict(utc=own.utc(),processes=foreign))
  need(not foreign,'foreign vendor/launcher; abort only own PG')
  p=folder/'progress.json' if folder else None
  if armed and p and p.is_file():
   q=json.loads(p.read_text())
   need(q['phase'] in PHASES and time.time()-q['started_epoch']<PHASES[q['phase']]+2,'fixed phase observation timeout')
 try:
  for arm in CASES:
   validate(a,row);guard();idle=own.empty_inventory();folder=w/arm;folder.mkdir();active=None;armed=True
   source=a['resume_checkpoint'];argv=[a['tool_wrapper']['path'],'-log',str(folder/'vivado.log'),'-journal',str(folder/'vivado.jou'),'-source',str(HERE/'probe.tcl'),'-tclargs',arm,source['path'],a['clock_policy']['path']]
   item=dict(arm=arm,prelaunch_idle=idle,argv=argv,embedded_constraints=checkpoint_evidence(source,folder,False));state['arms'].append(item);save(w/'session.json',state)
   def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(CAPS['AS_bytes'],CAPS['AS_bytes']));resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,512*1024**2))
   try:
    with (folder/'console.log').open('wb') as log:item['ownership']=owned.run(argv,folder,dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(w/'tmp')),log,3600,guard,limits)
   except BaseException as e:item['ownership']=getattr(e,'owned_receipt',None);raise
   armed=False;need(item['ownership']['returncode']==0 and item['ownership']['failure'] is None and not item['ownership']['owned_group_remaining'],'native phase/tool/cleanup failure, preserve and stop')
   if active:need(item['ownership']['owned_pgid']==active['pgid'],'discovered child ownership mismatch')
   active=None;guard();own.empty_inventory();item['analysis']=analyze(folder,arm,None if arm=='baseline' else w/'baseline');item['artifacts']=[bind(p) for p in sorted(folder.rglob('*')) if p.is_file()];save(w/'session.json',state)
  guard();state['state']='PASS closed single placement follow-up; inspect outcome, no fit acceptance'
 except BaseException as e:state.update(state='FAIL/DEFER preserved; no retries or foreign signaling',error=repr(e));raise
 finally:
  for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,signal.SIG_IGN)
  armed=False
  try:validate(a,row);state['source_and_DCP_endcheck']='PASS'
  except BaseException as e:state.update(state='FAIL source/checkpoint endcheck',end_error=repr(e))
  remains=any(z.get('ownership',{}).get('owned_group_remaining',False) for z in state['arms'] if z.get('ownership')) or bool(active and owned.group_state(active['pgid']))
  state['global_vendor_at_end']=own.vendor_inventory(own.process_rows())
  if state['global_vendor_at_end']:state['state']='FAIL/DEFER vendor still present at closure; no foreign signaling'
  final=dict(receipt,linux_claim_state='HELD_OWNED_GROUP_REMAINS' if remains else 'RELEASED',release_utc=own.utc(),outcome=state['state'],owned_group_remaining=remains)
  try:
   current=json.loads(rp.read_text())
   if all(current.get(k)==identity[k] for k in identity) and current.get('linux_claim_state')=='ACK':save(rp,final)
   else:save(w/'ROOT-ownership-final.json',final)
  except BaseException as e:state['release_error']=repr(e)
  state.update(elapsed_seconds=time.monotonic()-started,ownership_final=final);save(w/'session.json',state)
  print(state['state'],flush=True)
  if remains or not state['state'].startswith('PASS closed'):raise SystemExit(1)
if __name__=='__main__':main()
