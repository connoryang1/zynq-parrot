#!/usr/bin/env python3
"""ROOT-only full complete768 three-role cohort capture; no target/reader, deletion or implicit future release."""
import argparse,fcntl,gzip,hashlib,json,os,resource,shutil,signal,stat,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
C3=Path('/run/user/1001/zp-csr768-allslots-native-20261123-01')
H3=HERE.with_name('csr768-allslots-native-preparation-20261123')
SEM=HERE.with_name('csr768-capacity-semantic-adapter-20261123')
CTX=Path('/home/coyang/fpga-artifacts/context-resume/csr768-semantic-authority-20261123')
AUTH=Path('/home/coyang/fpga-artifacts/context-resume/csr768-cohort-closure-authority-20261123')
ART=Path('/home/coyang/fpga-artifacts/context-resume/csr768-cohort-closure-20261123');OUT=ART/'closed01'
ROOTS=dict(cohort=C3,native_helper=H3,semantic_helper=SEM,ROOT_context=CTX,ROOT_closure_authority=AUTH,closure_helper=HERE)
ORDER=('d-enabled','d-off','i-enabled')
CAP=16*1024**2


def require(v,m):
    if not v:raise ValueError(m)


def binding(p):
    p=Path(p);h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def verify(r):require(binding(r['path'])=={k:r[k]for k in ('path','bytes','sha256')},'frozen binding '+r['path'])


def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')


def size(root):
    n=0;todo=[root]
    if not root.exists():return 0
    while todo:
        with os.scandir(todo.pop())as entries:
            for e in entries:
                if e.is_dir(follow_symlinks=False):todo.append(Path(e.path))
                else:n+=len(os.readlink(e.path).encode())if e.is_symlink()else e.stat(follow_symlinks=False).st_size
    return n


def ancestor(path):
    p=Path(path)
    while not p.exists():require(p!=p.parent,'existing filesystem ancestor');p=p.parent
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


def guard(a):
    used=size(ART)+size(AUTH);helper=size(HERE)
    require(used<=CAP and helper<=65536,'entire16MiB closure family/64KiB new recipe caps')
    r=a['resources'];require(r['all_other_charged_reserves_included']is True,'fresh full union pricing')
    verify(a['active_CAD_admission']);cad=json.loads(Path(a['active_CAD_admission']['path']).read_text());verify(cad['resource_profile'])
    require(a['active_CAD_admission']['sha256']=='8cb0404b90965f209b702c84e5de02df333ea8a975399a3ba00d342c718f44fb','unchanged live768 CAD')
    cfg=cad['configuration'];lim=cad['resources'];require(cad['top']=='1b24c915ed628f6d47a382b3aa89fb662884e1a1' and cad['bp']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','exact768 source')
    require(lim['source_cap_bytes']==134217728 and lim['work_cap_bytes']==1610612736 and lim['evidence_cap_bytes']==201326592,'unchanged actual CAD caps')
    require(r['OTHER_RUN_bytes']>=lim['other_work_future_bytes']==301989888 and r['OTHER_HOME_bytes']>=lim['other_home_future_bytes']==183060828 and r['OTHER_SHM_bytes']>=lim['other_shm_future_bytes']==335544320,'BASE33MiB/mapping256MiB+8MiB and all CAD OTHER preserved')
    entries=[]
    for roots,cap,floor in (([cfg['prepared_source_root']],lim['source_cap_bytes'],lim['work_floor_bytes']),([cfg['work_root']],lim['work_cap_bytes'],lim['work_floor_bytes']),(cfg['evidence_roots'],lim['evidence_cap_bytes'],lim['home_floor_bytes'])):
        charged=sum(allocated(p)for p in roots);require(charged<=cap,'immutable CAD allocation cap');entries.append((roots[0],floor,cap-charged))
    require(size(C3)<=134217728 and size(H3)<=131072 and size(SEM)+size(CTX)<=98304,'unchanged current whole stage/native-helper/semantic-context source caps')
    entries += [(C3,1073741824,134217728-size(C3)+r['OTHER_RUN_bytes']),
        (HERE,1879048192,CAP-used+65536-helper+131072-size(H3)+98304-size(SEM)-size(CTX)+r['OTHER_HOME_bytes']),
        ('/dev/shm',536870912,r['OTHER_SHM_bytes'])]
    groups={}
    for path,floor,remaining in entries:
        root=ancestor(path);dev=root.stat().st_dev;free=shutil.disk_usage(root).free
        q=groups.setdefault(dev,dict(floor=0,remaining=0,free=free));q['floor']=max(q['floor'],floor);q['remaining']+=remaining;q['free']=min(q['free'],free)
    for q in groups.values():require(q['free']>=q['floor']+q['remaining'],'same-device full union reserve '+repr(q))
    avail=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines()if l.startswith('MemAvailable:'))
    require(avail>=r['MemAvailable_required_bytes'],'encoder1GiB and all other memory priced')



