#!/usr/bin/env python3
"""ROOT-only exact-route read-only tag-clock query; default source plan only."""
import argparse,hashlib,importlib.util,json,os,re,resource,shutil,signal,socket,sys,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PLAN=HERE/'plan.json';FINAL=HERE/'admission.FINAL.json'
RUN=Path('/run/user/1001/zp-csr256-routed-tag-query-20261123-01')
CLAIM='ONE read-only saved-route tag-clock42/endpoint76 query; no constraint/implementation mutation'
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
 p=json.loads(PLAN.read_text());require(p['schema']=='csr256-routed-tag-query-plan-v1'and p['stage']==str(RUN)and p['linux_claim']==CLAIM,'fixed scope')
 for r in p['inputs']:verify(r)
 require(bind(Path(__file__))in p['inputs'],'actual runner pin')
 verify(p['policy']);require(p['policy']['sha256']=='6dfc1df776c7686f519e2be825f0aba98bb03a5ea32a88cb587a027722701ea0','exact observed policy')
 require(p['DCP']['sha256']=='6c15bf5292a6757c3212fde0419299ba0c8b3028ee8af5fc580d6cc6ec255ab4'and p['DCP']['bytes']==37038288,'exact routed input')
 if not execute:return p,None
 require(sha and bind(FINAL)['sha256']==sha,'ROOT exact FINAL SHA')
 f=json.loads(FINAL.read_text());require(f['schema']=='csr256-routed-tag-query-admission-v1'and f['launchable']is True,'NULL/unadmitted cannot launch')
 require(f['source_plan']==bind(PLAN)and f['limits']==p['limits']and f['linux_claim']==CLAIM,'exact plan/caps/claim')
 verify(f['ROOT_release']);r=json.loads(Path(f['ROOT_release']['path']).read_text())
 require(r.get('allow_csr256_routed_tag_query')is True and r.get('source_plan')==bind(PLAN)and r.get('linux_claim')==CLAIM,'explicit ROOT query release')
 require(r.get('held_CAD_job')==HELD_JOB and r.get('held_CAD_builder_released')is True,'current768 CAD must close before query')
 verify(r['held_CAD_terminal_proof'])
 o=f['fixed_OTHER_reservations'];require(set(o)=={'RUN_bytes','HOME_bytes','SHM_bytes'}and all(type(v)is int and v>=0 for v in o.values()),'all other reservations priced')
 require(r.get('fixed_OTHER_reservations')==o and r.get('all_existing_future_caps_priced')is True,'release same conservative resource sum')
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

