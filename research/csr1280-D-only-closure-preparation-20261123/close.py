#!/usr/bin/env python3
"""ROOT-only full D1280 stage capture; no target/reader, deletion or implicit future release."""
import argparse,fcntl,gzip,hashlib,json,os,resource,shutil,signal,stat,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
C3=Path('/run/user/1001/zp-csr1280-allslots-native-20261123-03')
H3=HERE.with_name('csr1280-allslots-native-preparation03-20261123')
PROMO=HERE.with_name('csr1280-d-audit-promotion-preparation-20261123')
PF=Path('/home/coyang/fpga-artifacts/context-resume/csr1280-d-audit-promotion-20261123')
ART=Path('/home/coyang/fpga-artifacts/context-resume/csr1280-D-only-closure-20261123');OUT=ART/'closed01'
ROOTS=dict(C3=C3,H3=H3,promotion_helper=PROMO,promotion_family=PF,closure_helper=HERE)
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


def guard(a):
    used=size(ART);require(used<=CAP and size(HERE)<=65536,'whole prospective16MiB artifact/64KiB helper caps')
    r=a['resources'];require(r['all_other_charged_reserves_included']is True,'fresh ROOT all-current reserve pricing')
    require(shutil.disk_usage(HERE).free>=r['HOME_fixed_required_free_bytes']+CAP-used+65536-size(HERE),'HOME floor+OTHER+newremaining+helperremaining')
    require(shutil.disk_usage(C3).free>=r['RUN_required_free_bytes']and shutil.disk_usage('/dev/shm').free>=r['SHM_required_free_bytes'],'all current RUN/SHM reserves unchanged')
    avail=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines()if l.startswith('MemAvailable:'))
    require(avail>=r['MemAvailable_required_bytes'],'includes encoder1GiB allowance and all other memory')


def gates(a):
    for key in ('baseline_manifest','baseline_archive','baseline_inventory','promotion','promotion_exit','ROOT_no_producers'):
        verify(a[key])
    require(a['baseline_archive']['sha256']=='344536b19857b239210e358406048c420598d65db8b0d4ff60a98d74b7dff320','exact immutable baseline archive dependency')
    base=json.loads(Path(a['baseline_manifest']['path']).read_text());require(base['state'].startswith('PASS base32')and base['archive']==a['baseline_archive']and base['inventory']==a['baseline_inventory']and base['originals_unchanged']is True,'complete full/scoped/STD baseline, no duplicated model')
    promotion=json.loads(Path(a['promotion']['path']).read_text());require(promotion['schema']=='csr1280-D-closed-audit-promotion-composite-v1'and promotion['state'].startswith('PASS promotion-only')and promotion['source_endcheck']=='PASS','actual closed D-only receipt promotion')
    exitproof=json.loads(Path(a['promotion_exit']['path']).read_text());require(exitproof['ROOT_verified']is True and exitproof['actual_command_exitcode']==0 and exitproof['completion']==a['promotion'] and exitproof['no_model_reader_checker_child']is True,'actual ROOT promotion exit proof')
    require(a['ROOT_reviewed_promotion_actual_exit0']is True and a['promotion']['path']==str(PF/'closed01/completion.json'),'actual ROOT command success, not draft or failed receipt')
    no=json.loads(Path(a['ROOT_no_producers']['path']).read_text());require(no['ROOT_verified']is True and no['all_C3_native_reader_accounting_groups_absent']is True and no['global_vendor_absent']is True,'fresh ROOT original-producer/vendor absence')
    for r in a['historical_failed_closures']:verify(r)
    for path in (C3/'d-enabled/run.owned.json',C3/'d-enabled/resource-phase.json',C3/'d-enabled-audit/reader.owned.json',C3/'d-enabled-audit/counter-checker.owned.json',C3/'d-enabled-audit/resource-phase.json'):
        life=json.loads(path.read_text());require(life['owned_group_remaining']is False,'closed exact old owned group')
        pg=life.get('owned_pgid')
        if pg is not None:
            try:os.killpg(pg,0)
            except ProcessLookupError:pass
            else:raise ValueError('old PG identity live/reused; ROOT review required; no signals')
    require(a['deferred_roles']==['d-off','i-enabled','joint1280']and a['no_completion_claim_for_deferred_roles']is True,'D only; placement failure does not qualify absent roles')
    return dict(baseline=a['baseline_archive'],promotion=a['promotion'],ROOT_no_producers=a['ROOT_no_producers'],historical_failed_closures=a['historical_failed_closures'])


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
        require(root.is_dir()and not root.is_symlink(),'entire exact source/stage/promotion root '+str(root))
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
    inputs=p['runtime_sources']+p['linked_libraries']+[p[k]for k in ('model','program','reader','compiled_sources','source_plan','semantic_context','ROOT_authority','fixed_reservations')]+program['sources']+[program[k]for k in ('elf','compiler','converter')]
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
    return dict(schema='csr1280-D-only-lossless-inventory-v1',roots={k:str(v)for k,v in ROOTS.items()},members=members,baseline_payload_references=refs,baseline_identity_pins=identity,baseline_dependency=a['baseline_archive'],class_raw_bytes=counts,raw_FSTs=[{k:r[k]for k in ('path','bytes','sha256')}for r in members if r['kind']=='file'and r['path'].endswith('.fst')],scope='D-only1280 closed correctness plus every C3/H3/promotion byte; deferred roles not qualified')


