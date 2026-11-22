#!/usr/bin/env python3
"""Exact sparse scratch-only source collection, no compiler/model/reader."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
SOURCE=Path('/home/coyang/zynq-parrot-linux-scratch-profile')
TOP='4dadebbfdddfe958eff432b7f87280cfb9b5d991'
BP='7566c67aad9b93f5546fcc5e258e405402a47850'
PREVIOUS=Path('/home/coyang/zynq-parrot-linux-host-observer/research/retained256-qualification-20261122')
SOURCE_CAP=4*1024**2;HELPER_CAP=8*1024**2;FLOOR=3*1024**3
V1=HERE.parent/'scratch-trace-profile-preparation-20261122'


def require(ok,message):
    if not ok:raise ValueError(message)

def size(path):return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file()) if Path(path).exists() else 0
def bind(path):
    p=Path(path);raw=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def git(repo,*args):
    repo=Path(repo);marker=repo/'.git';require(marker.is_file() or marker.is_dir(),'initialized .git before Git invocation')
    admin=Path(marker.read_text().strip().split(': ',1)[1]) if marker.is_file() else marker
    if not admin.is_absolute():admin=(repo/admin).resolve()
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')};env.update(GIT_DIR=str(admin),GIT_WORK_TREE=str(repo.resolve()))
    return subprocess.check_output(['git','-c','core.sparseCheckout=true','-c','core.sparseCheckoutCone=false',*args],cwd=repo,env=env,timeout=60)

def budget():
    used,helpers=size(SOURCE),size(HERE)+size(V1)
    require(used<=SOURCE_CAP and helpers<=HELPER_CAP,'new source4MiB/helpers8MiB caps')
    # Preserve the existing matched256 HOME reservations as well as new ones.
    oldsource=Path('/home/coyang/zp-retained256-source-20261122');durable=Path('/home/coyang/fpga-artifacts/context-resume/retained256-qualification-20261122')
    old_remaining=max(0,SOURCE_CAP-size(oldsource))+max(0,HELPER_CAP-size(PREVIOUS))+max(0,128*1024**2-size(durable))
    need=FLOOR+SOURCE_CAP-used+HELPER_CAP-helpers+old_remaining
    require(shutil.disk_usage(HERE).free>=need,'HOME3GiB plus BOTH old/new remaining allocations')
    return dict(source_bytes=used,helper_bytes=helpers,old_remaining_bytes=old_remaining,required_free_bytes=need,free_bytes=shutil.disk_usage(HERE).free)

def main():
    original=PREVIOUS/'source-plan-v4.json';plan=copy.deepcopy(json.loads(original.read_text()))
    require(bind(original)['sha256']=='a39b7e42177d3c9ed32ea77c005746a14548002ad28e5acde3c75dfe8e4ca765','fixed complete392HDL/host-include lineage')
    require(git(SOURCE,'rev-parse','HEAD').decode().strip()==TOP,'scratch-only TOP')
    require(git(SOURCE,'diff','--name-only','f4479696cbd61820bde7065a261a01d37201d323',TOP).decode().splitlines()==['import/black-parrot'],'only scratch-only gitlink composition')
    reference=Path('/home/coyang/bp-retained-scratch-coalesced-20261122')
    require(git(reference,'diff','--name-only','8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c',BP).decode().splitlines()==['bp_me/src/v/cce/bp_uce.sv'],'only scratch UCE source change')
    plan.update(schema='scratch-trace-profile-source-plan-v1',source=str(SOURCE),TOP=TOP,BP=BP,
                capacity_selection=None,prospective_run_defines=dict(BP_CACHE_MISS_TRACE=0),source_cap=SOURCE_CAP)
    plan['repositories'][0].update(commit=TOP,reference=str(SOURCE))
    plan['repositories'][0]['files']['testing/rtl/retained-advisory-trace/validate.py']={}
    for row in plan['repositories']:
        if row['relative']=='import/black-parrot':row.update(commit=BP,reference=str(reference))
        names=list(row['files']);raw=git(Path(row['reference']),'ls-tree','-l',row['commit'],'--',*names).decode().splitlines()
        actual={}
        for line in raw:
            fields,name=line.split('\t',1);mode,kind,blob,n=fields.split();require(kind=='blob','selected source blob only')
            actual[name]=dict(mode=mode,blob=blob,bytes=int(n))
        require(set(actual)==set(names),'same full source/host closure paths')
        row['files']=actual
    plan['planned_file_bytes']=sum(p['bytes'] for r in plan['repositories'] for p in r['files'].values())
    require(plan['planned_file_bytes']+4096<=SOURCE_CAP,'source cap before nested checkout')
    output=HERE/'source-plan.json'
    with output.open('x') as f:json.dump(plan,f,indent=2);f.write('\n')
    record=dict(state='RUNNING exact source-only materialization',script=bind(__file__),previous_plan=bind(original),plan=bind(output),repositories=[])
    try:
        for row in plan['repositories']:
            budget();target=SOURCE/row['relative'];ref=Path(row['reference'])
            common=Path(git(ref,'rev-parse','--git-common-dir').decode().strip())
            if not common.is_absolute():common=(ref/common).resolve()
            before=bind(common/'config')
            if not (target/'.git').is_file():
                require(not target.exists() or not any(target.iterdir()),'no foreign/partial repository')
                git(ref,'worktree','add','--detach','--no-checkout',str(target),row['commit'])
            require((target/'.git').is_file(),'actual .git before child Git')
            admin=Path((target/'.git').read_text().strip().split(': ',1)[1]).resolve()
            require((admin/(admin/'commondir').read_text().strip()).resolve()==common,'expected shared Git identity')
            require(Path((admin/'gitdir').read_text().strip()).resolve()==target/'.git','own worktree backreference')
            (admin/'config.worktree').write_text('[core]\n\tworktree = '+str(target)+'\n\tsparseCheckout = true\n\tsparseCheckoutCone = false\n')
            (admin/'info').mkdir(exist_ok=True);(admin/'info/sparse-checkout').write_text('\n'.join('/'+p for p in list(row['files'])+row['children'])+'\n')
            git(target,'read-tree','-mu','HEAD')
            require(git(target,'rev-parse','HEAD').decode().strip()==row['commit'],'exact repo HEAD')
            for name,wanted in row['files'].items():
                path=target/name;data=os.readlink(path).encode() if wanted['mode']=='120000' else path.read_bytes()
                require(len(data)==wanted['bytes'] and hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==wanted['blob'],'exact source blob '+str(path))
            require(bind(common/'config')==before,'shared common config unchanged')
            record['repositories'].append(dict(path=str(target),head=row['commit'],common_config_unchanged=before))
        for row in record['repositories']:
            require(not git(Path(row['path']),'status','--porcelain','--untracked-files=normal').decode(),'clean real source worktree '+row['path'])
        record.update(state='PASS exact scratch-only source prepared; no compiler/model/reader; final capacity pending',resources=budget(),
            files=[bind(SOURCE/r['relative']/name) for r in plan['repositories'] for name in r['files']],
            source_defaults_are_lineage_only=dict(i_lines=1792,d_lines=1792,sets=256),prospective_run_defines=dict(BP_CACHE_MISS_TRACE=0),capacity_selection=None)
    except BaseException as error:record.update(state='FAIL source preparation preserved',error=repr(error));raise
    finally:
        with (HERE/'source-materialization.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print(HERE/'source-materialization.json',record['state'])


if __name__=='__main__':main()
