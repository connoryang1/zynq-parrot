#!/usr/bin/env python3
"""ROOT-only postroute tag timing replay; default unadmitted source plan only."""
import argparse,hashlib,importlib.util,json,os,re,resource,shutil,signal,socket,sys,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PLAN=HERE/'plan.json';FINAL=HERE/'admission.FINAL.json'
RUN=Path('/run/user/1001/zp-tag-postroute-sta-replay-20261123-01')
CLAIM='ONE postroute50ns conservative tag-clock STA diagnostic; no implementation/hold-exception change'
HELD_JOB='20261123T060312Z-1b24c915e'
def require(ok,message):
 if not ok:raise RuntimeError(message)
def bind(p):
 p=Path(p);h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())
def verify(r):require(bind(r['path'])==r,'byte identity drift '+r['path'])
def module(name,row):
 verify(row);s=importlib.util.spec_from_file_location(name,row['path']);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def usage(p):
 if not p.exists():return 0
 ss=[f.lstat()for f in p.rglob('*')if f.is_file()or f.is_symlink()]
 return max(sum(s.st_size for s in ss),sum(s.st_blocks*512 for s in ss))
def stamp(p):
 s=Path(p).stat();return [s.st_dev,s.st_ino,s.st_size,s.st_ctime_ns,s.st_mtime_ns]
def load(sha,execute):
 p=json.loads(PLAN.read_text());require(p['schema']=='tag-postroute-sta-plan-v1'and p['stage']==str(RUN)and p['linux_claim']==CLAIM,'fixed scope')
 for r in p['inputs']:verify(r)
 require(bind(Path(__file__))in p['inputs'],'actual runner pin')
 verify(p['policy']);require(p['policy']['sha256']=='6dfc1df776c7686f519e2be825f0aba98bb03a5ea32a88cb587a027722701ea0','exact observed policy')
 if not execute:return p,None
 require(sha and bind(FINAL)['sha256']==sha,'ROOT exact FINAL SHA')
 f=json.loads(FINAL.read_text());require(f['schema']=='tag-postroute-sta-admission-v1'and f['launchable']is True,'NULL/unadmitted cannot launch')
 require(f['source_plan']==bind(PLAN)and f['limits']==p['limits']and f['linux_claim']==CLAIM,'exact plan/caps/claim')
 verify(f['ROOT_release']);r=json.loads(Path(f['ROOT_release']['path']).read_text())
 require(r.get('allow_tag_postroute_sta')is True and r.get('source_plan')==bind(PLAN)and r.get('linux_claim')==CLAIM,'explicit ROOT query release')
 require(r.get('held_CAD_job')==HELD_JOB and r.get('held_CAD_builder_released')is True,'current768 CAD must close before query')
 verify(r['held_CAD_terminal_proof'])
 o=f['fixed_OTHER_reservations'];require(set(o)=={'RUN_bytes','HOME_bytes','SHM_bytes'}and all(type(v)is int and v>=0 for v in o.values()),'all other reservations priced')
 require(r.get('fixed_OTHER_reservations')==o and r.get('all_existing_future_caps_priced')is True,'release same conservative resource sum')
 selection=f['routed_selection'];verify(f['ROOT_routed_binding']);binding=json.loads(Path(f['ROOT_routed_binding']['path']).read_text())
 require(binding.get('ROOT_approved') is True and binding.get('routed_selection')==selection
         and binding.get('completed_route') is True and binding.get('final_postroute_physical_state') is True, 'ROOT exact final postroute-physical/source binding')
 profile=selection['profile'];require(profile in ('csr256','csr768'),'two fixed source profiles only');require(selection['checkpoint_stage']=='final_postroute_physopt','never select intermediate routed checkpoint')
 expected=dict(p['fixed_geometry']);expected.update(retained_I_lines=256 if profile=='csr256' else 768,retained_D_lines=256 if profile=='csr256' else 768)
 require(selection['geometry']==expected and selection['BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','no geometry/policy/BP relaxation')
 require(re.fullmatch(r'[0-9a-f]{40}',selection['TOP'])is not None,'full TOP identity, no prefix admission')
 require(re.fullmatch(r'[0-9a-f]{64}',selection['DCP']['sha256'])is not None and selection['DCP']['bytes']>0 and Path(selection['DCP']['path']).is_absolute(),'explicit ROOT full DCP binding')
 if profile=='csr256':
  require(selection['TOP']=='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd'and selection['DCP']==p['known32_DCP'],'exact existing32 route')
 else:
  require(selection['job_id']==HELD_JOB and binding.get('same_final_physical_state_as_BIT') is True,'exact current96 final physical state used for BIT')
  verify(binding['BIT_artifact'])
 verify(binding['terminal_proof'])
 p['DCP']=selection['DCP'];p['selected_source']=selection
 require(socket.gethostname()==p['target_hostname'],'actual bp1 host')
 return p,f

def budget(p,f):
 z=p['limits'];run=usage(RUN);home=usage(HERE)
 extra=0 if HERE in Path(f['ROOT_release']['path']).resolve().parents else f['ROOT_release']['bytes']
 require(home+extra<=z['source_bytes']and home+extra<=z['HOME_bytes'],'source64KiB/wholeHOME8MiB')
 require(run<=z['RUN_bytes'],'wholeRUN64MiB')
 q=RUN/'query';output=sum(x.stat().st_size for x in q.iterdir()if x.is_file())if q.exists()else 0
 require(output<=z['report_bytes'],'reports/logs8MiB; all other scratch stays charged in64MiB')
 o=f['fixed_OTHER_reservations']
 require(len({Path(x).stat().st_dev for x in (str(HERE),str(RUN.parent),'/dev/shm')})==3,'separate observed volumes; no reserve borrowing')
 require(shutil.disk_usage(RUN.parent).free>=z['RUN_floor_bytes']+z['RUN_bytes']-run+o['RUN_bytes'],'RUN floor/remaining64/OTHER')
 require(shutil.disk_usage(HERE).free>=z['HOME_floor_bytes']+z['HOME_bytes']-home-extra+o['HOME_bytes'],'HOME floor/remaining8/OTHER including logging')
 require(shutil.disk_usage('/dev/shm').free>=z['SHM_floor_bytes']+o['SHM_bytes'],'SHM floor/OTHER')
 mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines()if l.startswith('MemAvailable:'));require(mem>=z['MemAvailable_bytes'],'8GiB host memory floor')
 return dict(RUN_bytes=run,HOME_bytes=home,report_bytes=output,MemAvailable_bytes=mem)

