#!/usr/bin/env python3
"""One ROOT-reviewed owned-group clone build/cold08; no cleanup or all-slot run."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
sys.dont_write_bytecode=True
from common import *
from host_flow import ADMISSION,STAGE,HOME_CAP,used,validate

FROZEN=Path('/home/coyang/zynq-parrot-linux-host-observer/research/retained256-qualification-20261122')
sys.path.insert(0,str(FROZEN))
import budget256_v2 as budget
import software_owned_v2 as ownership
DEADLINE=6600


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--approval-sha',required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    require(a.execute,'default offline; explicit ROOT execution required')
    require(bind(ADMISSION)['sha256']==a.approval_sha,'external prepared admission SHA')
    admission=json.loads(ADMISSION.read_text());proposal=validate(admission)
    require(not STAGE.exists() and not (ROOT/'target-one-shot-claim.json').exists(),'one fresh clone qualification, no retries')
    stat=ORIGINAL.stat();require(proposal['namespace_identity']==dict(device=stat.st_dev,inode=stat.st_ino),'actual original namespace identity')
    baseline=budget.check(ORIGINAL);home=budget.home.check_budget()
    require(baseline['own_bytes']+ARTIFACT_ALLOCATION<=budget.OWN_CAP,'reserve full clone256MiB plus frozen original/failed stages in768MiB')
    frozen=dict(own=baseline['own_bytes'],r7=baseline['r7_bytes'])
    STAGE.mkdir();(STAGE/'tmp').mkdir()
    start=time.monotonic();life=None
    def guard():
        require(time.monotonic()-start<DEADLINE,'fixed6600s complete clone/build/native/five-domain/checker deadline')
        work=used(STAGE);require(work<=ARTIFACT_ALLOCATION,'256MiB observation stage cap')
        total=frozen['own']+work;require(total<=budget.OWN_CAP,'shared768MiB cap includes originals and clone')
        need=budget.FLOOR+budget.OWN_CAP-total+budget.R7_CAP-frozen['r7']
        require(shutil.disk_usage(STAGE.parent).free>=need,'same-volume1GiB plus remaining own/R7 caps')
        durable=used(budget.DURABLE);require(durable<=budget.DURABLE_CAP and used(ROOT)<=HOME_CAP,'combined128MiB durable/scoped64MiB subcap')
        h=budget.home
        needhome=h.HOME_FLOOR+h.SOURCE_CAP-home['source_bytes']+h.HELPER_CAP-home['helper_bytes']+budget.DURABLE_CAP-durable
        require(shutil.disk_usage(ROOT).free>=needhome,'HOME3GiB plus all remaining allocations')
    journal=ROOT/'host-supervision.json'
    record=dict(state='RUNNING ROOT-approved owned clone flow',admission=bind(ADMISSION),supervisor=bind(__file__),
                frozen_original_work=baseline,source_helper=home,stage=str(STAGE),deadline_seconds=DEADLINE)
    save(journal,record)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(STAGE/'tmp'),CCACHE_DISABLE='1',SCCACHE_DISABLE='1',OBJCACHE='')
    try:
        with (STAGE/'worker.log').open('wb') as log:
            life=ownership.run([sys.executable,'-B',HERE/'host_flow.py','--worker','--approval-sha',a.approval_sha],HERE,env,log,DEADLINE,guard,lambda:None)
        require(life['returncode']==0,'clone flow rejected; preserve failed attempt')
        validate(admission);budget.check(ORIGINAL)
        require(used(budget.BASE)+used(budget.FAILED_BASE)==frozen['own']+used(STAGE),'frozen original/failed stage byte sizes unchanged')
        record.update(state='PASS one matched256 observation-only qualification',flow=bind(STAGE/'flow.json'),
                      durable_archive=bind(ROOT/'closed01/archive.json'),stage_bytes=used(STAGE))
    except BaseException as error:
        life=getattr(error,'owned_receipt',life);record.update(state='FAIL preserved no retry or cleanup',error=repr(error));raise
    finally:
        record.update(ownership=life,elapsed_seconds=time.monotonic()-start);save(journal,record)
        print(journal,record['state'])


if __name__=='__main__':main()