def analyze(p,folder):
 names=['clocks.tsv','clocks.rpt','existing-constraints.xdc','pin-domain-drivers.tsv','net-properties.tsv','cell-properties.tsv','endpoint-startpoints.tsv','root-and-crossing-fanout.tsv','no-clock.rpt','constant-clock.rpt','unconstrained.rpt','timing.rpt','result.tsv','console.log','vivado.log','vivado.jou']
 require(all((folder/n).is_file()for n in names),'complete narrow raw query outputs')
 result=(folder/'result.tsv').read_text();require(result=='result\tREAD_ONLY_TAG_QUERY_REQUIRES_ROOT_REVIEW\nclock_pins\t42\nendpoint_pins\t76\nconstraint_mutations\t0\n','exact read-only terminal')
 log=(folder/'console.log').read_text();require(len(re.findall(r'(?m)^TAG_QUERY_TOOL 2024\.2 THREADS 8\s*$',log))==1 and log.count('TAG_QUERY_COMPLETE exact_tag_clock_pins=42 exact_unconstrained=76 constraint_mutations=0')==1,'actual2024.2/8workers and terminal')
 clock={}
 for l in (folder/'clocks.tsv').read_text().splitlines()[1:]:
  n,period,wave,generated,sources=l.split('\t');require(n not in clock,'unique clock');clock[n]=dict(period=float(period),waveform=[float(v)for v in wave.strip('{}').split()],generated=int(generated),sources=sources)
 require(clock==p['expected_clocks'],'all five original clock identities unchanged; no tag clock created')
 pol=json.loads(Path(p['policy']['path']).read_text())
 for filename,key in [('no-clock.rpt','exact_tag_no_clock_pins'),('unconstrained.rpt','exact_tag_unconstrained_pins')]:
  lines=(folder/filename).read_text().splitlines();actual=[l.strip()for l in lines if l.startswith('black_parrot_bd_1_i/')];require(len(actual)==len(set(actual))and set(actual)==set(pol[key]),'exact existing exception set '+filename)
 rows=(folder/'pin-domain-drivers.tsv').read_text().splitlines();require(len(rows)==1+2+42+76,'exact root2/tag42/endpoint76 table')
 require('There are 0 register/latch pins with constant_clock.'in(folder/'constant-clock.rpt').read_text(),'no new constant-clock register classification')
 return dict(result='READ_ONLY_DIAGNOSTIC_REQUIRES_ROOT_REVIEW',tag_no_clock=42,unconstrained_endpoint_pins=76,original_clocks=5,no_constraint_mutations=True,no_new_timing_signoff=True,artifacts=[bind(folder/n)for n in names])

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');ap.add_argument('--admission-sha256');a=ap.parse_args();p,f=load(a.admission_sha256,a.execute)
 if not a.execute:print(json.dumps(dict(state='UNADMITTED source-only; no runtime or inventory',source_plan=bind(PLAN),limits=p['limits'])));return
 verify(p['DCP']);before=stamp(p['DCP']['path'])
 owned=module('software_owned_v2',p['owned']);q=module('tag_query_qualified_worker',p['qualified']);require(q.owned is owned,'exact qualified ownership helper')
 require(not RUN.exists(),'fresh one-shot namespace only');idle=q.empty_inventory();initial=budget(p,f);RUN.mkdir();folder=RUN/'query';folder.mkdir();(RUN/'tmp').mkdir()
 ident=dict(hostname=socket.gethostname(),pid=os.getpid(),pgid=os.getpgrp(),startticks=q.stat_row(os.getpid())['startticks'],nonce=uuid.uuid4().hex)
 rec=dict(schema='bp1-root-pervm-cad-ownership-receipt-v1',**ident,admission_sha256=a.admission_sha256,linux_claim_state='ACK',linux_claim=CLAIM,basis='coordinator conditional release + ROOT perVM onejobprotocol',atomic_global_lock=False,initial_idle=idle)
 ack=RUN/'ROOT-ownership.json';q.save(ack,rec);q.save(RUN/'ROOT-ownership-initial.json',rec)
 state=dict(state='RUNNING narrow read-only route query',admission=bind(FINAL),initial_resources=initial,DCP_initial_stamp=before,command=None,no_clock_mutation=True,no_synth_opt_place_route=True,no_board=True);active=None;armed=False;started=time.monotonic()
 def guard():
  nonlocal active
  require(time.monotonic()-started<270,'fixed270s owner');budget(p,f);require(bind(FINAL)['sha256']==a.admission_sha256,'FINAL unchanged');require(stamp(p['DCP']['path'])==before,'exact input identity unchanged')
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
  load(a.admission_sha256,True);guard();q.empty_inventory();argv=[p['wrapper']['path'],'-mode','batch','-source',str(HERE/'query.tcl'),'-log','vivado.log','-journal','vivado.jou','-tclargs',p['DCP']['path']]
  state['command']=dict(argv=argv,timeout_seconds=240,cwd=str(folder));q.save(RUN/'session.json',state);armed=True
  try:
   with (folder/'console.log').open('wb')as log:state['command']['owned']=owned.run(argv,folder,dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(RUN/'tmp')),log,240,guard,limits)
  except BaseException as e:state['command']['owned']=getattr(e,'owned_receipt',dict(failure=repr(e),owned_group_remaining=False));raise
  armed=False;o=state['command']['owned'];require(o['returncode']==0 and o['failure']is None and not o['owned_group_remaining'],'actual native0 and owned lifecycle')
  if active:require(o['owned_pgid']==active['pgid'],'actual child identity')
  active=None;guard();state['analysis']=analyze(p,folder);state['state']='PASS read-only exact-route tag diagnostic collected; ROOT timing-model review required'
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
 require(state['state'].startswith('PASS read-only'),'final diagnostic acceptance')
if __name__=='__main__':main()
