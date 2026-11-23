#!/usr/bin/env python3
"""ROOT-only receipt promotion; no model/reader/checker subprocess or old producer import."""
import argparse,fcntl,hashlib,importlib.util,json,os,shutil,signal,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
C3=Path('/run/user/1001/zp-csr1280-allslots-native-20261123-03')
H3=HERE.with_name('csr1280-allslots-native-preparation03-20261123')
OUT=Path('/home/coyang/fpga-artifacts/context-resume/csr1280-d-audit-promotion-20261123/closed01')
ROLE='d-enabled'


def require(ok,msg):
    if not ok:raise ValueError(msg)


def bind(path):
    path=Path(path).resolve();h=hashlib.sha256()
    with path.open('rb')as f:
        for raw in iter(lambda:f.read(1024**2),b''):h.update(raw)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=h.hexdigest())


def verify(row):require(bind(row['path'])=={k:row[k]for k in ('path','bytes','sha256')},'immutable input '+row['path'])


def logical(root):
    total=0;todo=[os.fspath(root)]
    while todo:
        with os.scandir(todo.pop())as entries:
            for e in entries:
                if e.is_dir(follow_symlinks=False):todo.append(e.path)
                elif e.is_symlink():total+=len(os.readlink(e.path).encode())
                else:total+=e.stat(follow_symlinks=False).st_size
    return total


def stage_caps(p):
    roles=('d-enabled','d-off','i-enabled');counts={'other':0,**{'raw:'+r:0 for r in roles},**{'audit:'+r:0 for r in roles}};todo=[C3]
    while todo:
        with os.scandir(todo.pop())as entries:
            for e in entries:
                path=Path(e.path)
                if e.is_dir(follow_symlinks=False):todo.append(path);continue
                size=len(os.readlink(e.path).encode())if e.is_symlink()else e.stat(follow_symlinks=False).st_size
                parts=path.relative_to(C3).parts;top=parts[0]
                kind='raw:'+top if len(parts)==2 and parts[1]=='trace.fst'and top in roles else 'audit:'+top[:-6]if top.endswith('-audit')and top[:-6]in roles else 'other'
                counts[kind]+=size
    c=p['caps'];require(sum(counts.values())<=c['stage_total'] and counts['other']<=c['other_total'],'unchanged original whole/other output caps')
    require(sum(counts['raw:'+r]for r in roles)<=c['raw_total']and sum(counts['audit:'+r]for r in roles)<=c['audit_total'],'unchanged original raw/audit totals')
    require(all(counts['raw:'+r]<=c['raw_per_case']and counts['audit:'+r]<=c['audit_per_case']for r in roles),'unchanged per-role artifact caps')
    return counts