def clock_rows(path):
 rows={}
 for l in path.read_text().splitlines()[1:]:
  n,period,wave,generated,sources=l.split('\t');require(n not in rows,'unique clock');rows[n]=dict(period=float(period),waveform=[float(v)for v in wave.strip('{}').split()],generated=int(generated),sources=sources)
 return rows
def xdc_commands(text):
 result=[];pending=''
 for line in text.splitlines(keepends=True):
  pending+=line
  if line.rstrip().endswith('\\'):continue
  result.append(pending);pending=''
 require(not pending,'complete exported XDC command');return result
def analyze(p,folder):
 names=['before-clocks.tsv','after-clocks.tsv','before-constraints.xdc','after-constraints.xdc','tag-polarity-before.tsv','tag-coverage-after.tsv','serializer-source-properties.tsv','before-route.rpt','after-route.rpt','before-no-clock.rpt','before-unconstrained.rpt','after-no-clock.rpt','after-unconstrained.rpt','full-check-timing.rpt','timing.rpt','setup-recovery.rpt','hold-removal.rpt','asynchronous-recovery.rpt','asynchronous-removal.rpt','async-targets.tsv','serializer-to-tag-max.rpt','serializer-to-tag-min.rpt','tag-internal-max.rpt','tag-internal-min.rpt','original-to-tag-max.rpt','original-to-tag-min.rpt','tag-to-original-max.rpt','tag-to-original-min.rpt','endpoint-paths.tsv','cdc.rpt','drc.rpt','drc-severity.tsv','console.log','vivado.log','vivado.jou']
 require(all((folder/n).is_file()for n in names),'complete replay reports preserved')
 log=(folder/'console.log').read_text();require(len(re.findall(r'(?m)^TAG_STA_TOOL 2024\.2 THREADS 8\s*$',log))==1 and log.count('TAG_STA_COLLECTION_COMPLETE clocks_added=1 tag_sinks=42 original_endpoints=76; ROOT_REVIEW_REQUIRED')==1,'actual2024.2 and terminal')
 before=clock_rows(folder/'before-clocks.tsv');after=clock_rows(folder/'after-clocks.tsv');require(before==p['expected_clocks'],'same five original clocks before model')
 require(set(after)==set(before)|{'tag_conservative50'}and all(after[n]==r for n,r in before.items()),'original clocks unchanged; only one clock added')
 require(after['tag_conservative50']['period']==50 and after['tag_conservative50']['generated']==1,'actual source-derived50ns conservative envelope')
 b=(folder/'before-constraints.xdc').read_text();cmds=xdc_commands((folder/'after-constraints.xdc').read_text());new=[c for c in cmds if c.lstrip().startswith('create_generated_clock')and'tag_conservative50'in c]
 require(len(new)==1,'one new generated-clock command');require(''.join(c for c in cmds if c not in new)==b,'all original exported constraints/scopes/exceptions byte-preserved; no extra exceptions')
 pol=json.loads(Path(p['policy']['path']).read_text())
 for filename,key in [('before-no-clock.rpt','exact_tag_no_clock_pins'),('before-unconstrained.rpt','exact_tag_unconstrained_pins')]:
  actual=[l.strip()for l in(folder/filename).read_text().splitlines()if l.startswith('black_parrot_bd_1_i/')];require(len(actual)==len(set(actual))and set(actual)==set(pol[key]),'independent exact prior42/76')
 no_clock=(folder/'after-no-clock.rpt').read_text();unconstrained=(folder/'after-unconstrained.rpt').read_text()
 coverage=('There are 0 register/latch pins with no clock'in no_clock and 'There are 0 pins that are not constrained for maximum delay.'in unconstrained)
 text=(folder/'timing.rpt').read_text();section=text.split('| Design Timing Summary',1)[-1].split('| Clock Summary',1)[0];numeric=[]
 for line in section.splitlines():
  values=line.split()
  if len(values)==12 and all(re.fullmatch(r'[-+]?(?:\d+\.?\d*|\.\d+)',v)for v in values):numeric.append([float(v)for v in values])
 metrics=None
 if len(numeric)==1:metrics=dict(zip(['WNS','TNS','setup_failing','setup_total','WHS','THS','hold_failing','hold_total','WPWS','TPWS','pulse_failing','pulse_total'],numeric[0]))
 numbers_pass=bool(metrics and all(metrics[k]>=0 for k in ('WNS','WHS','WPWS'))and all(metrics[k]==0 for k in ('TNS','THS','TPWS','setup_failing','hold_failing','pulse_failing')))
 drc=[l.split('\t',1)for l in(folder/'drc-severity.tsv').read_text().splitlines()[1:]]
 return dict(result='DIAGNOSTIC_COLLECTED_REQUIRES_ROOT_CDC_RESET_HOLD_REVIEW',selected_source=p['selected_source'],all_prior_constraints_preserved=True,tag42_clocked=True,unexplained_coverage_zero=coverage,timing_metrics=metrics,numeric_setup_hold_pulse_pass=numbers_pass,DRC_severities=drc,qualified=False,reason='No automatic hold/source-on-fall or CDC/reset waiver; actual violations and missing path rows require review',artifacts=[bind(folder/n)for n in names])

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');ap.add_argument('--admission-sha256');a=ap.parse_args();p,f=load(a.admission_sha256,a.execute)
 if not a.execute:print(json.dumps(dict(state='UNADMITTED source-only; no runtime or inventory',source_plan=bind(PLAN),limits=p['limits'])));return
 verify(p['DCP']);before=stamp(p['DCP']['path'])
 owned=module('software_owned_v2',p['owned']);q=module('tag_query_qualified_worker',p['qualified']);require(q.owned is owned,'exact qualified ownership helper')
 require(not RUN.exists(),'fresh one-shot namespace only');idle=q.empty_inventory();initial=budget(p,f);RUN.mkdir();folder=RUN/'query';folder.mkdir();(RUN/'tmp').mkdir()
 ident=dict(hostname=socket.gethostname(),pid=os.getpid(),pgid=os.getpgrp(),startticks=q.stat_row(os.getpid())['startticks'],nonce=uuid.uuid4().hex)
 rec=dict(schema='bp1-root-pervm-cad-ownership-receipt-v1',**ident,admission_sha256=a.admission_sha256,linux_claim_state='ACK',linux_claim=CLAIM,basis='coordinator conditional release + ROOT perVM onejobprotocol',atomic_global_lock=False,initial_idle=idle)
 ack=RUN/'ROOT-ownership.json';q.save(ack,rec);q.save(RUN/'ROOT-ownership-initial.json',rec)
 state=dict(state='RUNNING source-derived clock STA replay only',admission=bind(FINAL),initial_resources=initial,DCP_initial_stamp=before,command=None,exactly_one_conservative_generated_clock=True,no_synth_opt_place_route=True,no_board=True);active=None;armed=False;started=time.monotonic()
 def guard():
  nonlocal active
  require(time.monotonic()-started<330,'fixed330s owner');budget(p,f);require(bind(FINAL)['sha256']==a.admission_sha256,'FINAL unchanged');require(stamp(p['DCP']['path'])==before,'exact input identity unchanged')
  q.validate_ack(json.loads(ack.read_text()),ident,a.admission_sha256,CLAIM);rows=q.process_rows()
  if armed and active is None:
   children=[r for r in rows if r['ppid']==os.getpid()and r['pgid']==r['pid']];require(len(children)<=1,'one owned child group')
   if children:active={k:children[0][k]for k in ('pid','pgid','startticks')}
  leader=next((r for r in rows if active and r['pid']==active['pid']and r['startticks']==active['startticks']),None)
  require(not q.vendor_inventory(rows,active['pgid']if leader else None),'foreign vendor/launcher including current768 CAD; stop only OWN group')
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(p['limits']['AS_bytes'],)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(p['limits']['RUN_bytes'],)*2)
 def interrupted(sig,frame):raise RuntimeError('ROOT query signal '+str(sig))
 for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,interrupted)
 try:
  load(a.admission_sha256,True);guard();q.empty_inventory();argv=[p['wrapper']['path'],'-mode','batch','-source',str(HERE/'replay.tcl'),'-log','vivado.log','-journal','vivado.jou','-tclargs',p['DCP']['path']]
  state['command']=dict(argv=argv,timeout_seconds=300,cwd=str(folder));q.save(RUN/'session.json',state);armed=True
  try:
   with (folder/'console.log').open('wb')as log:state['command']['owned']=owned.run(argv,folder,dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(RUN/'tmp')),log,300,guard,limits)
  except BaseException as e:state['command']['owned']=getattr(e,'owned_receipt',dict(failure=repr(e),owned_group_remaining=False));raise
  armed=False;o=state['command']['owned'];require(o['returncode']==0 and o['failure']is None and not o['owned_group_remaining'],'actual native0 and owned lifecycle')
  if active:require(o['owned_pgid']==active['pgid'],'actual child identity')
  active=None;guard();state['analysis']=analyze(p,folder);state['state']='PASS collected postroute tag STA diagnostic; NOT_TIMING_QUALIFIED; ROOT review required'
 except BaseException as e:state.update(state='FAIL/DEFER preserved; no retry/mutation/foreign signaling',error=repr(e));raise
 finally:
  for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,signal.SIG_IGN)
  armed=False
  try:load(a.admission_sha256,True);verify(p['DCP']);require(stamp(p['DCP']['path'])==before,'end input inode/ctime/mtime');state['source_DCP_endcheck']='PASS byte and identity unchanged'
  except BaseException as e:state.update(state='FAIL source/DCP endcheck',endcheck_error=repr(e))
  o=(state.get('command')or{}).get('owned',{});remaining=bool(active and owned.group_state(active['pgid']))or bool(o.get('owned_group_remaining',False))
  state['global_vendor_at_end']=q.vendor_inventory(q.process_rows())
  if remaining or state['global_vendor_at_end']:state['state']='FAIL/DEFER owned/global vendor absence not established'
  final=dict(rec,linux_claim_state='HELD_OWNED_GROUP_REMAINS'if remaining else'RELEASED',owned_group_remaining=remaining,outcome=state['state'])
  try:
   cur=json.loads(ack.read_text())
   if all(cur.get(k)==ident[k]for k in ident)and cur.get('linux_claim_state')=='ACK':q.save(ack,final)
   else:q.save(RUN/'ROOT-ownership-final.json',final)
  except BaseException as e:state['ownership_error']=repr(e);q.save(RUN/'ROOT-ownership-final.json',final)
  state.update(elapsed_seconds=time.monotonic()-started,ownership_final=final);q.save(RUN/'session.json',state)
 require(state['state'].startswith('PASS collected postroute'),'final diagnostic acceptance')
if __name__=='__main__':main()
