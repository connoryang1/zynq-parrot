#!/usr/bin/env python3
"""Compile only under the common reservation; never execute/install a runner."""
from pathlib import Path
import datetime
import fcntl
import hashlib
import json
import shlex
import subprocess

ROOT=Path('/home/coyang/fpga-artifacts/context-resume/retained-observer-host-build-20261121')
REMOTE_DIR='/home/xilinx/bp-logs/retained-observer-host-build-20261121'
HOST='xilinx@192.168.4.35'
OLD_SHA='2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30'
REMOTE=r'''
import pathlib,hashlib,json,tarfile,subprocess,shlex,os
root=pathlib.Path('/home/xilinx/bp-logs/retained-observer-host-build-20261121')
old=pathlib.Path('/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq/control-program')
oldsha='2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(old)==oldsha,'accepted runner changed'
assert subprocess.run(['pgrep','-x','control-program'],stdout=subprocess.PIPE).returncode==1,'active program'
v=os.statvfs(root);assert v.f_bavail*v.f_frsize>=24*1024*1024,'compile peak space reserve'
archive=root/'source.tar.gz';assert sha(archive)=='6c53393a78123253c8647841a6bb1a0d67bd312841f75ba7d4364f1020809855','archive'
with tarfile.open(str(archive),'r:gz') as t:
 members=t.getmembers();assert all(m.isfile() and not m.name.startswith('/') and '..' not in pathlib.PurePosixPath(m.name).parts for m in members),'safe files only'
 assert len(members)==20 and len({m.name for m in members})==20,'members'
 t.extractall(str(root))
m=json.loads((root/'manifest.json').read_text())
for name,b in m['sources'].items():assert sha(root/name)==b['sha256'] and (root/name).stat().st_size==b['bytes'],'source binding'
assert m['definitions']['DRAM_ALLOCATE_SIZE_MB']==46 and m['definitions']['BP_RETAINED_OBSERVE']==1
args=m['compiler_argv_before_python_includes_and_libs'];inc=shlex.split(subprocess.check_output(['python3-config','--includes']).decode());libs=shlex.split(subprocess.check_output(['python3-config','--libs']).decode())
cmd=args[:1]+inc+args[1:]+libs+['-lpthread'];(root/'compiler-argv.json').write_text(json.dumps(cmd,indent=2)+'\n')
with (root/'compile.log').open('w') as log:p=subprocess.run(cmd,cwd=str(root),stdout=log,stderr=subprocess.STDOUT,timeout=240)
result=dict(state='PASS compile only; runner unexecuted/uninstalled' if p.returncode==0 else 'FAIL compile only',returncode=p.returncode,accepted_runner_after=sha(old),board_runtime_artifacts_changed=False)
for name,b in m['sources'].items():assert sha(root/name)==b['sha256'],'source changed during compile'
assert sha(old)==oldsha,'accepted runner changed during compile'
if p.returncode==0:
 out=root/'control-program-observe1';result['runner']=dict(bytes=out.stat().st_size,sha256=sha(out));result['readelf']=subprocess.check_output(['readelf','-h',str(out)]).decode()
(root/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit(p.returncode)
'''

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
 with Path('/home/coyang/fpga-artifacts/pynq-session.lock').open('r') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print('COMMON_RESERVATION_BUSY: no board action');return
  out=ROOT/'compile01';out.mkdir(exist_ok=False);state=dict(state='reserved compile only',started=now(),reservation='/home/coyang/fpga-artifacts/pynq-session.lock',physical_program_runs=0)
  def run(name,argv,limit):
   with (out/(name+'.log')).open('w') as f:p=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,timeout=limit)
   if p.returncode:raise RuntimeError(name+' rc='+str(p.returncode))
  try:
   run('create',['ssh','-o','BatchMode=yes',HOST,'test ! -e '+shlex.quote(REMOTE_DIR)+' && mkdir '+shlex.quote(REMOTE_DIR)],20)
   run('upload',['scp','-q',str(ROOT/'source.tar.gz'),HOST+':'+REMOTE_DIR+'/source.tar.gz'],30)
   (out/'remote-build.py').write_text(REMOTE)
   run('compile',['ssh','-o','BatchMode=yes',HOST,'python3 -c '+shlex.quote(REMOTE)],270)
   run('retrieve',['scp','-q',HOST+':'+REMOTE_DIR+'/{control-program-observe1,result.json,compile.log,compiler-argv.json}',str(out)],30)
   result=json.loads((out/'result.json').read_text());blob=(out/'control-program-observe1').read_bytes();assert hashlib.sha256(blob).hexdigest()==result['runner']['sha256'] and len(blob)==result['runner']['bytes']
   state.update(state='PASS native compile only; accepted runner untouched; new binary unexecuted',result=result)
  except BaseException as e:state.update(state='FAIL compile/stage only; no target program execution',error=repr(e));raise
  finally:state['released']=now();(out/'session.json').write_text(json.dumps(state,indent=2)+'\n')
 print(out/'session.json')
if __name__=='__main__':main()