def gates(a):
    for key in ('baseline_manifest','baseline_archive','baseline_inventory','ROOT_no_producers','ROOT_cohort_acceptance','preparation','native_resource_profile','semantic_context','active_CAD_admission'):verify(a[key])
    require(a['baseline_archive']['sha256']=='bd5cfd6aad726b3c91c529c967a50c2f7b4aa887368b4c725c3a8aa6b92ff4b5','exact current768 full/scoped/STD base archive')
    base=json.loads(Path(a['baseline_manifest']['path']).read_text());require(base['state'].startswith('PASS base32')and base['archive']==a['baseline_archive']and base['inventory']==a['baseline_inventory']and base['originals_unchanged']is True,'complete unchanged baseline dependency')
    require(a['preparation']['path']==str(C3/'preparation.json'),'actual separate768 cohort preparation')
    p=json.loads(Path(a['preparation']['path']).read_text())
    require(p['schema']=='csr768-complete-allslots-v1'and p['stage']==str(C3)and p['schedule']==list(ORDER),'actual complete schedule/namespace')
    require(p['model']['sha256']=='1f192b69fb95fce8919d7fbbe6a4c2c594fc8983982e7e2822821e74f2b75fef'and p['semantic_context']==a['semantic_context']and p['fixed_reservations']==a['native_resource_profile'],'actual qualified768 lineage')
    require(p['source_plan']==binding(H3/'source-plan.json'),'unchanged exact executed source contract')
    for source in p['runtime_sources']:verify(source)
    verify(p['source_plan']);verify(p['ROOT_authority']);verify(p['model']);verify(p['compiled_sources']);verify(p['program'])
    policy=json.loads(Path(a['native_resource_profile']['path']).read_text());require(policy['ROOT_approved']is True and policy['prospective_durable_archive_bytes']==CAP and policy['active_CAD_admission']==a['active_CAD_admission'],'16MiB already priced; new codec authority separate')
    root=json.loads(Path(a['ROOT_cohort_acceptance']['path']).read_text())
    require(root['ROOT_verified']is True and root['completed_roles']==list(ORDER)and root['roles']==a['roles']and root['preparation']==a['preparation']and root['all_six_outer_commands_actual_exit0']is True and root['all_owned_groups_absent']is True,'ROOT actual six outer command0 plus semantic completion')
    no=json.loads(Path(a['ROOT_no_producers']['path']).read_text());require(no['ROOT_verified']is True and no['all_cohort_native_reader_accounting_groups_absent']is True and no['cohort']==str(C3),'only actual cohort producer absence; independent live CAD untouched')
    import literal_checks as checks
    require(set(a['roles'])==set(ORDER),'all and only three completed controls')
    for role in ORDER:
        pins=a['roles'][role];require(set(pins)=={'native','audit','native_outer','audit_outer'},'six exact native/audit terminal anchors and ROOT outer scopes')
        for key in pins:verify(pins[key])
        require(pins['native']['path']==str(C3/role/'verification.json')and pins['audit']['path']==str(C3/(role+'-audit')/'acceptance.json'),'complete actual current role paths')
        checks.check_native(C3,role,p,Path(a['preparation']['path']),pins['native']['sha256'])
        checks.verify_audit(C3,role,p,Path(a['preparation']['path']),pins['audit']['sha256'])
        for key in ('native_outer','audit_outer'):
            outer=json.loads(Path(pins[key]['path']).read_text());require(outer['ROOT_verified']is True and outer['actual_command_exitcode']==0 and outer['owned_group_remaining']is False,'actual external outer0/group closure')
        for path in (C3/role/'run.owned.json',C3/role/'resource-phase.json',C3/(role+'-audit')/'reader.owned.json',C3/(role+'-audit')/'counter-checker.owned.json',C3/(role+'-audit')/'resource-phase.json'):
            life=json.loads(path.read_text());require(life['owned_group_remaining']is False,'no old cohort producer remains')
            pg=life.get('owned_pgid')
            if pg is not None:
                try:os.killpg(pg,0)
                except ProcessLookupError:pass
                else:raise ValueError('old PG live/reused; ROOT review required; never signal')
    return dict(baseline=a['baseline_archive'],ROOT_cohort_acceptance=a['ROOT_cohort_acceptance'],ROOT_no_producers=a['ROOT_no_producers'],roles=a['roles'])



