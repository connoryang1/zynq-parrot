#!/usr/bin/env python3
"""Negative-only bounded component continuation; no positive rerun/CAD/board/fullcore."""
import argparse,hashlib,json,os,shutil,signal,subprocess
from pathlib import Path
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
FAMILY=Path('/dev/shm/zp-csr-snapshot-dual-writer-20261122-01')
OUT=FAMILY/'negative-continuation02'
WORK=Path('/home/coyang/bp-csr-snapshot-dual-writer-20261122')
A=HERE/'negative-admission.json';R=HERE/'negative-receipt.json'
V=Path('/home/coyang/zynq-parrot/install/bin/verilator')
VR=Path('/home/coyang/zynq-parrot/install/share/verilator')
CAP=128*1024**2;FST_CAP=8*1024**2;HOME_CAP=128*1024;FLOOR=512*1024**2
state=None

def need(v,m):
 if not v:raise ValueError(m)
def bind(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def size(p):return sum(x.stat().st_size for x in p.rglob('*') if x.is_file()) if p.exists() else 0
def guard():
 used=size(FAMILY);tr=sum(p.stat().st_size for p in FAMILY.rglob('*.fst')) if FAMILY.exists() else 0;home=size(HERE)+size(WORK)
 need(used<=CAP and tr<=FST_CAP,'original aggregate128MiB/8MiB limits')
 need(home<=HOME_CAP,'original aggregate HOME128KiB limit')
 need(shutil.disk_usage('/dev/shm').free>=FLOOR+CAP-used,'512MiB RAM floor plus remaining family allocation')
 need(shutil.disk_usage(HERE).free>=2684354560+HOME_CAP-home,'active2.5GiB HOME floor plus remaining family allocation')
 return dict(stage_bytes=used,FST_bytes=tr,HOME_bytes=home)
def preflight():
 a=json.loads(A.read_text());need(a['schema']=='csr-snapshot-negative-only-continuation-v1','admission schema')
 need(a['output']==str(OUT) and a['limits']==dict(stage=CAP,FST=FST_CAP,HOME=HOME_CAP,workers=2,phase_seconds=120),'fixed output/limits')
 for r in a['inputs']:need(bind(r['path'])==r,'immutable input drift '+r['path'])
 old=json.loads((HERE/'receipt.json').read_text());c=old['commands']
 need(old['state'].startswith('FAIL') and len(c)==4 and len(old['cases'])==1,'preserve exact old incomplete family')
 need([x['owned']['returncode'] for x in c]==[0,0,0,1],'only negative generation failed')
 need(all(not x['owned']['owned_group_remaining'] for x in c),'old owned groups not closed')
 need('-Gnegative_p=1' in c[3]['argv'] and c[3]['argv'][0]==str(V),'failed negative generation identity')
 for r in a['positive_artifacts']+[x['log'] for x in c]:need(bind(r['path'])==r,'positive/failed immutable artifact drift')
 need('WIDTHTRUNC' in Path(c[3]['log']['path']).read_text(),'preserved exact warning failure')
 t=Path(c[2]['log']['path']).read_text();need('cycles=7234 all_context_checks=57868 width=1666 contexts=4 single_width=65' in t and t.count('CSR_SNAPSHOT_EXIT_CLEAN')==1,'closed positive markers')
 for src,dst in a['stage_source_pairs']:need(Path(src).read_bytes()==Path(dst).read_bytes(),'old compiled stage/source mismatch')
 return dict(admission=bind(A),inherited_positive=old['cases'][0],resources=guard())
def checkpoint():
 if state is not None:
  tmp=R.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(R)
def run(argv,cwd,log):
 row=dict(argv=[str(x) for x in argv],timeout_seconds=120);state['commands'].append(row);checkpoint()
 env=os.environ.copy();env.update(PATH='/usr/bin:/bin',VERILATOR_ROOT=str(VR),OBJCACHE='',CCACHE_DISABLE='1',SCCACHE_DISABLE='1',TMPDIR=str(FAMILY/'tmp'))
 for k in ['CC','CXX','AR','MAKE','CXXFLAGS','CPPFLAGS','LDFLAGS','MAKEFLAGS','MFLAGS']:env.pop(k,None)
 try:
  with log.open('wb') as f:row['owned']=owned.run(row['argv'],cwd,env,f,120,guard,lambda:dict(stage=CAP,FST=FST_CAP))
  need(row['owned']['returncode']==0,'negative continuation command failed')
 except BaseException as e:row.setdefault('owned',getattr(e,'owned_receipt',None));row['error']=repr(e);raise
 finally:row['log']=bind(log) if log.exists() else None;checkpoint()

def main():
 global state
 p=argparse.ArgumentParser();p.add_argument('--preflight',action='store_true');p.add_argument('--execute',action='store_true');args=p.parse_args();need(args.preflight!=args.execute,'choose action')
 proof=preflight()
 if args.preflight:print(json.dumps(proof,indent=2));return
 sentinel=Path('/dev/shm/zp-linux-borrow256-fpga-source-20261122-01');need((sentinel/'.git').is_dir(),'actual ROOT private-clone namespace')
 need(subprocess.check_output(['git','-C',str(sentinel),'rev-parse','HEAD'],text=True).strip()=='1008854d30e5d923c86c3232fc22af039467d552','exact sentinel HEAD')
 need(not OUT.exists() and not R.exists(),'one fresh negative-only attempt')
 guard();OUT.mkdir();src=FAMILY/'source';obj=OUT/'obj'
 state=dict(state='RUNNING negative only; original familyFAIL preserved',preflight=proof,commands=[]);checkpoint()
 def stop(sig,frame):raise RuntimeError('interrupted '+str(sig))
 for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,stop)
 try:
  run([V,'--cc','--exe','--trace-fst','--assert','-Wall','-Wno-DECLFILENAME','--top-module','csr_snapshot_wrapper',"-Gnegative_p=1'b1",'--Mdir',obj,'-CFLAGS','-std=c++14',src/'candidate.sv',src/'reference.sv',src/'wrapper.sv',src/'driver.cpp'],OUT,OUT/'generate.log')
  run(['make','-C',obj,'-f','Vcsr_snapshot_wrapper.mk','-f',src/'no-pch.mk','-j2','OBJCACHE='],OUT,OUT/'compile.log')
  need(not list(FAMILY.rglob('*.gch')),'unexpected PCH')
  exe=obj/'Vcsr_snapshot_wrapper';run([exe,'negative'],OUT,OUT/'runtime.log')
  t=(OUT/'runtime.log').read_text();need(t.count('CSR_SNAPSHOT_NEGATIVE_REJECTED')==1 and t.count('CSR_SNAPSHOT_EXIT_CLEAN')==1 and 'CSR_SNAPSHOT_FULL_IMAGE_PASS' not in t,'actual negative witness/clean exit')
  need((OUT/'snapshot.fst').stat().st_size>0,'negative trace missing')
  state['negative']=dict(executable=bind(exe),FST=bind(OUT/'snapshot.fst'))
  state['final_immutable_check']=preflight();need(bind(A)==state['preflight']['admission'],'admission drift');state['resources']=guard()
  state['state']='PASS composite inherited positive plus negative witness; original familyFAIL preserved; area/integration pending'
 except BaseException as e:state.update(state='FAIL negative continuation preserved; no retry',error=repr(e));raise
 finally:checkpoint();print(R,state['state'],flush=True)
if __name__=='__main__':main()
