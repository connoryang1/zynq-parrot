"""ROOT-bound closed-R8 pair plus fixed prospective CAD ceilings; no live CAD walk."""
import json
import os
from pathlib import Path
import shutil
import stat
import bridge as b

HERE=Path(__file__).resolve().parent
POLICY=HERE/'ROOT-fixed-reservations.json'
EXPORT=Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow256-native-monitor-failure-20261122/preflight-export01/allslots-resource-preflight01.json')
EXPORT_SHA='ca5878f852d05ac4941c9571f0401071f619d0abc4a2dd3d2af6bcb4c82bfe81'
CLOSURES=Path('/home/coyang/fpga-artifacts/context-resume/reservation-closures-20261122')
OLD_WORK=Path('/run/user/1001/zp-linux-borrow1792-trace0-cad-20261122-01')
OLD_EVIDENCE=[Path('/home/coyang/fpga-logs-linux-retained-borrow1792-trace0'),Path('/home/coyang/zynq-parrot-linux-host-observer/research/borrow-fpga-cad-preparation-20261122')]
NEW_WORK=Path('/run/user/1001/zp-linux-borrow256-trace0-cad-20261122-01')
NEW_EVIDENCE=[Path('/home/coyang/fpga-logs-linux-retained-borrow256-trace0'),Path('/home/coyang/fpga-artifacts/context-resume/borrow256-fpga-preparation-20261122/preparation01')]
OWN_CAP=768*1024**2;DURABLE_CAP=64*1024**2;FLOOR=1024**3;HOME_FLOOR=2560*1024**2
WORK_CAP=2560*1024**2;EVIDENCE_CAP=192*1024**2;HELPER_CAP=1024**2
OTHER_POOLS={
    'matched':[Path('/run/user/1001/zp-retained256-fullcore-20261122-'+x)for x in ('01','02')],
    'scratch':[Path('/run/user/1001/zp-retained-scratch-trace0-fullcore-20261122-'+x)for x in ('01','02')],
    'borrow1792':[Path('/run/user/1001/zp-retained-borrow-trace0-fullcore-20261122-'+x)for x in ('01','02','03')],
}


def scan(root):
    rows={};todo=[Path(root)]
    if not Path(root).exists():return rows
    while todo:
        with os.scandir(todo.pop()) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):todo.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=True):rows[Path(entry.path)]=entry.stat(follow_symlinks=True).st_size
    return rows


