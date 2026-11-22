"""Fresh borrowing fulltrace allocation; existing frozen work reservations remain priced."""
from pathlib import Path
import shutil
import materialize as source
BASE=Path('/run/user/1001/zp-retained-borrow256-trace0-fullcore-20261122-01')
PRIOR_BASE=[]
BORROW1792=[Path('/run/user/1001/zp-retained-borrow-trace0-fullcore-20261122-'+x)for x in ('01','02','03')]
BORROW1792_CAP=768*1024**2
OWN_CAP=768*1024**2
MATCHED=[Path('/run/user/1001/zp-retained256-fullcore-20261122-02'),Path('/run/user/1001/zp-retained256-fullcore-20261122-01')]
SCRATCH=[Path('/run/user/1001/zp-retained-scratch-trace0-fullcore-20261122-02'),Path('/run/user/1001/zp-retained-scratch-trace0-fullcore-20261122-01')]
MATCHED_CAP=768*1024**2;SCRATCH_CAP=768*1024**2
R7=Path('/run/user/1001/zp-linux-canonical-r7-20261121');R7_CAP=2560*1024**2
FLOOR=1024**3
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow256-trace0-fullcore-20261122')
DURABLE_CAP=64*1024**2

def required_free(own,matched,scratch,r7,borrow1792,free):
    source.require(0<=own<=OWN_CAP and 0<=matched<=MATCHED_CAP and 0<=scratch<=SCRATCH_CAP and 0<=r7<=R7_CAP and 0<=borrow1792<=BORROW1792_CAP,'all five bounded work allocations')
    need=FLOOR+OWN_CAP-own+MATCHED_CAP-matched+SCRATCH_CAP-scratch+BORROW1792_CAP-borrow1792
    source.require(free>=need,'1GiB floor plus ALL five remaining work allocations')
    return need

def check():
    home=source.budget();durable=source.size(DURABLE)
    source.require(durable<=DURABLE_CAP,'newsmall64MiB complete durable cap')
    source.require(shutil.disk_usage(source.HERE).free>=home['required_free_bytes']+DURABLE_CAP-durable,'HOME3GiB plus old/new source/helper/durable remaining allocations')
    # Source preparation does not reserve/create this fresh run directory.
    source.require(BASE.parent.is_dir() and all(p.is_dir()for p in MATCHED+SCRATCH+[R7]+[p for p in BORROW1792 if p.exists()]),'actual ROOT work namespace and existing frozen work required')
    source.require(all(p.stat().st_dev==BASE.parent.stat().st_dev for p in MATCHED+SCRATCH+[R7]+[p for p in BORROW1792 if p.exists()]) and BASE.parent.stat().st_dev!=source.HERE.stat().st_dev,'actual shared separate /runuser volume, no private substitution')
    own=source.size(BASE)+sum(source.size(p)for p in PRIOR_BASE);matched=sum(source.size(p)for p in MATCHED);scratch=sum(source.size(p)for p in SCRATCH);r7=source.size(R7);free=shutil.disk_usage(BASE.parent).free
    borrow1792=sum(source.size(p)for p in BORROW1792)
    r7_release=source.reservations.r7();cad=source.reservations.cad()
    source.require(source.reservations.CAD_WORK.stat().st_dev==BASE.parent.stat().st_dev,'active CAD shares actual runuser volume')
    need=required_free(own,matched,scratch,r7,borrow1792,free)+cad['remaining_work']
    source.require(free>=need,'1GiB floor plus ALL own/old/activeCAD future work allocations')
    return dict(own_bytes=own,matched_bytes=matched,scratch_bytes=scratch,r7_bytes=r7,borrow1792_bytes=borrow1792,required_free_bytes=need,free_bytes=free,own_cap=OWN_CAP,matched_cap=MATCHED_CAP,scratch_cap=SCRATCH_CAP,r7_cap=R7_CAP,r7_release=r7_release,active_CAD=cad,reserve=FLOOR)
