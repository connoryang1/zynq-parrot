#!/usr/bin/env python3
"""One clean, bounded standalone gate; no shared model, source, vendor or board."""
import argparse,hashlib,json,os,shutil,signal,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
VERILATOR=Path('/home/coyang/zynq-parrot/install/bin/verilator')
CAP=128*1024**2;TRACE_CAP=8*1024**2
SOURCES=('hp0_passive_read_timing_observer.sv','hp0_observer_tb_top.sv','driver.cpp','no-pch.mk','run_unit.py')
def bind(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def usage(p):return sum(x.stat().st_blocks*512 for x in p.rglob('*') if x.is_file())
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--stage',required=True,type=Path);ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
 stage=a.stage.resolve();out=a.out.resolve()
 if stage.exists() or out.exists() or str(stage.parent)!='/dev/shm':raise RuntimeError('fresh owned RAM stage and evidence output required')
 if shutil.disk_usage('/dev/shm').free<CAP+512*1024**2:raise RuntimeError('RAM stage plus512MiB floor unavailable')
 stage.mkdir();out.mkdir(parents=True);before=[bind(HERE/n) for n in SOURCES];peak=0;commands=[]
 for n in SOURCES:shutil.copyfile(HERE/n,stage/n)
 def guard():
  nonlocal peak
  family=list(stage.parent.glob(stage.name.rsplit('-',1)[0]+'-*'))
  used=sum(usage(p) for p in family if p.is_dir());peak=max(peak,used)
  if used>CAP:raise RuntimeError('128MiB stage cap')
  trace_total=sum(p.stat().st_size for d in family if d.is_dir() for p in d.glob('unit.fst'))
  if trace_total>TRACE_CAP:raise RuntimeError('8MiB family trace cap')
  if shutil.disk_usage('/dev/shm').free<512*1024**2+max(0,CAP-used):raise RuntimeError('RAM remaining-allocation reserve')
 def run(argv,log,deadline):
  guard();start=time.monotonic();p=None;failure=None
  with (out/log).open('wb') as stream:
   try:
    p=subprocess.Popen(argv,cwd=stage,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    while p.poll() is None:
     guard()
     if time.monotonic()-start>deadline:raise RuntimeError('fixed phase deadline')
     time.sleep(.1)
    guard()
    if p.returncode:raise RuntimeError('phase exit '+str(p.returncode))
   except BaseException as e:failure=repr(e);raise
   finally:
    if p is not None:
     try:os.killpg(p.pid,signal.SIGKILL)
     except ProcessLookupError:pass
     p.wait(timeout=5)
     try:os.killpg(p.pid,0);remaining=True
     except ProcessLookupError:remaining=False
     receipt=dict(argv=argv,returncode=p.returncode,failure=failure,owned_group_remaining=remaining,elapsed_s=time.monotonic()-start,deadline_s=deadline)
     commands.append(receipt);(out/(log+'.owned.json')).write_text(json.dumps(receipt,indent=2)+'\n')
     if remaining:raise RuntimeError('own process group remains')
 try:
  run([str(VERILATOR),'--cc','--exe','--trace-fst','--assert','--Wall','--top-module','hp0_observer_tb_top','--Mdir',str(stage/'obj'),'-CFLAGS','-std=c++17',str(stage/SOURCES[0]),str(stage/SOURCES[1]),str(stage/'driver.cpp')],'generate.log',60)
  run(['make','-C',str(stage/'obj'),'-f','Vhp0_observer_tb_top.mk','-f',str(stage/'no-pch.mk'),'-j4','OBJCACHE='],'compile.log',180)
  if list(stage.rglob('*.gch')):raise RuntimeError('unexpected PCH artifact')
  run([str(stage/'obj/Vhp0_observer_tb_top'),str(stage/'unit.fst')],'unit.log',30)
  if before!=[bind(HERE/n) for n in SOURCES]:raise RuntimeError('source drift')
  raw=(out/'unit.log').read_text()
  if 'HP0_PASSIVE_TIMING_OBSERVER PASS cases=' not in raw:raise RuntimeError('specific scoreboard PASS absent')
  state='PASS standalone protocol scoreboard TRACE1; inference/area/integration unverified'
 except BaseException:
  state='FAIL preserved standalone attempt';raise
 finally:
  for n in SOURCES:shutil.copyfile(stage/n,out/n)
  trace=stage/'unit.fst'
  if trace.exists():shutil.copyfile(trace,out/'unit.fst')
  proof=dict(state=state,sources_before=before,sources_after=[bind(HERE/n) for n in SOURCES],verilator=bind(VERILATOR),commands=commands,stage=str(stage),family_stage_peak_allocated_bytes=peak,family_stage_cap_bytes=CAP,trace_cap_bytes=TRACE_CAP,PCH=False,compiler_cache=False,compiler_workers=4,trace=bind(out/'unit.fst') if (out/'unit.fst').exists() else None,model=bind(stage/'obj/Vhp0_observer_tb_top') if (stage/'obj/Vhp0_observer_tb_top').exists() else None,limits='No top wiring, synthesis, board, memory-traffic interference, latency attribution or performance claim')
  (out/'manifest.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(dict(state=state,manifest=bind(out/'manifest.json')),sort_keys=True))
if __name__=='__main__':main()