def unchanged(a,c):
    require(inventory(a)==c,'entire original membership/bytes/modes/links/timestamps/inodes changed')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--admission',type=Path,required=True);ap.add_argument('--admission-sha256',required=True);ap.add_argument('--phase',choices=('prepare','capture','finalize'),required=True);ap.add_argument('--inventory-sha256');ap.add_argument('--ROOT-review',type=Path);ap.add_argument('--ROOT-review-sha256');args=ap.parse_args()
    verify_source=binding(args.admission);require(verify_source['sha256']==args.admission_sha256,'exact fresh ROOT source/resource admission');a=json.loads(args.admission.read_text());require(a['schema']=='csr1280-D-only-closure-admission-v1'and a['ROOT_approved']is True,'DRAFT unadmitted')
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
        record=dict(state='RUNNING D-only lossless closure',admission=verify_source,inventory=binding(inv),ROOT_inventory_review=binding(args.ROOT_review),gates=g,commands=[]);write(manifest,record);start=time.monotonic()
        def limits():
            resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(15*1024**2,)*2)
        try:
            for action,deadline in (('compress',600),('roundtrip',180)):
                remaining=780-(time.monotonic()-start);require(remaining>0,'fixed780s total archive phases');entry=dict(action=action);record['commands'].append(entry);write(manifest,record)
                try:
                    with (OUT/(action+'.log')).open('wb')as log:entry['owned']=owned.run([sys.executable,'-B',HERE/'codec.py','--inventory',inv,'--output',OUT/'whole-D-only.tar.xz','--action',action],HERE,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,min(deadline,remaining),lambda:guard(a),limits)
                except BaseException as error:entry['owned']=getattr(error,'owned_receipt',None);raise
                finally:write(manifest,record)
                require(entry['owned']['returncode']==0 and entry['owned']['failure']is None and entry['owned']['owned_group_remaining']is False,'all-member archive/readback actual0/owned closure')
            unchanged(a,c);require(gates(a)==g,'closed promotion/producers/source prerequisites unchanged');record.update(state='PASS all-member lossless D1280-only stage/helper/promotion capture; original operational failures retained',archive=binding(OUT/'whole-D-only.tar.xz'),members=len(c['members']),raw_member_bytes=sum(r['bytes']for r in c['members']),all_originals_preserved=True,all_members_modes_links_roundtripped=True,baseline_dependency=a['baseline_archive'],unused_C3_RUN_future_bytes=None,unused_C3_HOME_future_bytes=None,seconds=time.monotonic()-start);write(manifest,record);guard(a)
        except BaseException as error:record.update(state='FAIL preserved; no retries/extensions/future release',error=repr(error));write(manifest,record);raise
        print(json.dumps(binding(manifest)));return
    verify(review['capture']);require(review['capture']==binding(manifest)and review['ROOT_independent_full_readback_verified']is True and review['ROOT_original_unused_C3_future_release_authorized']is True,'separate ROOT actual complete closure/readback before any future0')
    m=json.loads(manifest.read_text());require(m['state'].startswith('PASS all-member')and m['all_originals_preserved']is True,'complete durable all-member capture');verify(m['archive'])
    require(not(OUT/'reservation-complete.json').exists(),'one final unused-future disposition')
    first=inventory(a);second=inventory(a);require(first==second==c and gates(a)==g,'two exact whole original inventories plus absence/proof unchanged')
    for r in a['source_inputs']:verify(r)
    write(OUT/'reservation-complete.json',dict(schema='csr1280-D-only-complete-preservation-future-disposition-v1',state='PASS ROOT-reviewed full durable D-only closure and double-inventory; unused C3 futures finalized only',capture=binding(manifest),ROOT_review=binding(args.ROOT_review),inventory=binding(inv),whole_original_double_inventory_equal=True,all_originals_preserved=True,baseline_dependency=a['baseline_archive'],actual_original_logical_bytes=sum(r['bytes']for r in c['members']),actual_original_allocated_bytes=sum(r['allocated_bytes']for r in c['members']),unused_C3_RUN_future_bytes=0,unused_C3_HOME_future_bytes=0,original_caps_unchanged=True,all_actual_bytes_still_charged=True,no_cleanup_or_model_source_change=True,deferred_roles=a['deferred_roles'],no_completion_claim_for_deferred_roles=True));guard(a);print(json.dumps(binding(OUT/'reservation-complete.json')))

if __name__=='__main__':main()
