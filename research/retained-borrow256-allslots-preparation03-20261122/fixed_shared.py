"""One shared fixed policy: no live CAD recursion or legacy guard calls."""
import json
from pathlib import Path
import shutil
import bridge as b
import fixed_reservations as frozen

POLICY=Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/retained-borrow256-shared-budget-preparation-20261122/policy.json')
POLICY_SHA='865f8008175d2049a0c9e7e362962b75a5bedc4600a12ef8cc2cdf1d2a8ca10a'
NOTE=POLICY.with_name('operational-note.json')
NOTE_SHA='564dc85acc3f57c1ca6a6724034c61f8c01e3156fdb6470e1b91b085e4e1ab62'


def load(path,expected_sha,full=False):
    b.require(Path(path)==POLICY and expected_sha==POLICY_SHA and b.bind(path)['sha256']==POLICY_SHA,'exact shared ROOT reviewed reserve policy')
    p=json.loads(POLICY.read_text())
    b.require(p['schema']=='borrow256-shared-reserve-policy-v1' and p['state']=='PREPARED exact shared prospective policy; ROOT launch/source/idle guards still required','resource policy only; target requires separate ROOT admission')
    b.require(p['source']['TOP']=='1008854d30e5d923c86c3232fc22af039467d552' and p['source']['BP']=='bb575a764c200f07c6f3259a179bdc861dd7593f','matched source geometry')
    b.require(p['basis']==b.bind(frozen.EXPORT) and p['basis']['sha256']==frozen.EXPORT_SHA,'same actual non-CAD HOME basis')
    old=p['old_R8_freeze'];b.require(old['all_three_required'] is True and old['old_caps_unchanged'] is True,'no half-pair release')
    pair=frozen.closed_pair(dict(old_R8_freeze={k:old[k]for k in ('work','evidence','complete')}),full=full)
    b.require(old['freeze_pair_id']==pair['work']['freeze_pair_id']==pair['evidence']['freeze_pair_id'],'same actual complete freeze pair')
    new=p['new_CAD']
    b.require(new==dict(work_root=str(frozen.NEW_WORK),work_cap_bytes=frozen.WORK_CAP,evidence_roots=list(map(str,frozen.NEW_EVIDENCE)),evidence_cap_bytes=frozen.EVIDENCE_CAP,
                        work_floor_bytes=frozen.FLOOR,HOME_floor_bytes=frozen.HOME_FLOOR,shm_floor_bytes=512*1024**2,deadline_seconds=10800),'fixed full prospective lower256 CAD bounds')
    n=p['native'];b.require(n==dict(pool=str(b.POOL),pool_cap_bytes=frozen.OWN_CAP,new_cohort_cap_inside_pool_bytes=256*1024**2,durable_root=str(b.DURABLE),
                                  durable_cap_bytes=frozen.DURABLE_CAP,durable_bytes_at_policy=47509654,durable_remaining_reserved_bytes=19599210,
                                  allslot_durable_prospective_bytes_inside_same_cap=16*1024**2,shared_helper_cap_bytes=frozen.HELPER_CAP),'unchanged nested native/durable/helper caps')
    other=p['fixed_other_for_CAD_monitor']
    b.require(other['old_RAM_future_by_family']==dict(matched=329830081,scratch=397346275,borrow1792=396196110) and other['old_RAM_future_sum_bytes']==1123372466,'same fixed historical RAM reservations')
    b.require(other['RAM_bytes']==1123372466+frozen.OWN_CAP and other['HOME_nonCAD_base_including_floor_bytes']==frozen.home_base() and other['HOME_bytes']==49424582,'same shared OTHER envelope basis')
    b.require(b.bind(NOTE)['sha256']==NOTE_SHA,'ROOT archive deferral note preserved')
    b.require(frozen.NEW_WORK.parent.stat().st_dev==b.POOL.stat().st_dev!=POLICY.stat().st_dev,'same actual disjoint ROOT work/HOME volumes')
    return p


def snapshot(policy_row):
    p=load(policy_row['path'],policy_row['sha256'])
    pools={name:{str(root):frozen.footprint(root)for root in roots if root.exists()}for name,roots in frozen.OTHER_POOLS.items()}
    totals={name:sum(r['bytes']for rows in roots.values()for r in rows.values())for name,roots in pools.items()}
    reserved=p['fixed_other_for_CAD_monitor']['old_RAM_future_by_family']
    b.require(all(0<=n<=frozen.OWN_CAP and frozen.OWN_CAP-n<=reserved[name]for name,n in totals.items()),'fixed OTHER may overreserve growth, never underprice missing/deleted old work')
    return dict(policy=p,other_pool_footprints=pools,other_pool_totals=totals)


def live_check(snapshot,pool_bytes,durable_bytes,helper_bytes,stage):
    # Only two statvfs calls. NO tree walk, receipt read/hash or legacy guard.
    p=snapshot['policy'];native=p['native'];other=p['fixed_other_for_CAD_monitor'];cad=p['new_CAD']
    b.require(pool_bytes<=native['pool_cap_bytes'] and helper_bytes<=native['shared_helper_cap_bytes'],'same SELF pool/shared helper caps')
    b.require(durable_bytes==native['durable_bytes_at_policy'],'allslot durable archival deferred until CAD terminal/freeze')
    ram_need=cad['work_floor_bytes']+native['pool_cap_bytes']-pool_bytes+other['old_RAM_future_sum_bytes']+cad['work_cap_bytes']
    home_need=other['HOME_nonCAD_base_including_floor_bytes']+native['durable_remaining_reserved_bytes']+native['shared_helper_cap_bytes']+cad['evidence_cap_bytes']
    b.require(shutil.disk_usage(stage).free>=ram_need,'1GiB plus SELF remaining/fixed old RAM/FULL newCAD2.5GiB')
    b.require(shutil.disk_usage(POLICY).free>=home_need,'HOME2.5GiB plus fixed native/old/FULL newCAD192MiB')
    return dict(RAM_required_free_bytes=ram_need,HOME_required_free_bytes=home_need,full_newCAD_work_reserved=cad['work_cap_bytes'],full_newCAD_evidence_reserved=cad['evidence_cap_bytes'])


def verify_snapshot(snapshot,policy_row):
    load(policy_row['path'],policy_row['sha256'],full=True)
    for name,roots in snapshot['other_pool_footprints'].items():
        for root,rows in roots.items():b.require(frozen.footprint(root)==rows,'other sealed work footprint changed')
