"""New lean fulltrace stage; preserve remaining matched256/R7 reservations."""
import json
from pathlib import Path
import shutil
import materialize as source

BASE=Path('/run/user/1001/zp-retained-scratch-trace0-fullcore-20261122-02')
PRIOR_BASE=Path('/run/user/1001/zp-retained-scratch-trace0-fullcore-20261122-01')
OWN_CAP=768*1024**2
MATCHED=Path('/run/user/1001/zp-retained256-fullcore-20261122-02')
FAILED=Path('/run/user/1001/zp-retained256-fullcore-20261122-01')
MATCHED_CAP=768*1024**2
R7=Path('/run/user/1001/zp-linux-canonical-r7-20261121');R7_CAP=2560*1024**2
FLOOR=1024**3
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/retained-scratch-trace0-fullcore-20261122')
DURABLE_CAP=128*1024**2

def own_bytes():return source.size(BASE)+source.size(PRIOR_BASE)

def required_free(own,matched,r7,free):
    source.require(0<=own<=OWN_CAP and 0<=matched<=MATCHED_CAP and 0<=r7<=R7_CAP,'all three source-bound allocation caps')
    need=FLOOR+(OWN_CAP-own)+(MATCHED_CAP-matched)+(R7_CAP-r7)
    source.require(free>=need,'1GiB floor plus ALL three remaining work allocations')
    return need


def check():
    source.budget()
    durable=source.size(DURABLE)
    source.require(durable<=DURABLE_CAP,'new128MiB durable cap')
    source.require(shutil.disk_usage(source.HERE).free>=source.budget()['required_free_bytes']+DURABLE_CAP-durable,'HOME3GiB plus old/new source/helper/durable remaining allocations')
    source.require(BASE.parent.is_dir() and MATCHED.is_dir() and R7.is_dir(),'actual ROOT work namespace required')
    source.require(BASE.parent.stat().st_dev==MATCHED.stat().st_dev==R7.stat().st_dev and BASE.parent.stat().st_dev!=source.HERE.stat().st_dev,'actual shared /runuser separate from HOME, no private RAM substitute')
    own=own_bytes();matched=source.size(MATCHED)+source.size(FAILED);r7=source.size(R7)
    free=shutil.disk_usage(BASE.parent).free;need=required_free(own,matched,r7,free)
    return dict(own_bytes=own,prior_failed_bytes=source.size(PRIOR_BASE),matched_bytes=matched,r7_bytes=r7,required_free_bytes=need,free_bytes=free,
                own_cap=OWN_CAP,matched_cap=MATCHED_CAP,r7_cap=R7_CAP,reserve=FLOOR)
