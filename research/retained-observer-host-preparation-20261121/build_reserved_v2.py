#!/usr/bin/env python3
"""Native compile with complete failure evidence; never run/install the binary."""
import importlib.util
from pathlib import Path
import fcntl
import datetime
import subprocess
import json
import hashlib
import shlex

spec=importlib.util.spec_from_file_location('prior',Path(__file__).with_name('build_reserved.py'));prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
ROOT=Path(str(prior.ROOT)+'-v2');REMOTE_DIR=prior.REMOTE_DIR+'-v2'
REMOTE=prior.REMOTE.replace(prior.REMOTE_DIR,REMOTE_DIR).replace('6c53393a78123253c8647841a6bb1a0d67bd312841f75ba7d4364f1020809855','452160c14f2fe1d5be2cc0e18e933d3cebd1b7848e79e50bdaeffef59bcfa890').replace('raise SystemExit(p.returncode)','raise SystemExit(0)')

def main():
 with Path('/home/coyang/fpga-artifacts/pynq-session.lock').open('r') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print('COMMON_RESERVATION_BUSY: no board action');return
  out=ROOT/'compile01';out.mkdir(exist_ok=False);state=dict(state='reserved compile only',started=prior.now(),reservation='/home/coyang/fpga-artifacts/pynq-session.lock',physical_program_runs=0)
  def run(name,argv,limit):
   with (out/(name+'.log')).open('w') as f:p=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,timeout=limit)
   if p.returncode:raise RuntimeError(name+' transport/protocol rc='+str(p.returncode))
  try:
   run('create',['ssh','-o','BatchMode=yes',prior.HOST,'test ! -e '+shlex.quote(REMOTE_DIR)+' && mkdir '+shlex.quote(REMOTE_DIR)],20)
   run('upload',['scp','-q',str(ROOT/'source.tar.gz'),prior.HOST+':'+REMOTE_DIR+'/source.tar.gz'],30)
   (out/'remote-build.py').write_text(REMOTE)
   run('compile',['ssh','-o','BatchMode=yes',prior.HOST,'python3 -c '+shlex.quote(REMOTE)],270)
   for name in ('result.json','compile.log','compiler-argv.json'):
    run('retrieve-'+name,['scp','-q',prior.HOST+':'+REMOTE_DIR+'/'+name,str(out/name)],30)
   result=json.loads((out/'result.json').read_text());state['result']=result
   if result['returncode']!=0:raise RuntimeError('native compiler rc='+str(result['returncode'])+'; full logs collected')
   run('retrieve-binary',['scp','-q',prior.HOST+':'+REMOTE_DIR+'/control-program-observe1',str(out/'control-program-observe1')],30)
   blob=(out/'control-program-observe1').read_bytes();assert hashlib.sha256(blob).hexdigest()==result['runner']['sha256'] and len(blob)==result['runner']['bytes']
   assert result['accepted_runner_after']==prior.OLD_SHA and result['board_runtime_artifacts_changed'] is False
   state.update(state='PASS native compile only; accepted runner untouched; new binary unexecuted')
  except BaseException as e:state.update(state='FAIL compile/stage only; no target execution',error=repr(e));raise
  finally:state['released']=prior.now();(out/'session.json').write_text(json.dumps(state,indent=2)+'\n')
 print(out/'session.json')
if __name__=='__main__':main()