def row(path,member):
    st=path.lstat();r=dict(path=str(path),member=member,mode=stat.S_IMODE(st.st_mode),device=st.st_dev,inode=st.st_ino,mtime_ns=st.st_mtime_ns,ctime_ns=st.st_ctime_ns,allocated_bytes=st.st_blocks*512)
    if stat.S_ISLNK(st.st_mode):
        target=os.readlink(path);b=target.encode();r.update(kind='symlink',target=target,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
    elif stat.S_ISDIR(st.st_mode):r.update(kind='directory',bytes=0,sha256=hashlib.sha256(b'').hexdigest())
    else:
        require(stat.S_ISREG(st.st_mode),'special file must not be silently skipped '+str(path));r.update(kind='file',**{k:v for k,v in binding(path).items()if k!='path'})
    return r


def inventory(a):
    start=time.monotonic();members=[];seen=set()
    for label,root in ROOTS.items():
        require(root.is_dir()and not root.is_symlink(),'entire exact source/stage/authority root '+str(root))
        paths=[root]+sorted(root.rglob('*'))
        for p in paths:
            members.append(row(p,label+('/'+p.relative_to(root).as_posix()if p!=root else'')));seen.add(str(p))
            if time.monotonic()-start>120:raise TimeoutError('fixed120s full original inventory')
    # Existing baseline explicitly records raw payload vs installed/historical
    # identity-only pins. There is no recursive all-JSON binary/tool collector.
    base=json.loads(Path(a['baseline_inventory']['path']).read_text());payload={r['path']:r for r in base['members']};ids={}
    for r in base.get('identity_pins',[]):
        for key in ('recorded','observed'):
            if isinstance(r.get(key),dict)and'path'in r[key]:ids[r[key]['path']]=r[key]
    refs=[];identity=[];extra=[]
    p=json.loads((C3/'preparation.json').read_text());program=json.loads(Path(p['program']['path']).read_text())
    inputs=[r for role in a['roles'].values()for r in role.values()]+[a[k]for k in ('ROOT_cohort_acceptance','ROOT_no_producers','preparation','native_resource_profile','semantic_context')]+p['runtime_sources']+p['linked_libraries']+[p[k]for k in ('model','program','reader','compiled_sources','source_plan','semantic_context','ROOT_authority','fixed_reservations')]+program['sources']+[program[k]for k in ('elf','compiler','converter')]
    inputs+=list(json.loads(Path(p['compiled_sources']['path']).read_text()).values())
    ctx=json.loads(Path(p['semantic_context']['path']).read_text());inputs+=list(ctx['closed_anchors'].values())
    # The live CAD authority used by the accounting code is an executed input.
    cad=json.loads(Path(p['fixed_reservations']['path']).read_text())['active_CAD_admission'];inputs+=[cad]
    inputs+=[json.loads(Path(cad['path']).read_text())['resource_profile']]
    for r in inputs:
        verify(r);path=r['path'];pin={k:r[k]for k in ('path','bytes','sha256')}
        if path in seen:continue
        if path in payload and all(payload[path][k]==r[k]for k in ('bytes','sha256')):refs.append(dict(recorded=pin,member=payload[path]['member']));continue
        if path in ids and all(ids[path][k]==r[k]for k in ('bytes','sha256')):identity.append(pin);continue
        require(Path(path).name!='Vbsg_nonsynth_zynq_testbench','no model duplicate or unsupported baseline model reference')
        extra.append(row(Path(path),'external/'+path.lstrip('/')));seen.add(path)
    members+=extra;require(not any(Path(r['path']).name=='Vbsg_nonsynth_zynq_testbench'for r in members),'no duplicated baseline model in closure payload')
    require(len({r['member']for r in members})==len(members),'unique complete archive members')
    counts={k:sum(r['bytes']for r in members if r['member']==k or r['member'].startswith(k+'/'))for k in (*ROOTS,'external')}
    return dict(schema='csr768-complete-cohort-lossless-inventory-v1',roots={k:str(v)for k,v in ROOTS.items()},members=members,baseline_payload_references=refs,baseline_identity_pins=identity,baseline_dependency=a['baseline_archive'],class_raw_bytes=counts,raw_FSTs=[{k:r[k]for k in ('path','bytes','sha256')}for r in members if r['kind']=='file'and r['path'].endswith('.fst')],scope='Complete D-on/D-off/I-only768 correctness; joint and physical/performance unqualified')


def unchanged(a,c):
    require(inventory(a)==c,'entire original membership/bytes/modes/links/timestamps/inodes changed')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--admission',type=Path,required=True);ap.add_argument('--admission-sha256',required=True);ap.add_argument('--phase',choices=('prepare','capture','finalize'),required=True);ap.add_argument('--inventory-sha256');ap.add_argument('--ROOT-review',type=Path);ap.add_argument('--ROOT-review-sha256');args=ap.parse_args()
    verify_source=binding(args.admission);require(verify_source['sha256']==args.admission_sha256,'exact fresh ROOT source/resource admission');a=json.loads(args.admission.read_text());require(a['schema']=='csr768-complete-cohort-closure-admission-v1'and a['ROOT_approved']is True,'DRAFT unadmitted')
    require(a['roots']=={k:str(v)for k,v in ROOTS.items()}and a['ART']==str(ART)and a['HOME_family_cap_bytes']==CAP,'exact full roots/16MiB prospective family')
    for r in a['source_inputs']:verify(r)
    guard(a);g=gates(a);lock=(C3/'acquisition.lock').open('rb');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    inv=OUT/'inventory.json';manifest=OUT/'manifest.json'
    if args.phase=='prepare':
        require(not OUT.exists(),'fresh closure namespace');c=inventory(a);guard(a);OUT.mkdir(parents=True);write(inv,c);unchanged(a,c);write(OUT/'prepared.json',dict(state='PASS inventory only;16MiB compression NOT yet admitted/measured',admission=verify_source,inventory=binding(inv),members=len(c['members']),raw_bytes=sum(r['bytes']for r in c['members']),class_raw_bytes=c['class_raw_bytes'],raw_FSTs=c['raw_FSTs']));guard(a);print(json.dumps(binding(inv)));return
    require(binding(inv)['sha256']==args.inventory_sha256,'exact ROOT-reviewed frozen inventory');c=json.loads(inv.read_text());unchanged(a,c)
    require(args.ROOT_review and binding(args.ROOT_review)['sha256']==args.ROOT_review_sha256,'fresh postinventory/postcapture ROOT review');review=json.loads(args.ROOT_review.read_text());require(review['ROOT_approved']is True and review['inventory']==binding(inv)and review['admission']==verify_source,'exact immutable ROOT review')
    if args.phase=='capture':
        require(review['allow_one_16MiB_capture']is True and not manifest.exists(),'one ROOT-reviewed inventory-based compression admission')
        record=dict(state='RUNNING complete768 three-role lossless closure',admission=verify_source,inventory=binding(inv),ROOT_inventory_review=binding(args.ROOT_review),gates=g,commands=[]);write(manifest,record);start=time.monotonic()
        def limits():
            resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(15*1024**2,)*2)
        try:
            for action,deadline in (('compress',600),('roundtrip',180)):
                remaining=780-(time.monotonic()-start);require(remaining>0,'fixed780s total archive phases');entry=dict(action=action);record['commands'].append(entry);write(manifest,record)
                try:
                    with (OUT/(action+'.log')).open('wb')as log:entry['owned']=owned.run([sys.executable,'-B',HERE/'codec.py','--inventory',inv,'--output',OUT/'whole-cohort.tar.xz','--action',action],HERE,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,min(deadline,remaining),lambda:guard(a),limits)
                except BaseException as error:entry['owned']=getattr(error,'owned_receipt',None);raise
                finally:write(manifest,record)
                require(entry['owned']['returncode']==0 and entry['owned']['failure']is None and entry['owned']['owned_group_remaining']is False,'all-member archive/readback actual0/owned closure')
            unchanged(a,c);require(gates(a)==g,'closed three-role/producers/source prerequisites unchanged');record.update(state='PASS all-member lossless 768-three-role stage/helper/ROOT-context capture; all historical evidence retained',archive=binding(OUT/'whole-cohort.tar.xz'),members=len(c['members']),raw_member_bytes=sum(r['bytes']for r in c['members']),all_originals_preserved=True,all_members_modes_links_roundtripped=True,baseline_dependency=a['baseline_archive'],unused_cohort_RUN_future_bytes=None,unused_cohort_HOME_future_bytes=None,seconds=time.monotonic()-start);write(manifest,record);guard(a)
        except BaseException as error:record.update(state='FAIL preserved; no retries/extensions/future release',error=repr(error));write(manifest,record);raise
        print(json.dumps(binding(manifest)));return
    verify(review['capture_outer']);outer=json.loads(Path(review['capture_outer']['path']).read_text());require(outer['ROOT_verified']is True and outer['actual_command_exitcode']==0 and outer['owned_group_remaining']is False and outer['capture']==binding(manifest),'actual completed capture outer0, never self-declared exit');verify(review['capture']);require(review['capture']==binding(manifest)and review['ROOT_independent_full_readback_verified']is True and review['ROOT_original_unused_cohort_future_release_authorized']is True,'separate ROOT actual complete closure/readback before any future0')
    m=json.loads(manifest.read_text());require(m['state'].startswith('PASS all-member')and m['all_originals_preserved']is True,'complete durable all-member capture');verify(m['archive'])
    require(not(OUT/'reservation-complete.json').exists(),'one final unused-future disposition')
    first=inventory(a);second=inventory(a);require(first==second==c and gates(a)==g,'two exact whole original inventories plus absence/proof unchanged')
    for r in a['source_inputs']:verify(r)
    write(OUT/'reservation-complete.json',dict(schema='csr768-complete-cohort-complete-preservation-future-disposition-v1',state='PASS ROOT-reviewed full durable three-role768 closure and double-inventory; unused current cohort/helper futures finalized only',capture=binding(manifest),ROOT_review=binding(args.ROOT_review),inventory=binding(inv),whole_original_double_inventory_equal=True,all_originals_preserved=True,baseline_dependency=a['baseline_archive'],actual_original_logical_bytes=sum(r['bytes']for r in c['members']),actual_original_allocated_bytes=sum(r['allocated_bytes']for r in c['members']),unused_cohort_RUN_future_bytes=0,unused_cohort_HOME_future_bytes=0,original_caps_unchanged=True,all_actual_bytes_still_charged=True,no_cleanup_or_model_source_change=True,completed_roles=list(ORDER),joint_not_qualified=True,unused_native_helper_HOME_future_bytes=0,unused_semantic_helper_HOME_future_bytes=0,other_CAD_mapping_BASE_reserves_unchanged=True));guard(a);print(json.dumps(binding(OUT/'reservation-complete.json')))

if __name__=='__main__':main()
