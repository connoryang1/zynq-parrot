"""Same-volume remaining allocations from immutable CAD admission plus new SELF."""
import json,os,shutil,stat
from pathlib import Path
import bridge as b
POLICY=b.HERE/'ROOT-resource-profile.json'
CAD_ADMISSION={'path': '/home/coyang/fpga-artifacts/context-resume/csr-opt768-fpga-preparation-20261123/preparation01/admission.FINAL.json', 'bytes': 2218979, 'sha256': '8cb0404b90965f209b702c84e5de02df333ea8a975399a3ba00d342c718f44fb'}
LIMITS=dict(pool_cap_bytes=96*1024**2,cohort_inside_pool_bytes=96*1024**2,delta_HOME_cap_bytes=0,helper_cap_bytes=128*1024,RUN_floor_bytes=1024**3,HOME_floor_bytes=1792*1024**2,SHM_floor_bytes=512*1024**2)


def load(path,expected_sha,full=False):
    b.require(Path(path)==POLICY and b.bind(path)['sha256']==expected_sha,'exact fresh ROOT resource authority')
    p=json.loads(POLICY.read_text())
    b.require(p['schema']=='csr768-standalone-joint-resources-v1' and p['ROOT_approved']is True,'no allocation/execution authority in DRAFT')
    b.require(p['host_accounting']==b.HOST_ACCOUNTING,'same explicit03 host accounting cadence')
    b.require(p['limits']==LIMITS and p['pool']==str(b.POOL) and p['cohort']==str(b.COHORT) and p['base_durable']==str(b.DURABLE),'exact fresh96MiB joint namespace; no closed pool growth')
    b.require(p['source_plan']==b.bind(b.HERE/'source-plan.json'),'same source contract')
    b.require(p['base_future_growth_reserved_bytes']==0 and p['new_writes_to_closed_base_require_new_admission']is True and p['base_closure_reviewed_complete']is True,'closed base unchanged')
    b.require(p['base_closure']['sha256']==b.BASE_MANIFEST_SHA,'same actual768 base');b.verify(p['base_closure'])
    b.require(type(p['base_closed_logical_bytes'])is int and p['base_closed_logical_bytes']>=24914716,'complete existing durable family charged')
    b.require(p['all_other_charged_reserves_included']is True and set(p['OTHER'])=={'RUN_bytes','HOME_bytes','SHM_bytes'} and all(type(v)is int and v>=0 for v in p['OTHER'].values()),'fresh fixed OTHER; CAD remaining is separately dynamic')
    b.require(p['active_CAD_admission']==CAD_ADMISSION and p['CAD_remaining_in_OTHER']is False,'exact immutable active CAD; do not duplicate its dynamic remaining in OTHER')
    for row in p['basis_records']:b.verify(row)
    return p


def snapshot(row):return dict(policy=load(row['path'],row['sha256']))


def ancestor(path):
    p=Path(path)
    while not p.exists():
        b.require(p!=p.parent,'existing filesystem ancestor');p=p.parent
    return p


def allocated(root):
    # Same per-root du semantics as01: include root and directory/symlink blocks,
    # do not follow symlinks, deduplicate hardlinked inodes. DirEntry.stat avoids
    # per-file Path allocation and the separate per-file path/lstat traversal.
    root=os.fspath(root);seen=set();total=0;todo=[]
    try:st=os.lstat(root)
    except FileNotFoundError:return 0
    seen.add((st.st_dev,st.st_ino));total+=st.st_blocks*512
    if stat.S_ISDIR(st.st_mode):todo.append(root)
    while todo:
        directory=todo.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:st=entry.stat(follow_symlinks=False)
                    except FileNotFoundError:continue
                    key=(st.st_dev,st.st_ino)
                    if key in seen:continue
                    seen.add(key);total+=st.st_blocks*512
                    if stat.S_ISDIR(st.st_mode):todo.append(entry.path)
        except FileNotFoundError:continue  # Concurrent CAD temp unlink.
    return total


