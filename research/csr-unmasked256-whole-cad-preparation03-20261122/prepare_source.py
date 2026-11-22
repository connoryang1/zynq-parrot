#!/usr/bin/env python3
"""ROOT-only private-clone FPGA source/readiness; no vendor or launcher."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
SOURCE=Path('/dev/shm/zp-linux-csr-unmasked256-fpga-source-20261122-03')
NATIVE=Path('/home/coyang/zynq-parrot-csr-unmasked256-profile-20261122')
NATIVE_ROOT=Path('/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source')
ART=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fpga-preparation-20261122/preparation03')
PROOF=ART/'native-proof'
AUTHORITY=None
AUTHORITY_SHA=None
PREVIOUS_SOURCES=[Path('/dev/shm/zp-linux-csr-unmasked256-fpga-source-20261122-'+n) for n in ('01','02')]
FAMILY_ART=ART.parent
PREVIOUS_HELPERS=[HERE.parent/n for n in ('csr-unmasked256-whole-cad-preparation-20261122','csr-unmasked256-whole-cad-preparation02-20261122')]
R8PLAN=Path('/home/coyang/zynq-parrot-linux-host-observer/research/borrow-fpga-source-preparation-20261122/actual02/plan.json')
R8PLAN_SHA='3548165a653cb20ec626f5f1353f7cb8802fd008c45c5d05b78803c098cc9547'
TOP='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd'
BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
OPS=Path('/home/coyang/zynq-parrot-linux-capacity')
SHARED=Path('/home/coyang/zynq-parrot')
OWNED=HERE/'software_owned_v2.py'
SOURCE_CAP=128*1024**2
OUTPUT_CAP=8*1024**2
FLOOR=512*1024**2
KEEP={'ci','codex-skills','cosim','import','software','testing','tools'}

def require(ok,message):
    if not ok:raise RuntimeError(message)
def bind(p):
    p=Path(p);b=p.read_bytes()
    return dict(path=str(p.resolve()),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def git_env(repo):
    marker=repo/'.git';require(marker.is_file() or marker.is_dir(),'initialized Git marker before Git: '+str(repo))
    admin=Path(marker.read_text().strip().split(': ',1)[1]) if marker.is_file() else marker
    if not admin.is_absolute():admin=(repo/admin).resolve()
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_DIR=str(admin),GIT_WORK_TREE=str(repo))
    return env,admin
def git(repo,*args):
    env,_=git_env(repo)
    return subprocess.check_output(['git','-c','core.sparseCheckout=true','-c','core.sparseCheckoutCone=false',*args],cwd=repo,env=env,timeout=60)
def listing(repo,commit,top=False):
    out=[]
    for line in git(repo,'ls-tree','-rl',commit).decode().splitlines():
        fields,name=line.split('\t',1);mode,kind,blob,n=fields.split()
        p=PurePosixPath(name)
        if kind=='blob' and (not top or len(p.parts)==1 or p.parts[0] in KEEP):
            out.append(dict(name=name,mode=mode,blob=blob,bytes=int(n)))
    return out
def size(root):
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink()) if root.exists() else 0
def plan():
    require(bind(R8PLAN)['sha256']==R8PLAN_SHA,'exact validatedR8 source-repository blueprint')
    old=json.loads(R8PLAN.read_text())
    from contracts import source_authority
    authority=source_authority(AUTHORITY)
    native=json.loads((PROOF/'session.json').read_text())
    require(native['source_tree_baseline']==TOP and native['source_bp']==BP,'exact new CSR native source')
    require(git(NATIVE,'diff','--name-only','1008854d30e5d923c86c3232fc22af039467d552..'+TOP).decode().splitlines()==['cosim/black-parrot-example/Makefile.hardware','import/black-parrot'],'only reviewed CSR filelist/gitlink integration')
    repos=[]
    for i,r in enumerate(old['repositories']):
        relative=r['relative'];ref=NATIVE if i==0 else Path(r['reference']);commit=TOP if i==0 else BP if relative=='import/black-parrot' else r['commit'];files=listing(ref,commit,i==0)
        repos.append(dict(relative=relative,reference=str(ref),commit=commit,files=files))
    require(repos[0]['commit']==TOP and next(r for r in repos if r['relative']=='import/black-parrot')['commit']==BP,'fixed source identities')
    for r in repos[1:]:
        parent=max((p for p in repos if p['relative']=='.' or r['relative'].startswith(p['relative']+'/')),key=lambda x:len(x['relative']))
        local=str(Path(r['relative']).relative_to(parent['relative']))
        row=git(Path(parent['reference']),'ls-tree',parent['commit'],'--',local).decode().split()
        require(row[:3]==['160000','commit',r['commit']],'exact parent gitlink '+r['relative'])
    n=sum(f['bytes'] for r in repos for f in r['files'])
    require(n<SOURCE_CAP,'tracked source capacity before materialization')
    return dict(state='PLANNED only; ROOT execution required',source=str(SOURCE),TOP=TOP,BP=BP,repositories=repos,tracked_bytes=n,source_cap=SOURCE_CAP,output_cap=OUTPUT_CAP,shm_floor=FLOOR,source_artifacts=['private local shared-object clones/config; no linked worktrees','no native source mutation','no source revision advancement/network','same six critical gitlinks plus replicant and riscvdbg'])

def main():
    global AUTHORITY,AUTHORITY_SHA
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute-root',action='store_true');ap.add_argument('--authority',type=Path,required=True);ap.add_argument('--authority-sha256',required=True);a=ap.parse_args()
    require(bind(a.authority)['sha256']==a.authority_sha256,'exact ROOT source authority')
    AUTHORITY=a.authority
    AUTHORITY_SHA=a.authority_sha256
    q=plan()
    if not a.execute_root:
        print(json.dumps({k:v for k,v in q.items() if k!='repositories'},indent=2));return
    require(not SOURCE.exists(),'fresh source required; preserve any partial attempt')
    out=ART/'actual01';out.mkdir(parents=True,exist_ok=False)
    write(out/'plan.json',q);record=dict(state='RUNNING source-only',script=bind(__file__),authority=bind(AUTHORITY),plan=bind(out/'plan.json'),commands=[],repositories=[])
    started=time.monotonic()
    def guard():
        require(bind(AUTHORITY)['sha256']==AUTHORITY_SHA,'ROOT source authority unchanged')
        require(time.monotonic()-started<=600,'fixed600s source preparation deadline')
        used=size(SOURCE)+sum(size(p) for p in PREVIOUS_SOURCES);output=size(FAMILY_ART)
        require(used<=SOURCE_CAP and output<=OUTPUT_CAP,'source128MiB/helper8MiB caps')
        from contracts import source_resources
        source_resources(AUTHORITY,used,output,size(HERE)+sum(size(p) for p in PREVIOUS_HELPERS))
    require(bind(OWNED)['sha256']=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5','qualified ownership helper')
    spec=importlib.util.spec_from_file_location('source_owned',OWNED);owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned)
    def run(label,argv,cwd,env):
        entry=dict(label=label,argv=list(map(str,argv)),cwd=str(cwd));record['commands'].append(entry);life=None
        try:
            with (out/(label+'.log')).open('wb') as log:life=owned.run(entry['argv'],cwd,env,log,120,guard,lambda:None)
        except BaseException as e:life=getattr(e,'owned_receipt',dict(failure=repr(e)));raise
        finally:entry.update(ownership=life,log=bind(out/(label+'.log')));write(out/'session.json',record)
        require(life['returncode']==0 and not life['owned_group_remaining'],'source/readiness command failed '+label)
    native_before={r['reference']:git(Path(r['reference']),'status','--porcelain','--untracked-files=no') for r in q['repositories']}
    try:
        for i,r in enumerate(q['repositories']):
            guard();ref=Path(r['reference']);target=SOURCE/r['relative'];env,admin=git_env(ref)
            common=Path(git(ref,'rev-parse','--git-common-dir').decode().strip())
            if not common.is_absolute():common=(ref/common).resolve()
            before=bind(common/'config')
            require(not target.exists() or not any(target.iterdir()),'no foreign/nonempty target '+str(target))
            clone_env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
            # Proven materializer contract: clone COMMON repository with clean
            # Git environment and neutral cwd. Explicit reference identity is
            # ONLY for read/config calls, never for git clone destination.
            run('clone-'+str(i),['git','clone','--shared','--no-checkout','--no-recurse-submodules',common,target],out,clone_env)
            ownenv,ownadmin=git_env(target)
            require(ownadmin.resolve()==(target/'.git').resolve() and ownadmin.is_dir(),'private clone Git directory')
            require(not (ownadmin/'commondir').exists(),'private config must not share common worktree config')
            run('pin-'+str(i),['git','update-ref','--no-deref','HEAD',r['commit']],target,ownenv)
            # HEAD becomes detached at the exact object without touching a
            # source ref or native config. Sparse checkout is command-local.
            (ownadmin/'info').mkdir(exist_ok=True)
            patterns='/*\n!/*/\n'+''.join('/'+n+'/\n' for n in sorted(KEEP)) if i==0 else '/*\n'
            (ownadmin/'info/sparse-checkout').write_text(patterns)
            run('checkout-'+str(i),['git','-c','core.sparseCheckout=true','-c','core.sparseCheckoutCone=false','read-tree','-mu','HEAD'],target,ownenv)
            require(git(target,'rev-parse','HEAD').decode().strip()==r['commit'],'exact materialized HEAD')
            require(bind(common/'config')==before,'shared common config unchanged')
            record['repositories'].append(dict(path=str(target),head=r['commit'],native_common_config_unchanged=before,private_git_dir=str(ownadmin),private_config=bind(ownadmin/'config'),object_alternates_present=(ownadmin/'objects/info/alternates').is_file(),object_alternates=(ownadmin/'objects/info/alternates').read_text().splitlines() if (ownadmin/'objects/info/alternates').is_file() else [],own_object_packs=[dict(path=str(p),bytes=p.stat().st_size) for p in sorted((ownadmin/'objects/pack').glob('*')) if p.is_file()]))
        files=[]
        for r in q['repositories']:
            for f in r['files']:
                p=SOURCE/r['relative']/f['name'];raw=os.readlink(p).encode() if f['mode']=='120000' else p.read_bytes()
                require(len(raw)==f['bytes'] and hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==f['blob'],'exact tracked blob '+str(p))
                files.append(dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),mode=f['mode']))
        write(out/'source-files.json',files);record['source_files']=bind(out/'source-files.json')
        (SOURCE/'install').mkdir();(SOURCE/'riscv/bootrom').mkdir(parents=True)
        for name in ('bin','include','lib','share'):
            require((SHARED/'install'/name).is_dir(),'prepared tool directory '+name)
            (SOURCE/'install'/name).symlink_to(SHARED/'install'/name,target_is_directory=True)
        # Generated PLIC and bootrom are private ignored copies. No rule can
        # regenerate or overwrite the shared originals through these paths.
        private=[]
        boot=SHARED/'riscv/bootrom/bootrom.none.riscv'
        dest=SOURCE/'riscv/bootrom/bootrom.none.riscv';shutil.copy2(boot,dest)
        private.append(dict(original=bind(boot),copy=bind(dest)))
        for p in sorted((SHARED/'install/gen/v/rv_plic/rtl').rglob('*')):
            if p.is_file():
                dest=SOURCE/'install/gen/v/rv_plic/rtl'/p.relative_to(SHARED/'install/gen/v/rv_plic/rtl')
                dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
                private.append(dict(original=bind(p),copy=bind(dest)))
        require(len(private)>1,'actual generated PLIC private copies')
        for row in private:require(all(row['original'][k]==row['copy'][k] for k in ('bytes','sha256')),'private generated bytes unchanged')
        write(out/'private-generated-inputs.json',private);record['private_generated_inputs']=bind(out/'private-generated-inputs.json')
        aux={SHARED/'install/bin/riscv64-unknown-elf-objcopy',SHARED/'install/include/boost/coroutine2/all.hpp'}
        aux.update((SHARED/'install/lib')/('libboost_'+n+'.so.1.72.0') for n in ('context','coroutine','system'))
        auxiliary=[dict(link_path=str(p),binding=bind(p)) for p in sorted(aux)]
        write(out/'auxiliary.json',auxiliary);record['auxiliary']=bind(out/'auxiliary.json')
        actual=json.loads((PROOF/'actual-source-list.json').read_text());bridge=[]
        from contracts import GHOST
        exclusions=[]
        require(actual['sources'],'actual new CSR source-list must be nonempty')
        for p,r in actual['sources'].items():
            old=Path(p)
            if old==GHOST:
                require(all(bind(GHOST)[k]==r[k] for k in ('bytes','sha256')),'exact simulation-only ghost binding')
                exclusions.append(dict(native=p,reason='simulation-only bind assertion; intentionally absent from production FPGA filelist',binding=bind(GHOST)))
                continue
            try:new=SOURCE/old.relative_to(NATIVE_ROOT)
            except ValueError:new=old
            b=bind(new);require(all(b[k]==r[k] for k in ('bytes','sha256')),'native/FPGA path-normalized consumed bytes '+p)
            bridge.append(dict(native=p,fpga=str(new),bytes=b['bytes'],sha256=b['sha256']))
        require(len(exclusions)==1 and len(bridge)+len(exclusions)==len(actual['sources']),'all current native consumed inputs, one exact simulation-only exclusion')
        write(out/'simulation-only-exclusion.json',exclusions);record['simulation_only_exclusion']=bind(out/'simulation-only-exclusion.json')
        write(out/'consumed-source-bridge.json',bridge);record['consumed_source_bridge']=bind(out/'consumed-source-bridge.json')
        wrapper=SOURCE/'import/basejump_stl/bsg_mem/bsg_mem_1r1w_sync.sv'
        require(re.search(r'parameter\s+ram_style_p',wrapper.read_text()) is not None,'real topBSG wrapper ram_style_p')
        env={k:v for k,v in os.environ.items() if not k.startswith(('GIT_','FPGA_','BP_')) and k not in ('NUM_THREADS','NUM_CONTEXTS','CFG')};env['ZP_REPO_DIR']=str(SOURCE)
        run('readiness',['bash',OPS/'codex-skills/bp-fpga-synthesis/scripts/check_build_ready.sh'],SOURCE,env)
        require((out/'readiness.log').read_text().rstrip().endswith('BUILD READY'),'actual maintained readiness PASS')
        argv=['make','-n','-C',SOURCE/'cosim/black-parrot-example/vivado','fpga_build','pack_bitstream','BOARDNAME=pynqz2','VIVADO_VERSION=2024.2','VIVADO_MODE=batch','CFG=e_bp_unicore_zynqparrot_prefetch16k_cfg','THREADS=8','ACLK_MHZ=20','BP_CACHE_MISS_TRACE=0','VIVADO_RUN='+str(OPS/'codex-skills/bp-fpga-synthesis/scripts/run_vivado_2024_2.sh'),'ZP_INSTALL_DIR='+str(SOURCE/'install'),'ZP_RISCV_DIR='+str(SOURCE/'riscv')]
        run('make-dryrun',argv,SOURCE,env)
        for r in q['repositories']:
            require(git(Path(r['reference']),'status','--porcelain','--untracked-files=no')==native_before[r['reference']],'native source remains unchanged')
            require(not git(SOURCE/r['relative'],'status','--porcelain','--untracked-files=no'),'new source tracked bytes clean')
        for r in record['repositories']:
            old=r['native_common_config_unchanged'];require(bind(old['path'])==old,'native/common config unchanged through complete readiness')
        for r in auxiliary:require(bind(r['link_path'])==r['binding'],'auxiliary unchanged through readiness')
        for r in private:
            require(bind(r['original']['path'])==r['original'] and bind(r['copy']['path'])==r['copy'],'private/generated original unchanged through readiness')
        record.update(state='PASS private-clone exact FPGA source/readiness/static Make dryrun; no CAD launch',source=str(SOURCE),TOP=TOP,BP=BP,top_bsg_wrapper=bind(wrapper),geometry='Exact new CSR fullcore source bridge; all actual consumed production bytes identical; exact ghost excluded, no old396/392 assumptions',dimension_overrides='Explicit empty NUM_THREADS/NUM_CONTEXTS for static named configuration; native/literal geometry remains2/4',elapsed_seconds=time.monotonic()-started)
    except BaseException as e:record.update(state='FAIL source preparation preserved; no CAD launch',error=repr(e));raise
    finally:write(out/'session.json',record)
    print(json.dumps(dict(state=record['state'],receipt=bind(out/'session.json')),indent=2))

if __name__=='__main__':main()
