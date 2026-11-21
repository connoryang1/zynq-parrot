#!/usr/bin/env python3
"""Run exact closed successful model build after a proven pre-model loader failure."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from run_isolated import artifact,limits,TOP,INSTALL


def verify(binding):
    if artifact(binding['path'])!=binding:raise ValueError('binding changed: '+binding['path'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build-session',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    session=a.build_session.resolve();m=json.loads(session.read_text());out=a.output.resolve()
    if out.exists() or not str(out).startswith('/home/coyang/'):raise ValueError('new isolated HOME runtime directory required')
    if m['state']!='FAIL-preserved-no-result' or [(c['label'],c['returncode']) for c in m['commands']]!=[('compile',0),('build',0),('nbf',0),('run',127),('checker',1)]:raise ValueError('only closed successful build with known pre-model loader failure admitted')
    loader=(session.parent/'run.log').read_text()
    if 'error while loading shared libraries: libboost_context.so.1.72.0' not in loader or '[BSG-' in loader:raise ValueError('not the exact pre-model loader failure')
    for c in m['commands']:verify(c['log'])
    for key in ('executable','elf','nbf','actual_source_list'):verify(m[key])
    for binding in m['sources_before'].values():verify(binding)
    if m['geometry']!=dict(i_lines=1280,d_lines=1280,retained_sets=256,payload_bytes_per_line=64) or m['hp0_response_delay']!=0:raise ValueError('geometry/model mismatch')
    if 'I_LINES_1280' not in m['build_stamp'] or 'SETS_256' not in m['build_stamp'] or '-assert-bsgsimhidden-support' not in m['build_stamp']:raise ValueError('model stamp mismatch')
    out.mkdir();env=dict(os.environ);env['LD_LIBRARY_PATH']=str(INSTALL/'lib')+((':'+env['LD_LIBRARY_PATH']) if env.get('LD_LIBRARY_PATH') else '')
    trace=out/'retained1280-native0.fst'
    argv=[m['executable']['path'],'+c_args='+m['nbf']['path']+' 600000','+bsg_trace='+str(trace)]
    r=dict(state='running',build_session=artifact(session),runtime_script=artifact(__file__),executable=m['executable'],elf=m['elf'],nbf=m['nbf'],geometry=m['geometry'],topology=m['topology'],hp0_response_delay=0,build_stamp=m['build_stamp'],
           environment=dict(LD_LIBRARY_PATH=env['LD_LIBRARY_PATH']),libraries={n:artifact(INSTALL/'lib'/n) for n in ('libboost_context.so.1.72.0','libboost_coroutine.so.1.72.0','libboost_system.so.1.72.0')},
           command=dict(argv=argv,cwd=str(out),native_runtime_seconds=600,host_guard_seconds=780),scope=m['scope'])
    (out/'session.json').write_text(json.dumps(r,indent=2)+'\n')
    try:
        linked=subprocess.run(['ldd',m['executable']['path']],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (out/'loader-preflight.log').write_text(linked.stdout)
        if linked.returncode or 'not found' in linked.stdout:raise ValueError('loader dependencies unresolved before target execution')
        start=time.monotonic()
        with (out/'run.log').open('wb') as log:
            proc=subprocess.run(argv,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=780,preexec_fn=limits)
        r['command'].update(returncode=proc.returncode,elapsed_seconds=time.monotonic()-start,log=artifact(out/'run.log'))
        check=['python3',str(TOP/'testing/check_run.py'),str(out/'run.log'),'--test','mt_large_retained_system_test','--exit-code',str(proc.returncode)]
        checked=subprocess.run(check,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (out/'checker.log').write_text(checked.stdout);r['checker']=dict(argv=check,returncode=checked.returncode,script=artifact(TOP/'testing/check_run.py'),log=artifact(out/'checker.log'))
        if checked.returncode:raise ValueError('maintained completion checker rejected run')
        if (out/'run.log').read_text().count('Verilator assertion setting restored to 1')!=1:raise ValueError('runtime assertions not restored')
        r['trace']=artifact(trace)
        for binding in m['sources_before'].values():verify(binding)
        for key in ('executable','elf','nbf','actual_source_list'):verify(m[key])
        r['state']='PASS-complete-checked-system-1280-native0-scoped-assertions'
    except BaseException as e:r.update(state='FAIL-preserved-no-result',error=repr(e));raise
    finally:
        (out/'session.json').write_text(json.dumps(r,indent=2)+'\n');print(out/'session.json',r['state'])

if __name__=='__main__':main()
