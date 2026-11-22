#!/usr/bin/env python3
"""Separate ROOT-reviewed prepare/build phases, each in one bounded owned group."""
import argparse
import json
import os
import sys
import time
sys.dont_write_bytecode=True
from common import *
from bounded import Guard
from host_flow import ADMISSION,validate

SOURCE_PLAN=HERE.parent/'preparation-source.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('prepare','qualify'),required=True)
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--approval-sha')
    parser.add_argument('--fullcore-sha',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    require(args.execute,'default offline; explicit ROOT execution only')
    require(bind(SOURCE_PLAN)['sha256']==args.source_sha,'ROOT reviewed immutable preparation source SHA')
    source=json.loads(SOURCE_PLAN.read_text())
    for row in source['inputs']:verify(row)
    require(source['model_sha']==MODEL_SHA,'exact new matched256 model')
    require(bind(ORIGINAL/'session.json')['sha256']==args.fullcore_sha,'exact ROOT closed new-fullcore proof')
    require(json.loads((ORIGINAL/'session.json').read_text())['state'].startswith('PASS CSR unmasked256'),'new fullcore must close before observation work')
    if args.phase=='prepare':
        require(args.approval_sha is None and not STAGE.exists(),'fresh prepare only, no clone approval')
        deadline=3600;argv=[sys.executable,'-B',HERE/'prepare_host.py','--prepare-only','--worker','--fullcore-sha',args.fullcore_sha]
    else:
        require(args.approval_sha and bind(ADMISSION)['sha256']==args.approval_sha,'separate ROOT clone admission SHA')
        validate(json.loads(ADMISSION.read_text()))
        require(not (STAGE/'build').exists() and not (ROOT/'target-one-shot-claim.json').exists(),'one clone build/cold08; no retry')
        deadline=6600;argv=[sys.executable,'-B',HERE/'host_flow.py','--worker','--approval-sha',args.approval_sha]
    guard=Guard(deadline)
    if args.phase=='prepare':STAGE.mkdir();(STAGE/'tmp').mkdir()
    guard()
    journal=STAGE/(args.phase+'-supervision.json')
    require(not journal.exists(),'phase is not restartable')
    record=dict(state='RUNNING ROOT-approved '+args.phase,source_plan=bind(SOURCE_PLAN),phase=args.phase,
                original_resource_snapshot=guard.initial,source_helper_snapshot=guard.home,deadline_seconds=deadline)
    save(journal,record);life=None
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(STAGE/'tmp'),CCACHE_DISABLE='1',SCCACHE_DISABLE='1',OBJCACHE='')
    try:
        with (STAGE/(args.phase+'-worker.log')).open('xb') as stream:
            life=guard.owned.run(argv,HERE,env,stream,deadline,guard,None)
        require(life['returncode']==0,'owned phase failed; preserve without retry')
        for row in source['inputs']:verify(row)
        record.update(state='PASS separate '+args.phase,resource_after=guard.finish(),
                      result=bind(ROOT/'prepared-handoff.json') if args.phase=='prepare' else bind(STAGE/'flow.json'))
    except BaseException as error:
        life=getattr(error,'owned_receipt',life);record.update(state='FAIL preserved no retry',error=repr(error));raise
    finally:
        record.update(ownership=life,elapsed_seconds=time.monotonic()-guard.start);save(journal,record)
        print(journal,record['state'])


if __name__=='__main__':main()
