#!/usr/bin/env python3
"""ROOT-only fixed four-test batch, after new768 scoped clone qualification."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
SOURCE=HERE/'source-plan.json'


def bind(p):
    p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def require(v,m):
    if not v:raise ValueError(m)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');ap.add_argument('--source-sha',required=True);ap.add_argument('--clone-admission-sha',required=True);args=ap.parse_args()
    require(args.execute and bind(SOURCE)['sha256']==args.source_sha,'explicit ROOT exact-source execution only')
    source=json.loads(SOURCE.read_text())
    for row in source['inputs']:require(bind(row['path'])==row,'fixed source/tool/header/CRT input drift')
    helper=HERE.parent/'csr768-observation-preparation02-20261123/helper';sys.path.insert(0,str(helper))
    from common import STAGE,save
    from bounded import Guard
    from host_flow import ADMISSION,validate
    require(bind(ADMISSION)['sha256']==args.clone_admission_sha,'ROOT exact new clone admission')
    validate(json.loads(ADMISSION.read_text()))
    require(json.loads((STAGE/'flow.json').read_text())['state']=='PASS-one-CSR768-observation-qualification','old model or unqualified clone cannot run')
    journal=STAGE/'architectural-regressions-supervision.json';require(not journal.exists(),'one new fixed batch only; no retry')
    guard=Guard(2400);guard();state=dict(state='RUNNING four architectural software tests only',source=bind(SOURCE),clone_admission=bind(ADMISSION),before=guard.initial);save(journal,state);life=None
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(STAGE/'tmp'),CCACHE_DISABLE='1',SCCACHE_DISABLE='1',OBJCACHE='')
    try:
        with (STAGE/'architectural-regressions-worker.log').open('xb') as log:
            life=guard.owned.run([sys.executable,'-B',HERE/'regressions.py','--worker','--approval-sha',args.clone_admission_sha],HERE,env,log,2400,guard,None)
        require(life['returncode']==0 and not life['owned_group_remaining'],'four-test owned phase failed')
        for row in source['inputs']:require(bind(row['path'])==row,'source/tool/CRT end drift')
        state.update(state='PASS four-test phase, no hardware/app performance claim',result=bind(STAGE/'architectural-regressions01/session.json'),resources=guard.finish())
    except BaseException as e:life=getattr(e,'owned_receipt',life);state.update(state='FAIL preserve without retry',error=repr(e));raise
    finally:state.update(ownership=life,seconds=time.monotonic()-guard.start);save(journal,state)


if __name__=='__main__':main()
