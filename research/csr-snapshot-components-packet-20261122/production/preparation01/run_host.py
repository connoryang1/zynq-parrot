#!/usr/bin/env python3
"""Production-contract single-write component compilation/miter; no CAD/board/fullcore."""
import argparse,hashlib,json,os,shutil,signal,subprocess,time
from pathlib import Path
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
WORK=Path('/home/coyang/bp-csr-snapshot-production-contract-20261122')
STAGE=Path('/dev/shm/zp-csr-snapshot-production-contract-20261122-01')
V=Path('/home/coyang/zynq-parrot/install/bin/verilator')
VR=Path('/home/coyang/zynq-parrot/install/share/verilator')
CANDIDATE=WORK/'bp_be/src/v/bp_be_csr_snapshot_store_production.sv'
CAP=64*1024**2;TRACE=4*1024**2;HOME=96*1024;FLOOR=512*1024**2
BASE='bb575a764c200f07c6f3259a179bdc861dd7593f'
A=HERE/'admission.json';R=HERE/'receipt.json';state=None

def require(v,m):
 if not v:raise ValueError(m)
def bind(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def size(p):return sum(x.stat().st_size for x in p.rglob('*') if x.is_file()) if p.exists() else 0
def git(*args):return subprocess.check_output(['git','-C',str(WORK),*args],text=True).strip()
def guard():
 used=size(STAGE);tr=sum(x.stat().st_size for x in STAGE.rglob('*.fst')) if STAGE.exists() else 0
 home=size(HERE)+size(WORK)
 require(used<=CAP and tr<=TRACE,'total stage or aggregate FST allocation exceeded')
 require(home<=HOME,'complete source/helper/receipt family >96KiB')
 require(shutil.disk_usage('/dev/shm').free>=FLOOR+CAP-used,'512MiB floor plus remaining64MiB allocation')
 require(shutil.disk_usage(HERE).free>=2684354560+HOME-home,'active shared2.5GiB HOME floor plus remaining own allocation')
 return dict(stage_bytes=used,FST_bytes=tr,HOME_source_helper_receipt_bytes=home)
def checkpoint():
 if state is not None:
  tmp=R.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(R)
def preflight():
 a=json.loads(A.read_text());require(a['stage']==str(STAGE) and a['limits']==dict(stage=CAP,FST=TRACE,HOME=HOME,RAM_floor=FLOOR,workers=2,phase_seconds=120),'fixed allocations/phases')
 for r in a['inputs']:require(bind(r['path'])==r,'frozen input drift '+r['path'])
 require(git('rev-parse','HEAD')==BASE,'base/source drift')
 require(git('branch','--show-current')=='experiment/csr-snapshot-production-contract-20261122','dedicated branch')
 require((WORK/'.git').is_file() and V.is_file() and (VR/'include/verilated.h').is_file(),'real worktree/tools')
 return dict(admission=bind(A),resources=guard(),component_only=True)
def run(argv,cwd,log):
 row=dict(argv=[str(x) for x in argv],timeout_seconds=120);state['commands'].append(row);checkpoint()
 env=os.environ.copy();env.update(PATH='/usr/bin:/bin',VERILATOR_ROOT=str(VR),OBJCACHE='',CCACHE_DISABLE='1',SCCACHE_DISABLE='1',TMPDIR=str(STAGE/'tmp'))
 for k in ['CC','CXX','AR','MAKE','CXXFLAGS','CPPFLAGS','LDFLAGS','MAKEFLAGS','MFLAGS']:env.pop(k,None)
 try:
  with log.open('wb') as stream:row['owned']=owned.run(row['argv'],cwd,env,stream,120,guard,lambda:dict(stage_bytes=CAP,FST_bytes=TRACE))
  require(row['owned']['returncode']==0,'component command failed '+str(log))
 except BaseException as e:
  row.setdefault('owned',getattr(e,'owned_receipt',None));row['error']=repr(e);raise
 finally:
  row['log']=bind(log) if log.exists() else None;checkpoint()
 return row

def main():
 global state
 p=argparse.ArgumentParser();p.add_argument('--preflight',action='store_true');p.add_argument('--execute',action='store_true');args=p.parse_args();require(args.preflight!=args.execute,'choose one action')
 proof=preflight()
 if args.preflight:print(json.dumps(proof,indent=2));return
 # Host source sentinel: agent-private /dev/shm is never allocated by this helper.
 sentinel=Path('/dev/shm/zp-linux-borrow256-fpga-source-20261122-01')
 require((sentinel/'.git').is_dir(),'actual ROOT private-clone namespace required')
 require(subprocess.check_output(['git','-C',str(sentinel),'rev-parse','HEAD'],text=True).strip()=='1008854d30e5d923c86c3232fc22af039467d552','exact detached lower256 source HEAD required')
 require(subprocess.run(['git','-C',str(sentinel),'symbolic-ref','-q','HEAD'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==1,'lower256 source must remain detached')
 require(not STAGE.exists() and not R.exists(),'one fresh attempt only')
 guard();STAGE.mkdir();(STAGE/'tmp').mkdir();src=STAGE/'source';src.mkdir()
 shutil.copyfile(CANDIDATE,src/'candidate.sv')
 for f in ['reference.sv','wrapper.sv','driver.cpp','no-pch.mk']:shutil.copyfile(HERE/f,src/f)
 state=dict(state='RUNNING component-only',preflight=proof,commands=[],cases=[]);checkpoint()
 def stop(sig,frame):raise RuntimeError('interrupted '+str(sig))
 for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,stop)
 try:
  for name,neg in [('actual-raw-production-contract',0),('suppressed-write-negative',1)]:
   d=STAGE/name;d.mkdir();obj=d/'obj'
   run([V,'--cc','--exe','--trace-fst','--assert','-Wall','-Wno-DECLFILENAME','--top-module','csr_snapshot_production_wrapper',"-Gnegative_p=1'b"+str(neg),'--Mdir',obj,'-CFLAGS','-std=c++14',src/'candidate.sv',src/'reference.sv',src/'wrapper.sv',src/'driver.cpp'],d,d/'generate.log')
   run(['make','-C',obj,'-f','Vcsr_snapshot_production_wrapper.mk','-f',src/'no-pch.mk','-j2','OBJCACHE='],d,d/'compile.log')
   require(not list(STAGE.rglob('*.gch')),'unexpected PCH')
   exe=obj/'Vcsr_snapshot_production_wrapper';run([exe]+(['negative'] if neg else []),d,d/'runtime.log')
   t=(d/'runtime.log').read_text();require(t.count('CSR_PRODUCTION_EXIT_CLEAN')==1,'missing clean runtime closure')
   require(t.count('CSR_PRODUCTION_NEGATIVE_REJECTED' if neg else 'CSR_PRODUCTION_FULL_IMAGE_PASS')==1,'missing expected functional/witness marker')
   if not neg:require('cycles=22054 checks=176428 raw_combinations=8192 width=1666 contexts=4' in t,'complete fixed gate/bit/context coverage')
   require((d/'snapshot.fst').stat().st_size>0,'missing trace')
   state['cases'].append(dict(name=name,executable=bind(exe),FST=bind(d/'snapshot.fst')));guard();checkpoint()
  state['final_source_check']=preflight();require(bind(A)==state['preflight']['admission'],'admission drift');state['state']='PASS production-contract component independent raw gates/all-bit/all-context only; mapping/integration pending'
 except BaseException as e:state.update(state='FAIL preserved; no retry/extension/area claim',error=repr(e));raise
 finally:checkpoint();print(R,state['state'],flush=True)
if __name__=='__main__':main()
