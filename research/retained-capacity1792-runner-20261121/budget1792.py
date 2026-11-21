"""One unchanged phase/sum/free-space contract for native and audit phases."""
from pathlib import Path
import shutil
import threading
import time
from contextlib import contextmanager
import frozen
from build import require

@contextmanager
def resource_phase(check):
    """Continue resource checks during hashing, parsing and final proof writes."""
    stop=threading.Event();errors=[]
    def poll():
        previous=time.monotonic()
        while not stop.wait(.25):
            try:
                now=time.monotonic();require(now-previous<=1,'phase resource poll gap over1s');previous=now;check()
            except BaseException as error:errors.append(error);return
    def guarded():
        if errors:raise errors[0]
        check()
    guarded();thread=threading.Thread(target=poll,daemon=True);thread.start()
    try:
        yield guarded
        guarded()
    finally:
        stop.set();thread.join(timeout=1);require(not thread.is_alive(),'phase resource guard did not stop')
        if errors:raise errors[0]

def check_budget(cohort, preparation):
    fixed=dict(per_trace_cap_bytes=128*1024**2,raw_cohort_cap_bytes=384*1024**2,
               audit_cohort_cap_bytes=96*1024**2,per_audit_cap_bytes=32*1024**2,other_stage_cap_bytes=32*1024**2,native_runtime_ms=1800000,outer_timeout_s=1980,
               preparation_cap_bytes=16*1024**2,HOME_reserve_bytes=3*1024**3,
               RAM_stage_cap_bytes=512*1024**2,RAM_reserve_bytes=1024**3)
    require(all(preparation.get(k)==v for k,v in fixed.items()),'fixed reviewed budgets')
    total=sum(path.stat().st_size for path in cohort.rglob('*') if path.is_file())
    raw=sum(path.stat().st_size for path in cohort.glob('*/trace.fst'))
    audits=sum(path.stat().st_size for path in cohort.glob('*-audit/*') if path.is_file())
    require(total<=fixed['RAM_stage_cap_bytes'] and raw<=fixed['raw_cohort_cap_bytes'] and audits<=fixed['audit_cohort_cap_bytes'] and total-raw-audits<=fixed['other_stage_cap_bytes'],'exact combined/raw/audit/other caps')
    require(all(path.stat().st_size<=fixed['per_trace_cap_bytes'] for path in cohort.glob('*/trace.fst')),'per-case trace cap')
    require(all(sum(p.stat().st_size for p in d.rglob('*') if p.is_file())<=fixed['per_audit_cap_bytes'] for d in cohort.glob('*-audit') if d.is_dir()),'per-case audit cap')
    home=Path(preparation['HOME_preparation_path']);require(home.is_dir(),'explicit HOME preparation')
    require(sum(p.stat().st_size for p in home.rglob('*') if p.is_file())<=fixed['preparation_cap_bytes'],'HOME preparation cap')
    if preparation['storage']=='HOME':
        require(shutil.disk_usage(cohort).free>=fixed['HOME_reserve_bytes']+max(0,fixed['RAM_stage_cap_bytes']-total)+fixed['preparation_cap_bytes'],'HOME budget plus3GiB reserve')
    elif preparation['storage']=='ROOT-host-RAM':
        require(str(cohort.resolve()).startswith('/dev/shm/'),'explicit root-host RAM path only')
        require(total<=fixed['RAM_stage_cap_bytes'] and shutil.disk_usage(cohort).free>=fixed['RAM_reserve_bytes']+fixed['RAM_stage_cap_bytes']-total,'bounded RAM stage plus1GiB reserve')
        require(shutil.disk_usage(home).free>=fixed['HOME_reserve_bytes']+fixed['preparation_cap_bytes'],'HOME3GiB reserve')
    else:raise ValueError('reviewed storage path required')

