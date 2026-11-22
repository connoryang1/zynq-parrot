"""New closed-base authority: fixed current charges, no historical CAD scans."""
import json,shutil
from pathlib import Path
import bridge as b
POLICY=b.HERE/'ROOT-resource-profile.json'
LIMITS=dict(pool_cap_bytes=1024**3,cohort_inside_pool_bytes=256*1024**2,delta_HOME_cap_bytes=16*1024**2,helper_cap_bytes=1024**2,RUN_floor_bytes=1024**3,HOME_floor_bytes=2415919104,SHM_floor_bytes=512*1024**2)


def load(path,expected_sha,full=False):
    b.require(Path(path)==POLICY and b.bind(path)['sha256']==expected_sha,'exact new ROOT resource authority')
    p=json.loads(POLICY.read_text())
    b.require(p['schema']=='csr256-closed-base-capacity-resources-v1' and p['ROOT_approved'] is True,'pending current resources')
    b.require(p['limits']==LIMITS and p['pool']==str(b.POOL) and p['cohort']==str(b.COHORT) and p['base_durable']==str(b.DURABLE) and p['delta_durable']==str(b.DELTA),'same1GiB pool plus explicit new16MiB delta, fixed roots')
    b.require(p['source_plan']==b.bind(b.HERE/'source-plan.json'),'resource/source contract')
    b.require(p['base_original_HOME_cap_bytes']==32*1024**2 and p['base_future_growth_reserved_bytes']==0 and p['base_closure_reviewed_complete'] is True and p['new_writes_to_closed_base_require_new_admission'] is True,'base32MiB closed, never silently raise old cap')
    b.verify(p['base_closure'])
    b.require(type(p['base_closed_logical_bytes'])is int and 0<=p['base_closed_logical_bytes']<=32*1024**2,'actual closed base footprint')
    b.require(p['all_other_charged_reserves_included'] is True and set(p['OTHER'])=={'RUN_bytes','HOME_bytes','SHM_bytes'} and all(type(v)is int and v>=0 for v in p['OTHER'].values()),'fresh explicit fixed OTHER charges; no legacy future imports')
    for row in p['basis_records']:b.verify(row)
    return p


def snapshot(row):return dict(policy=load(row['path'],row['sha256']))


def live_check(snapshot,pool_bytes,durable_bytes,helper_bytes,stage):
    # Scalar caps and statvfs only. The Ledger seals all inactive file content.
    p=snapshot['policy'];c=p['limits'];o=p['OTHER']
    b.require(pool_bytes<=c['pool_cap_bytes'] and helper_bytes<=c['helper_cap_bytes'],'same whole pool/helper caps')
    b.require(durable_bytes==p['base_closed_logical_bytes'],'closed base has zero unadmitted future growth')
    run_need=c['RUN_floor_bytes']+c['pool_cap_bytes']-pool_bytes+o['RUN_bytes']
    home_need=c['HOME_floor_bytes']+c['delta_HOME_cap_bytes']+c['helper_cap_bytes']-helper_bytes+o['HOME_bytes']
    b.require(shutil.disk_usage(stage).free>=run_need,'RUN floor+SELF remaining+current fixed OTHER')
    b.require(shutil.disk_usage(b.HERE).free>=home_need,'HOME2.25GiB+new16MiB delta+helper remaining+current OTHER')
    b.require(shutil.disk_usage('/dev/shm').free>=c['SHM_floor_bytes']+o['SHM_bytes'],'SHM floor+current OTHER')
    return dict(RUN_required_free_bytes=run_need,HOME_required_free_bytes=home_need,delta_HOME_reserved_bytes=c['delta_HOME_cap_bytes'],legacy_CAD_or_closed_future_charges_imported=False)


def verify_snapshot(snapshot,row):b.require(load(row['path'],row['sha256'],full=True)==snapshot['policy'],'current fixed resource authority changed')
