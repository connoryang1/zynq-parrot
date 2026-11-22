#!/usr/bin/env python3
"""One unchanged offline HP0 audit, with owned process-group/resource bounds."""
import hashlib,json,os,resource,shutil,signal,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent
A=R/'admission.DRAFT.json'
T=Path('/dev/shm/retained-canonical-hp0-N40-helper-20261121-01')
COHORT=R.parent
CC=128*1024**2
HC=32*1024**2; RC=64*1024**2; HR=3*1024**3; RR=1024**3
class Stopped(RuntimeError):pass
def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def verify(x):
 if isinstance(x,dict):
  if {'path','bytes','sha256'}<=set(x):
   b=bind(x['path']);require(b=={k:x[k] for k in b},'input changed '+x['path'])
  for v in x.values():verify(v)
 elif isinstance(x,list):
  for v in x:verify(v)
def size(p):return sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) if p.exists() else 0
def stop(sig,frame):raise Stopped('caught signal '+str(sig))
def limits():
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(HC,HC))
def cleanup(p):
 end=time.monotonic()+5
 try:os.killpg(p.pid,signal.SIGTERM)
 except ProcessLookupError:pass
 try:p.wait(timeout=min(2,max(.001,end-time.monotonic())))
 except subprocess.TimeoutExpired:pass
 try:os.killpg(p.pid,signal.SIGKILL)
 except ProcessLookupError:pass
 p.wait(timeout=max(.001,end-time.monotonic()))
 while True:
  try:os.killpg(p.pid,0)
  except ProcessLookupError:break
  require(time.monotonic()<end,'owned group not gone within5s');time.sleep(.01)
def discover(p,owned):
 for q in Path('/proc').glob('[0-9]*'):
  try:
   fields=(q/'stat').read_text().rsplit(') ',1)[1].split()
   if int(fields[2])!=p.pid:continue
   for arg in (q/'cmdline').read_bytes().decode(errors='replace').split('\0'):
    if arg.startswith('/dev/shm/hp0-closed-fst-'):
     d=Path('/dev/shm')/arg.split('/')[3]
     if d.exists():
      st=d.stat();identity=(st.st_dev,st.st_ino);require(not d.is_symlink(),'helper symlink');require(d not in owned or owned[d]==identity,'helper identity drift');owned[d]=identity
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass

def main():
 require(bind(A)['sha256']=='1ca549f921b9935cc5ab9f4d5623a15d75d50104e117263fcff754a1da7e914a','admission pin')
 a=json.loads(A.read_text());verify(a);require(not (R/'audit01').exists() and not T.exists(),'fresh only')
 require(not (R/'root-session.json').exists(),'one attempt only')
 require(Path('/dev/shm/zp-linux-canonical-fulltop-20261121-01').is_dir(),'actual host namespace')
 require(size(COHORT)+HC-size(R)<=CC-65536,'full N40 allocation cannot fit128MiB')
 require(shutil.disk_usage(R).free>=HR+HC and shutil.disk_usage('/dev/shm').free>=RR+RC,'initial reserves')
 T.mkdir();owned={T:(T.stat().st_dev,T.stat().st_ino)};p=None;start=time.monotonic();state=dict(state='RUNNING one closed-trace audit',admission=bind(A),guard=bind(__file__),argv=a['argv'],board_actions=0,model_executions=0)
 (R/'root-admission.json').write_text(json.dumps(state,indent=2)+'\n')
 def guard():
  if p is not None:discover(p,owned)
  used=size(R);ram=sum(size(d) for d in owned)
  require(size(COHORT)<=CC-65536,'TOTAL existing N40 durable+new audit128MiB cap')
  require(used<=HC-65536 and ram<=RC,'fixed output/helper cap')
  require(shutil.disk_usage(R).free>=HR+HC-used,'HOME3GiB+remaining reserve')
  require(shutil.disk_usage('/dev/shm').free>=RR+RC-ram,'RAM1GiB+remaining-helper reserve')
  require(time.monotonic()-start<780,'fixed780s outer deadline')
 try:
  guard();env=dict(os.environ);env.update(a['environment']);env['PYTHONDONTWRITEBYTECODE']='1'
  with (R/'root-console.log').open('wb') as log:
   p=subprocess.Popen(a['argv'],stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True,preexec_fn=limits)
   state['owned_pgid']=p.pid
   while p.poll() is None:guard();time.sleep(.25)
   guard();require(p.returncode==0,'unchanged flow failed');verify(a)
   proof=json.loads((R/'audit01/verification.json').read_text());require(proof['accepted'] is True,'closed audit not accepted')
   state.update(state='PASS one unchanged canonical1792 N40 positive107 closed-trace HP0 audit',returncode=p.returncode,proof=bind(R/'audit01/verification.json'))
 except BaseException as e:state.update(state='FAIL preserved; no retry/extension',error=repr(e));raise
 finally:
  for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,signal.SIG_IGN)
  if p is not None:cleanup(p)
  state.update(elapsed_seconds=time.monotonic()-start,HOME_bytes=size(R),helper_bytes=sum(size(d) for d in owned),helper_dirs={str(k):v for k,v in owned.items()},owned_group_remaining=False)
  (R/'root-session.json').write_text(json.dumps(state,indent=2)+'\n');print(state['state'],flush=True)
if __name__=='__main__':
 for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
 main()
