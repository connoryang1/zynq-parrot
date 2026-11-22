import argparse,hashlib,importlib.util,json,os,resource,shutil,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
CWD=Path('/home/coyang/zynq-parrot-linux-host-observer/research/retained-parser-schema-cache-preparation02-20261122')
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
owned=load('host_owned','/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-allslots-delta-preparation-20261122/software_owned_v2.py')
watch=load('host_watch','/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-allslots-preparation02-20261122/process_monitor.py')
def need(x,m):
 if not x:raise ValueError(m)
def allocated(root):
 root=Path(root)
 if not root.exists():return 0
 stack=[root];seen=set();total=0
 while stack:
  p=stack.pop()
  try:
   st=p.lstat()
   if (st.st_dev,st.st_ino) in seen:continue
   seen.add((st.st_dev,st.st_ino));total+=st.st_blocks*512
   if p.is_dir() and not p.is_symlink():stack.extend(p.iterdir())
  except FileNotFoundError:pass
 return total
def bind(p):
 p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def main():
 a=argparse.ArgumentParser();a.add_argument('phase',choices=['unit','replay']);a.add_argument('--release');a.add_argument('--release-sha256');a.add_argument('--policy-sha256',required=True);a.add_argument('--self-sha256',required=True);x=a.parse_args()
 need(bind(__file__)['sha256']==x.self_sha256,'ROOT guard source drift');need(bind(HERE/'resources.json')['sha256']==x.policy_sha256,'ROOT policy drift');p=json.loads((HERE/'resources.json').read_text());start=time.monotonic()
 need(os.stat('/run/user/1001').st_dev!=os.stat(HERE).st_dev!=os.stat('/dev/shm').st_dev,'admitted three separate volumes')
 out=Path(p['test_output']); deadline=30 if x.phase=='unit' else 1280
 def check():
  used=allocated(out);w=allocated(p['work']);e=sum(allocated(r) for r in p['evidence_roots']);own=allocated(HERE)
  need(used<=p['test_cap'] and w<=p['work_cap'] and e<=p['evidence_cap'],'test/currentCAD caps');need(own<=p['own_HOME_helper_and_proof_cap'],'ROOT own HOME cap')
  rn=p['RUN_floor']+p['work_cap']-w+p['other_RUN']+p['test_cap']-used
  hn=p['HOME_floor']+p['evidence_cap']-e+p['other_HOME']+2*131072
  sn=p['SHM_floor']+p['other_SHM']
  free=dict(RUN=shutil.disk_usage('/run/user/1001').free,HOME=shutil.disk_usage(HERE).free,SHM=shutil.disk_usage('/dev/shm').free)
  need(free['RUN']>=rn and free['HOME']>=hn and free['SHM']>=sn,'three volume floors plus all current/future OTHER and new test')
  mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'));need(mem>=p['memory_floor']+p['encoder_extra_RAM_reserve'],'extra1GiB AS plus1GiB memory floor')
  need(time.monotonic()-start<deadline+5,'owned outer deadline+teardown')
  return dict(mutable_output_bytes=used,CAD_work_allocated=w,CAD_evidence_allocated=e,free=free,required=dict(RUN=rn,HOME=hn,SHM=sn))
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024**2,32*1024**2))
 need(not (HERE/(x.phase+'-owned.json')).exists(),'fresh no-retry phase')
 before=check();(HERE/(x.phase+'-preflight.json')).write_text(json.dumps(dict(policy=bind(HERE/'resources.json'),source=bind(__file__),resources=before,owned=bind(owned.__file__),watch=bind(watch.__file__)),indent=2)+'\n')
 argv=[sys.executable,'-B','-m','unittest','-v','test_schema_cache'] if x.phase=='unit' else [sys.executable,'-B','profile_replay.py','--plan-sha256','68450038454a0d12dd81460e4613cbc7267f79e5eb8b0d1a324864ef31e684f8','--release',x.release,'--release-sha256',x.release_sha256,'--execute']
 life=None
 try:
  with watch.phase(check,HERE/(x.phase+'-watch.json')) as guard:
   with (HERE/(x.phase+'.log')).open('wb') as log:life=owned.run(argv,CWD,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,deadline,guard,limits)
  need(life['returncode']==0 and life['failure'] is None and not life['owned_group_remaining'],'owned phase PASS')
 except BaseException as ex:
  life=life or getattr(ex,'owned_receipt',None);(HERE/(x.phase+'-owned.json')).write_text(json.dumps(dict(state='FAIL preserved',error=repr(ex),life=life),indent=2)+'\n');raise
 (HERE/(x.phase+'-owned.json')).write_text(json.dumps(dict(state='PASS bounded host phase',life=life,log=bind(HERE/(x.phase+'.log')),watch=bind(HERE/(x.phase+'-watch.json'))),indent=2)+'\n');print('PASS',x.phase)
if __name__=='__main__':main()
