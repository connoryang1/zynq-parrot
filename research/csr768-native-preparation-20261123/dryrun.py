#!/usr/bin/env python3
"""Actual bounded Make -n against the real source and parent-design layout."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import materialize as source
sys.path.insert(0,str(source.PREVIOUS))
import software_owned_v2 as owned

LIMIT=1024**2

def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')

def layout(out):
    source.require(out.is_dir() and not (out/'Makefile.design').exists(),'fresh out parent-design layout')
    (out/'Makefile.design').symlink_to(source.SOURCE/'cosim/black-parrot-example/Makefile.design')
    runtime=out/'verilator';runtime.mkdir()
    source.require(not (runtime/'Makefile.design').exists(),'actual recipe reads ../Makefile.design')
    return runtime

def verify(path,command,lines):
    q=json.loads(Path(path).read_text())
    source.require(q['state']=='PASS actual make-n only; no compiler/model/native/reader','successful actual Make preflight required')
    source.require(q['argv']==list(map(str,command+['-n','build'])),'same actual Make command')
    for row in (q['log'],q['design'],q['helper'],q['ownership_helper']):source.require(source.bind(row['path'])==row,'actual preflight input/log changed')
    life=q['ownership'];source.require(life['returncode']==0 and life['failure'] is None and not life['owned_group_remaining'],'complete actual owned Make')
    source.require(Path(q['runtime']).parent/'Makefile.design'==Path(q['design_link']) and Path(q['design_link']).resolve()==source.SOURCE/'cosim/black-parrot-example/Makefile.design','correct literal runtime parent design')
    text=Path(q['log']['path']).read_text()
    for token in ('BP_CACHE_MISS_TRACE=0','BP_RETAINED_I_LINES='+str(lines),'BP_RETAINED_D_LINES='+str(lines),'BP_RETAINED_SETS=256','--build-jobs 8','-DBSG_HIDE_FROM_SYNTHESIS'):
        source.require(token in text,'actual expanded Make preflight '+token)
    return q

def perform(out,command,lines,guard):
    source.require(not out.exists(),'fresh actual preflight, preserve any failure')
    out.mkdir();runtime=layout(out);(out/'tmp').mkdir()
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(out/'tmp'),CCACHE_DISABLE='1',SCCACHE_DISABLE='1',OBJCACHE='')
    for key in list(env):
        if key.startswith(('BP_RETAINED_','BP_AXI_RESPONSE_DELAY','BP_CACHE_MISS_TRACE')):env.pop(key)
    record=dict(state='RUNNING actual Make dryrun only',argv=list(map(str,command+['-n','build'])),runtime=str(runtime),
        design_link=str(out/'Makefile.design'),design=source.bind(source.SOURCE/'cosim/black-parrot-example/Makefile.design'),
        helper=source.bind(__file__),ownership_helper=source.bind(source.PREVIOUS/'software_owned_v2.py'),
        timeout_s=120,cleanup_s=5,cache=dict(CCACHE_DISABLE=1,SCCACHE_DISABLE=1,OBJCACHE=''))
    life=None
    def check():
        guard();source.require(source.size(out)<=LIMIT,'actual preflight1MiB output cap')
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(LIMIT,LIMIT))
    try:
        with (out/'make-n.log').open('wb') as log:life=owned.run(record['argv'],runtime,env,log,120,check,limits)
        record.update(state='PASS actual make-n only; no compiler/model/native/reader',ownership=life,log=source.bind(out/'make-n.log'))
        write(out/'verification.json',record);verify(out/'verification.json',command,lines)
    except BaseException as error:
        life=getattr(error,'owned_receipt',life);record.update(state='FAIL actual make-n preserved; no compile/model admission',error=repr(error),ownership=life)
        if (out/'make-n.log').exists():record['log']=source.bind(out/'make-n.log')
        raise
    finally:write(out/'verification.json',record)
    return source.bind(out/'verification.json')

if __name__=='__main__':
    raise SystemExit('Use run_full.py --prepare-only with the fresh768 ROOT selection/admission; this module does not provide an alternate launch path.')
