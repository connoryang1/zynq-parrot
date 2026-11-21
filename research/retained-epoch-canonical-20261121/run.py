#!/usr/bin/env python3
"""Fixed small HOME component miter. No full-core, vendor, network or FPGA calls."""
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import time

HERE=Path(__file__).resolve().parent;SRC=HERE/'source';CAP=64*1024**2;RESERVE=3*1024**3
VERILATOR=Path('/home/coyang/zynq-parrot/install/bin/verilator')

def bind(path):
 p=Path(path);raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def require(ok,message):
 if not ok:raise ValueError(message)
def guard():
 used=sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())
 require(used<=CAP,'fixed64MiB artifact cap')
 require(shutil.disk_usage(HERE).free>=RESERVE+CAP-used,'3GiB plus remaining artifact reserve')
 return used

def run(argv,cwd,log,timeout,expected_failure=False):
 guard();start=time.monotonic();process=None
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(12*1024**2,12*1024**2))
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(HERE/'tmp'))
 try:
  with log.open('wb') as stream:
   process=subprocess.Popen(list(map(str,argv)),cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
   while process.poll() is None:
    guard();require(time.monotonic()-start<timeout,'fixed component deadline');time.sleep(.1)
  rc=process.returncode
  require((rc!=0) if expected_failure else (rc==0),'component command failed: '+str(log))
  return dict(argv=list(map(str,argv)),cwd=str(cwd),returncode=rc,seconds=time.monotonic()-start,log=bind(log))
 finally:
  if process is not None:
   try:os.killpg(process.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   process.wait(timeout=5)

def main():
 require(not (HERE/'session.json').exists(),'preserve prior fixed component attempt')
 (HERE/'tmp').mkdir(exist_ok=False)
 sources=[bind(p) for p in sorted(SRC.iterdir()) if p.is_file()]+[bind(Path(__file__).resolve())]
 state=dict(state='RUNNING-component-only',sources=sources,commands=[],budget=dict(total_bytes=CAP,reserve_bytes=RESERVE,build_seconds=300,run_seconds=120),runs=[])
 def save():(HERE/'session.json').write_text(json.dumps(state,indent=2)+'\n')
 save()
 try:
  for name,iset,dset,sets,epoch,negative in [('actual1792',1792,1792,256,8,False),('small-fallback',93,131,256,2,False),('negative-clear0',1792,1792,256,8,True)]:
   out=HERE/name;out.mkdir();ram=SRC/'bp_retained_epoch_ram.sv'
   if negative:
    bad=out/'bp_retained_epoch_ram.sv';text=ram.read_text();require(text.count('if (write_v_i)')==1,'negative mutation anchor');bad.write_text(text.replace('if (write_v_i)',"if (write_v_i && write_addr_i != '0)"));ram=bad;state['negative_source']=bind(bad)
   args=[VERILATOR,'--cc','--exe','--build','--trace-fst','--assert','-Wall','-DBP_RETAINED_METADATA_VERIFY','--top-module','retained_metadata_wrapper',
         '-GI_LINES='+str(iset),'-GD_LINES='+str(dset),'-GRETAINED_SETS='+str(sets),'-GEPOCH_WIDTH='+str(epoch),
         '-CFLAGS','-std=c++14','-j','1','-MAKEFLAGS','VM_PARALLEL_BUILDS=0','--Mdir',out/'obj',
         ram,SRC/'bp_retained_line_store.sv',SRC/'bp_retained_line_store_reference.sv',SRC/'retained_metadata_wrapper.sv',SRC/'driver.cpp']
   state['commands'].append(run(args,out,out/'build.log',300));save()
   exe=out/'obj/Vretained_metadata_wrapper';state.setdefault('executables',{})[name]=bind(exe)
   for mode in (('inverted',) if negative else ('inverted','different-periods')):
    runtime=out/mode;runtime.mkdir();entry=run([exe]+([] if mode=='inverted' else [mode]),runtime,out/('run-'+mode+'.log'),120,negative)
    text=(out/('run-'+mode+'.log')).read_text()
    if negative:require('cycle/payload/RAM-port miter mismatch' in text and 'RETAINED_METADATA_MITER_PASS' not in text,'negative must fail actual miter')
    else:require(text.count('RETAINED_METADATA_MITER_PASS ')==1 and text.count('RETAINED_METADATA_HAZARDS_PASS ')==1 and text.count('RETAINED_TEST_EXIT_CLEAN')==1,'complete miter/hazard/clean markers')
    entry.update(case=name,mode=mode,expected_rejection=negative,fst=bind(runtime/'retained-line-store.fst'));state['runs'].append(entry);save()
  require(sources==[bind(p) for p in sorted(SRC.iterdir()) if p.is_file()]+[bind(Path(__file__).resolve())],'frozen component source drift')
  state.update(state='PASS-component-cycle512b-all-epoch-cells-coherence-plus-negative',artifact_bytes=guard())
 except BaseException as error:state.update(state='FAIL-preserved-component-attempt',error=repr(error));raise
 finally:save();print(HERE/'session.json',state['state'],flush=True)

if __name__=='__main__':main()