def source_derivation(a):
    verify(a['derivation']);d=json.loads(Path(a['derivation']['path']).read_text());verify(d['checker'])
    require(d['checker']==bind(HERE/'checks.py') and d['source_prefix']==str(H3),'fixed local literal checker/source lineage')
    correction=d['only_corrections'];require(correction==[dict(old="accepted=out/'acceptance.json'",new="accepted=out/'FAILED-acceptance.json'"),dict(old="full['sets'] == 256",new="full['actual_count_summary']['sets'] == 256")],'only allowed receipt-path and emitted sets-schema corrections')
    import ast
    copied=(HERE/'checks.py').read_text().splitlines(True)
    nodes={n.name:n for n in ast.parse(''.join(copied)).body if isinstance(n,ast.FunctionDef)}
    for row in d['functions']:
        verify(row['source']);lines=Path(row['source']['path']).read_text().splitlines(True);raw=''.join(lines[row['start']-1:row['end']])
        require(hashlib.sha256(raw.encode()).hexdigest()==row['original_span_sha256'],'exact original span '+row['name'])
        wanted=raw
        if row['name']=='semantic_verify_audit':
            for change in correction:
                require(wanted.count(change['old'])==1,'one exact corrected expression');wanted=wanted.replace(change['old'],change['new'])
        n=nodes[row['name']];actual=''.join(copied[n.lineno-1:n.end_lineno])
        require(actual==wanted and hashlib.sha256(actual.encode()).hexdigest()==row['derived_span_sha256'],'only literal authorized checker derivation '+row['name'])


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--admission',type=Path,required=True);ap.add_argument('--admission-sha256',required=True);ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    require(args.execute,'SOURCE ONLY default; explicit ROOT funding/review required')
    require(bind(args.admission)['sha256']==args.admission_sha256,'exact ROOT admission')
    a=json.loads(args.admission.read_text());require(a['schema']=='csr1280-D-audit-promotion-only-v1' and a['ROOT_approved']is True,'DRAFT cannot execute')
    require(a['OUT']==str(OUT) and a['limits']==dict(HOME_output_bytes=1024**2,source_bytes=32768,outer_seconds=120),'fresh small immutable completion only')
    require(a['ROOT_reviewed_original_failure']=='KeyError sets only after all native/semantic/counter/owned phases closed','preserve exact failed operational gate')
    require(not OUT.exists() and logical(HERE)<=32768,'fresh output and bounded whole helper')
    def caught(s,f):raise RuntimeError('promotion-only deadline/signal '+str(s))
    handlers={s:signal.signal(s,caught)for s in (signal.SIGINT,signal.SIGTERM,signal.SIGALRM,signal.SIGHUP)};signal.alarm(120)
    def guard():
        for path,key in ((HERE,'HOME_required_free_bytes'),(C3,'RUN_required_free_bytes'),(Path('/dev/shm'),'SHM_required_free_bytes')):
            require(type(a['resources'][key])is int and a['resources'][key]>=0,'fresh explicit resource requirement')
            require(shutil.disk_usage(path).free>=a['resources'][key],'fresh ROOT remaining-reserve floor '+key)
        if OUT.parent.exists():require(logical(OUT.parent)<=1024**2,'oneMiB entire completion family including ROOT authority/logs')
    started=time.monotonic();lock=None
    try:
        guard();source_derivation(a)
        lock=(C3/'acquisition.lock').open('rb');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for row in a['source_inputs']:verify(row)
        require(bind(__file__)in a['source_inputs'],'exact promotion worker')
        for key,path in (('preparation',C3/'preparation.json'),('failed_acceptance',C3/'d-enabled-audit/FAILED-acceptance.json')):
            require(a[key]['path']==str(path),'fixed original closed input path '+key);verify(a[key])
        before=dict(preparation=bind(C3/'preparation.json'),failed_acceptance=bind(C3/'d-enabled-audit/FAILED-acceptance.json'))
        p=json.loads((C3/'preparation.json').read_text());require(p['schema']=='csr1280-complete-allslots-v1' and p['stage']==str(C3),'actual03 source preparation')
        require(p['model']['sha256']=='bc6f17f4be2140071df2a23b9efcbdc75b30ce41d48b39c76b80019942e1e445','actual current1280 scoped model')
        require(p['caps']['stage_total']==128*1024**2 and p['caps']['raw_per_case']==24*1024**2 and p['caps']['raw_total']==72*1024**2 and p['caps']['audit_per_case']==8*1024**2 and p['caps']['audit_total']==24*1024**2 and p['caps']['other_total']==24*1024**2,'all original artifact caps unchanged')
        before_caps=stage_caps(p)
        for row in p['runtime_sources']+p['linked_libraries']+[p[k]for k in ('model','program','reader','compiled_sources','source_plan','semantic_context','ROOT_authority','fixed_reservations')]:verify(row)
        require(p['source_plan']['path']==str(H3/'source-plan.json'),'exact executed03 helper source contract')
        require(p['semantic_context']['sha256']=='55afbe1369bb4ca4ab7797cef4d77757963173964324a795bea903ecc280d75e','exact qualified1280 context')
        for row in json.loads(Path(p['compiled_sources']['path']).read_text()).values():verify(row)
        spec=importlib.util.spec_from_file_location('promotion_literal_checks',HERE/'checks.py');checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
        receipt=checks.verify_audit(C3,ROLE,p,C3/'preparation.json',a['failed_acceptance']['sha256'])
        require(before==dict(preparation=bind(C3/'preparation.json'),failed_acceptance=bind(C3/'d-enabled-audit/FAILED-acceptance.json')),'original failed/source receipts unchanged')
        for row in a['source_inputs']:verify(row)
        require(stage_caps(p)==before_caps,'closed original stage sizes unchanged');require(bind(args.admission)['sha256']==args.admission_sha256,'ROOT admission unchanged');guard();OUT.mkdir(parents=True,exist_ok=False)
        report=dict(schema='csr1280-D-closed-audit-promotion-composite-v1',state='PASS promotion-only existing closed D1280 native/full167 semantic/counter/owner/sealed checks; original audit helper failure preserved',admission=bind(args.admission),derivation=bind(HERE/'derivation.json'),original_inputs=before,accepted_original_receipt=receipt,original_failure='KeyError sets in final receipt validator only; original FAILED-acceptance.json retained verbatim',source_endcheck='PASS',not_valid_without_ROOT_actual_exit0=True,original_stage_cap_charges=before_caps,no_model_reader_checker_subprocess_or_original_writes=True,seconds=time.monotonic()-started,scope='Actual D-only1280 simulation correctness only. No D-off/I-on/joint1280 completion or physical/fit/performance claim.')
        (OUT/'completion.json').write_text(json.dumps(report,indent=2)+'\n');guard();print(json.dumps(bind(OUT/'completion.json')))
    finally:
        signal.alarm(0)
        if lock is not None:lock.close()
        for s,h in handlers.items():signal.signal(s,h)

if __name__=='__main__':main()
