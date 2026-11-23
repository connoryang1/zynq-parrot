"""Separately admitted standalone128MiB, all fixed OTHER charges retained explicitly."""
import json,shutil
from pathlib import Path
import bridge as b
POLICY=b.HERE/'ROOT-resource-profile.json'
LIMITS=dict(pool_cap_bytes=128*1024**2,cohort_inside_pool_bytes=128*1024**2,delta_HOME_cap_bytes=0,helper_cap_bytes=128*1024,RUN_floor_bytes=1024**3,HOME_floor_bytes=2*1024**3,SHM_floor_bytes=512*1024**2)


def load(path,expected_sha,full=False):
    b.require(Path(path)==POLICY and b.bind(path)['sha256']==expected_sha,'exact fresh ROOT resource authority')
    p=json.loads(POLICY.read_text())
    b.require(p['schema']=='csr1280-standalone-allslots-resources-v1' and p['ROOT_approved']is True,'no allocation/execution authority in DRAFT')
    b.require(p['limits']==LIMITS and p['pool']==str(b.POOL) and p['cohort']==str(b.COHORT) and p['base_durable']==str(b.DURABLE),'exact fresh128MiB namespace; no closed pool growth')
    b.require(p['source_plan']==b.bind(b.HERE/'source-plan.json'),'same source contract')
    b.require(p['base_future_growth_reserved_bytes']==0 and p['new_writes_to_closed_base_require_new_admission']is True and p['base_closure_reviewed_complete']is True,'closed base unchanged')
    b.require(p['base_closure']['sha256']==b.BASE_MANIFEST_SHA,'same actual1280 base');b.verify(p['base_closure'])
    b.require(type(p['base_closed_logical_bytes'])is int and p['base_closed_logical_bytes']>=25255944,'complete existing durable family charged')
    b.require(p['all_other_charged_reserves_included']is True and set(p['OTHER'])=={'RUN_bytes','HOME_bytes','SHM_bytes'} and all(type(v)is int and v>=0 for v in p['OTHER'].values()),'fresh fixed OTHER profile including active CAD')
    b.require(p['OTHER']['RUN_bytes']>=1156926898,'historic BASE remains fully charged unless separately versioned source admission')
    b.require(p['active_CAD_guard_also_satisfied']is True and type(p['active_CAD_RUN_required_free_bytes'])is int and type(p['active_CAD_HOME_required_free_bytes'])is int,'ROOT must price both unchanged active CAD and new native guard')
    for row in p['basis_records']:b.verify(row)
    return p


def snapshot(row):return dict(policy=load(row['path'],row['sha256']))


def live_check(snapshot,pool_bytes,durable_bytes,helper_bytes,stage):
    p=snapshot['policy'];c=p['limits'];o=p['OTHER']
    b.require(pool_bytes<=c['pool_cap_bytes'] and helper_bytes<=c['helper_cap_bytes'],'standalone stage/helper logical caps')
    b.require(durable_bytes==p['base_closed_logical_bytes'],'sealed durable base; no archive authority')
    run_need=max(c['RUN_floor_bytes']+c['pool_cap_bytes']-pool_bytes+o['RUN_bytes'],p['active_CAD_RUN_required_free_bytes'])
    home_need=max(c['HOME_floor_bytes']+c['helper_cap_bytes']-helper_bytes+o['HOME_bytes'],p['active_CAD_HOME_required_free_bytes'])
    b.require(shutil.disk_usage(stage).free>=run_need,'RUN floor+SELF remaining+ALL OTHER+active CAD minimum')
    b.require(shutil.disk_usage(b.HERE).free>=home_need,'HOME floor+helper remaining+ALL OTHER+active CAD minimum')
    b.require(shutil.disk_usage('/dev/shm').free>=c['SHM_floor_bytes']+o['SHM_bytes'],'SHM floor+ALL OTHER')
    return dict(RUN_required_free_bytes=run_need,HOME_required_free_bytes=home_need,delta_HOME_reserved_bytes=0,legacy_CAD_or_closed_future_charges_imported=False)


def verify_snapshot(snapshot,row):b.require(load(row['path'],row['sha256'],full=True)==snapshot['policy'],'fixed ROOT resource authority changed')