def cad_remaining(p):
    # Immutable authority is hash-checked; no live CAD Python module import,
    # recursive source hashing, or source/WORK/evidence mutation occurs here.
    b.verify(CAD_ADMISSION);a=json.loads(Path(CAD_ADMISSION['path']).read_text())
    b.verify(a['resource_profile']);cfg=a['configuration'];r=a['resources']
    b.require(a['top']=='1b24c915ed628f6d47a382b3aa89fb662884e1a1' and a['bp']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','same active768 CAD')
    b.require(r['source_cap_bytes']==134217728 and r['work_cap_bytes']==1610612736 and r['evidence_cap_bytes']==201326592 and r['home_floor_bytes']==1879048192 and r['work_floor_bytes']==1073741824 and r['shm_floor_bytes']==536870912,'all admitted CAD caps/floors unchanged')
    b.require(p['OTHER']['RUN_bytes']>=r['other_work_future_bytes']==301989888 and p['OTHER']['HOME_bytes']>=r['other_home_future_bytes']+98304 and r['other_home_future_bytes']==183060828 and p['OTHER']['SHM_bytes']>=r['other_shm_future_bytes']==335544320,'retain FULL historic BASE and other immutable CAD reserves exactly once')
    source=Path(cfg['prepared_source_root']);work=Path(cfg['work_root']);ev=list(map(Path,cfg['evidence_roots']))
    roots=[source,work,*ev]
    b.require(len(ev)==2 and len(set(roots))==4 and not any(x in y.parents for x in roots for y in roots if x!=y),'disjoint admitted CAD roots; no source-evidence double count')
    b.require(b.COHORT not in roots and not any(x in b.COHORT.parents or b.COHORT in x.parents for x in roots),'new SELF disjoint from active CAD')
    b.require(all(ancestor(x).stat().st_dev==ancestor(b.HERE).stat().st_dev for x in ev),'both CAD evidence roots on actual HOME volume')
    counts=dict(source=allocated(source),work=allocated(work),evidence=sum(allocated(x)for x in ev))
    entries=[]
    for name,path,cap,floor in (('source',source,r['source_cap_bytes'],r['work_floor_bytes']),('work',work,r['work_cap_bytes'],r['work_floor_bytes']),('evidence',ev[0],r['evidence_cap_bytes'],r['home_floor_bytes'])):
        b.require(0<=counts[name]<=cap,'unchanged CAD '+name+' allocation cap')
        entries.append((str(path),floor,cap-counts[name]))
    return entries,dict(admission=CAD_ADMISSION,allocated_bytes=counts,remaining=dict(source=r['source_cap_bytes']-counts['source'],work=r['work_cap_bytes']-counts['work'],evidence=r['evidence_cap_bytes']-counts['evidence']))


def live_check(snapshot,pool_bytes,durable_bytes,helper_bytes,stage):
    p=snapshot['policy'];c=p['limits'];o=p['OTHER']
    b.require(pool_bytes<=c['pool_cap_bytes'] and helper_bytes<=c['helper_cap_bytes'],'standalone stage/helper logical caps')
    b.require(durable_bytes==p['base_closed_logical_bytes'],'sealed durable base; no archive authority')
    entries,cad=cad_remaining(p)
    entries += [(stage,c['RUN_floor_bytes'],c['pool_cap_bytes']-pool_bytes+o['RUN_bytes']),
        (b.HERE,c['HOME_floor_bytes'],c['helper_cap_bytes']-helper_bytes+o['HOME_bytes']),
        ('/dev/shm',c['SHM_floor_bytes'],o['SHM_bytes'])]
    groups={}
    for path,floor,remaining in entries:
        root=ancestor(path);dev=root.stat().st_dev;free=shutil.disk_usage(root).free
        g=groups.setdefault(dev,dict(device=dev,paths=[],floor=0,remaining=0,free=free))
        g['paths'].append(str(path));g['floor']=max(g['floor'],floor);g['remaining']+=remaining;g['free']=min(g['free'],free)
    for g in groups.values():
        g['required_free_bytes']=g['floor']+g['remaining']
        b.require(g['free']>=g['required_free_bytes'],'actual-volume union floor+CADremaining+FULL BASE/OTHER+newSELFremaining: '+repr(g))
    return dict(volume_requirements=list(groups.values()),active_CAD=cad,delta_HOME_reserved_bytes=0,legacy_live_budget_imported=False)


def verify_snapshot(snapshot,row):b.require(load(row['path'],row['sha256'],full=True)==snapshot['policy'],'fixed ROOT resource authority changed')
