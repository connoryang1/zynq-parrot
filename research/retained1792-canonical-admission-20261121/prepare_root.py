#!/usr/bin/env python3
"""ROOT-only fresh RAM staging and admission; never executes a model or reader."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
STAGE=Path('/dev/shm/zp-retained1792-stream-canonical-20261121-01')
MODEL_SHA='b9f7f127121d750591513372a5d2e342046098a58984384e0f5b57b35b00b3e7'
MODEL_BYTES=15945696


def require(ok,message):
    if not ok:raise ValueError(message)


def bind(path):
    path=Path(path).resolve();digest=hashlib.sha256();size=0
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk);size+=len(chunk)
    return dict(path=str(path),bytes=size,sha256=digest.hexdigest())


def verify(row):require(bind(row['path'])==row,'input binding changed: '+row['path'])
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def reviewed_packet(path,expected_sha,facts,c):
    require(bind(path)['sha256']==expected_sha,'external review-packet SHA')
    r=json.loads(Path(path).read_text())
    require(r['schema']=='root-reviewed1792-model-bridge-v1' and r['state']=='ROOT-REVIEWED closed canonical gate plus observation clone','final reviewed closure still pending')
    require(r['checks']==dict.fromkeys(c.MODEL_CHECKS,True),'all eight root-reviewed checks required')
    for key in ('model','canonical_fullcore','compiled_sources','model_stamp','environment','linked_libraries'):
        require(r[key]==facts[key],'review packet bound canonical input: '+key)
    require(r['geometry']==c.GEOMETRY and r['schema167']==c.bind(c.OLD/'schema167.json'),'unchanged1792 geometry/raw167 schema')
    q=r['observation_qualification'];require(isinstance(q,dict),'final observation review missing');verify(q)
    qualification=json.loads(Path(q['path']).read_text())
    require(str(qualification.get('state','')).startswith('PASS'),'final observation closure must be PASS, not preserved wrong-root/awaiting state')
    return r


def namespace_and_resources(facts,c):
    sentinel=Path(facts['namespace_sentinel'])
    require(sentinel.is_dir(),'actual ROOT canonical namespace absent; no private-RAM staging')
    stat=sentinel.stat()
    require(dict(device=stat.st_dev,inode=stat.st_ino)==facts['namespace_identity'],'actual ROOT namespace identity')
    require(not STAGE.exists(),'fresh fixed stage only; no reuse/overwrite/retry')
    ram_free=shutil.disk_usage(STAGE.parent).free;home_free=shutil.disk_usage(c.HERE).free
    require(ram_free>=c.CAPS['RAM_reserve']+c.CAPS['stage_total'],'ROOT RAM1GiB plus512MiB before staging')
    require(home_free>=c.CAPS['HOME_reserve']+c.CAPS['preparation'],'HOME3GiB plus8MiB preparation')
    return dict(RAM_free_bytes=ram_free,HOME_free_bytes=home_free)


def stage(args,c):
    facts_path=HERE/'candidate.json';require(bind(facts_path)['sha256']==args.candidate_sha256,'external candidate SHA')
    facts=json.loads(facts_path.read_text())
    require(facts['model']['sha256']==MODEL_SHA and facts['model']['bytes']==MODEL_BYTES and facts['stage']==str(STAGE),'one exact canonical scoped model/stage')
    reviewed=reviewed_packet(args.review_packet,args.review_sha256,facts,c)
    for key in ('archive','model','model_gzip','canonical_fullcore','compiled_sources','model_stamp','proposal'):verify(facts[key])
    for row in facts['linked_libraries']:verify(row)
    compiled=json.loads(Path(facts['compiled_sources']['path']).read_text())
    for row in compiled['sources'].values():verify(row)
    c.original.source_bindings(Path(facts['compiled_sources']['path']))
    before_sources=c.runtime_sources()
    draft=c.HERE/'preparation.DRAFT.json';p,program=c.load(draft,c.bind(draft)['sha256'],approved=False)
    future_other=MODEL_BYTES+sum(program['elf']['bytes']+program['cases'][role]['nbf']['bytes'] for role in c.ORDER)+1024*1024
    require(future_other<=c.CAPS['other_total'],'model+all3program copies+1MiB metadata fit unchanged32MiB other cap')
    resources=namespace_and_resources(facts,c)
    STAGE.mkdir();(STAGE/'model').mkdir()
    try:
        model=STAGE/'model/Vbsg_nonsynth_zynq_testbench'
        shutil.copyfile(facts['model']['path'],model);model.chmod(0o755)
        require(bind(model)['sha256']==MODEL_SHA and model.stat().st_size==MODEL_BYTES,'exact staged model bytes')
        write(STAGE/'compiled-sources.json',compiled)
        p.update(state='ROOT-APPROVED future1792-stream complete-audit',stage=str(STAGE),model=bind(model),
            canonical_fullcore=facts['canonical_fullcore'],observation_qualification=reviewed['observation_qualification'],
            compiled_sources=bind(STAGE/'compiled-sources.json'),model_stamp=facts['model_stamp'],
            runtime_sources=before_sources,environment=facts['environment'],linked_libraries=facts['linked_libraries'])
        review=dict(reviewed,model=p['model'],compiled_sources=p['compiled_sources'],
            original_review_packet=bind(args.review_packet),original_compiled_sources=facts['compiled_sources'],
            source_candidate=bind(facts_path),archive=facts['archive'],model_gzip=facts['model_gzip'])
        write(STAGE/'model-review.json',review);p['model_approval']=bind(STAGE/'model-review.json')
        st=STAGE.stat()
        host=dict(state='ROOT-APPROVED fixed512MiB stage and source guard',stage=dict(path=str(STAGE),device=st.st_dev,inode=st.st_ino),
            runtime_sources=p['runtime_sources'],caps=c.CAPS,model=p['model'],
            RAM_free_bytes=resources['RAM_free_bytes'],
            HOME_free_bytes=resources['HOME_free_bytes'],preparation_only=True,
            original_namespace=facts['namespace_identity'],preparer=bind(__file__),source_review=bind(args.review_packet))
        write(STAGE/'host-admission.json',host);p['host_admission']=bind(STAGE/'host-admission.json')
        for row in before_sources:verify(row)
        require(c.runtime_sources()==before_sources,'driver/helper source immutable during preparation')
        for row in compiled['sources'].values():verify(row)
        out=STAGE/'preparation.json';write(out,p)
        c.load(out,bind(out)['sha256']);c.check_budget(STAGE,p)
        write(STAGE/'stage-preparation.json',dict(state='PREPARED VERIFIED ONLY no model/reader/target execution',
            preparation=bind(out),model=p['model'],runtime_sources=before_sources,preparer=bind(__file__),
            source_review=bind(args.review_packet),future_other_bytes_upper_plan=future_other))
        c.check_budget(STAGE,p)
        return out,bind(out)
    except BaseException as error:
        if (STAGE/'preparation.json').exists():(STAGE/'preparation.json').rename(STAGE/'FAILED-preparation.json')
        write(STAGE/'PREPARATION-FAIL.json',dict(state='FAIL preparation only; preserve stage, no automatic retry',error=repr(error)))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver-dir',type=Path,default=HERE.parent/'retained1792-stream-cohort-20261121')
    parser.add_argument('--candidate-sha256')
    parser.add_argument('--review-packet',type=Path)
    parser.add_argument('--review-sha256')
    parser.add_argument('--root-prepare',action='store_true')
    args=parser.parse_args()
    if not args.root_prepare:
        print('ROOT_PREPARATION_DRAFT_ONLY=1 final reviewed closure and ROOT namespace required');return
    require(all((args.candidate_sha256,args.review_packet,args.review_sha256)),'explicit candidate/review SHA anchors required')
    sys.path.insert(0,str(args.driver_dir.resolve()));c=importlib.import_module('contract')
    out,record=stage(args,c)
    print('APPROVED_PREPARATION='+str(out));print('APPROVED_PREPARATION_SHA256='+record['sha256'])
    print('NO_MODEL_READER_TARGET_EXECUTED=1')


if __name__=='__main__':main()