def footprint(root):
    result={}
    for path,size in scan(root).items():
        s=path.stat();result[str(path)]=dict(bytes=size,device=s.st_dev,inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
    return result


def home_base():
    b.require(b.bind(EXPORT)['sha256']==EXPORT_SHA,'actual earlier ROOT HOME snapshot, not invented budget')
    q=json.loads(EXPORT.read_text())['HOME_snapshot']
    value=q['required_free_bytes']-q['active_CAD']['remaining_evidence']
    b.require(value==2713131356 and value>=HOME_FLOOR,'exact non-CAD HOME reserve base')
    return value


def closed_pair(policy,full=False):
    rows=policy['old_R8_freeze']
    b.require(set(rows)=={'work','evidence','complete'},'all three closed-R8 receipts mandatory')
    for name,row in rows.items():
        b.require(Path(row['path'])==CLOSURES/('r8-freeze-complete.json' if name=='complete' else 'r8-'+name+'.json'),'fixed receipt paths')
        b.verify(row)
    marker=json.loads(Path(rows['complete']['path']).read_text())
    b.require(marker['schema']=='r8-work-evidence-freeze-complete-v1' and marker['state']=='PASS ROOT old R8 WORK/evidence immutable freeze; unused future allocations released','ROOT complete pair, no half release')
    b.require(marker['work']==rows['work'] and marker['evidence']==rows['evidence'],'complete marker binds both exact receipt bytes')
    result={}
    for kind in ('work','evidence'):
        q=json.loads(Path(rows[kind]['path']).read_text());roots=[OLD_WORK]if kind=='work' else OLD_EVIDENCE
        b.require(q['schema']=='r8-closed-family-v1' and q['roots']==list(map(str,roots)),'exact closed old-family scope')
        b.require(q['freeze_pair_id']==marker['freeze_pair_id'] and q['requires_complete_marker']==dict(path=rows['complete']['path'],freeze_pair_id=marker['freeze_pair_id']),'common pair ID and required complete marker')
        b.require(q['future_growth_reserved_bytes']==0 and q['original_allocation_limit_unchanged'] is True and q['new_writes_to_closed_family_require_new_admission'] is True and q['no_cleanup'] is True,'only unused future released; occupied bytes retained')
        expected_cap=WORK_CAP if kind=='work' else 384*1024**2
        logical=sum(r['bytes']for r in q['files']);allocated=sum(r['allocated_bytes']for r in q['files'])
        b.require(q['original_allocation_bytes']==expected_cap and q['actual_closed_logical_bytes']==logical and q['actual_closed_allocated_bytes']==allocated and q['actual_closed_charged_bytes']==max(logical,allocated),'closed charged-byte arithmetic')
        b.require(q['unused_allocation_released_bytes']==expected_cap-max(logical,allocated),'release exact unused bytes only')
        for name in ('terminal','durable_closure','independent_verification'):
            b.require(q[name]==marker[name],'common actual terminal/archive/independent proof');b.verify(q[name])
        if full:verify_closed_files(q)
        result[kind]=q
    return result


def verify_closed_files(q):
    # Entry/exit only, outside the accounting child. Never used by live_check.
    actual=set()
    for root in map(Path,q['roots']):
        for parent,dirs,files in os.walk(root,followlinks=False):
            for name in list(dirs):
                p=Path(parent)/name
                if p.is_symlink():actual.add(str(p));dirs.remove(name)
            actual.update(str(Path(parent)/name)for name in files)
    b.require(actual=={r['path']for r in q['files']},'entire frozen R8 pathset retained')
    for r in q['files']:
        p=Path(r['path']);s=p.lstat()
        b.require(stat.S_IMODE(s.st_mode)==r['mode'] and s.st_blocks*512==r['allocated_bytes'],'closed R8 storage metadata changed')
        if r['kind']=='symlink':
            import hashlib
            raw=os.fsencode(os.readlink(p));b.require(p.is_symlink() and os.readlink(p)==r['link_target'] and len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'],'closed R8 link bytes')
        else:b.require(r['kind']=='regular' and stat.S_ISREG(s.st_mode),'closed regular file');b.verify(r)


def load(path,expected_sha,full=False):
    b.require(Path(path)==POLICY and b.bind(path)['sha256']==expected_sha,'ROOT externally approved fixed reservation SHA')
    p=json.loads(Path(path).read_text())
    b.require(p['schema']=='borrow256-fixed-prospective-reservations-v1' and p['state']=='ROOT-APPROVED fixed full prospective lower256 CAD reserves after complete R8 freeze','DRAFT UNLAUNCHABLE')
    b.require(p['preflight']==b.bind(EXPORT),'same original HOME reserve basis')
    future=p['new_CAD']
    b.require(future['work_root']==str(NEW_WORK) and future['work_cap_bytes']==WORK_CAP and future['evidence_cap_bytes']==EVIDENCE_CAP,'prospective complete work/evidence ceilings, no later expansion')
    b.require(future['evidence_roots']==list(map(str,NEW_EVIDENCE)),'exact prospective HOME evidence domains')
    b.require(not set(future['evidence_roots']).intersection(map(str,OLD_EVIDENCE)),'new evidence domains separate from frozen old R8')
    b.require(NEW_WORK.parent.stat().st_dev==b.POOL.stat().st_dev!=HERE.stat().st_dev,'actual separate ROOT work volume')
    closed_pair(p,full=full);home_base()
    return p


def snapshot(policy_row):
    p=load(policy_row['path'],policy_row['sha256'])
    pools={name:{str(root):footprint(root)for root in roots if root.exists()}for name,roots in OTHER_POOLS.items()}
    totals={name:sum(r['bytes']for rows in roots.values()for r in rows.values())for name,roots in pools.items()}
    b.require(all(n<=OWN_CAP for n in totals.values()),'all original other768MiB work caps unchanged')
    return dict(policy=p,other_pool_footprints=pools,other_pool_totals=totals,nonCAD_HOME_base=home_base())


def live_check(snapshot,pool_bytes,durable_bytes,helper_bytes,stage):
    # Deliberately NO rglob, scan, receipt parsing, source hashing or CAD stat.
    b.require(pool_bytes<=OWN_CAP and durable_bytes<=DURABLE_CAP and helper_bytes<=HELPER_CAP,'fixed original own/durable/helper caps')
    ram_need=FLOOR+OWN_CAP-pool_bytes+sum(OWN_CAP-n for n in snapshot['other_pool_totals'].values())+WORK_CAP
    home_need=snapshot['nonCAD_HOME_base']+DURABLE_CAP-durable_bytes+HELPER_CAP-helper_bytes+EVIDENCE_CAP
    b.require(shutil.disk_usage(stage).free>=ram_need,'1GiB plus old/current remaining work and FULL newCAD2.5GiB reserve')
    b.require(shutil.disk_usage(HERE).free>=home_need,'HOME2.5GiB plus old/current remaining and FULL newCAD192MiB reserve')
    return dict(RAM_required_free_bytes=ram_need,HOME_required_free_bytes=home_need,full_newCAD_work_reserved=WORK_CAP,full_newCAD_evidence_reserved=EVIDENCE_CAP)


def verify_snapshot(snapshot,policy_row):
    load(policy_row['path'],policy_row['sha256'],full=True)
    for name,roots in snapshot['other_pool_footprints'].items():
        for root,rows in roots.items():b.require(footprint(root)==rows,'other frozen work pool metadata changed')
