#!/usr/bin/env python3
"""ROOT-only sparse local source adapter; clean clone environment, optional alternates."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
sys.dont_write_bytecode=True
import budget
HERE=Path(__file__).resolve().parent;SOURCE=budget.BASE/'source';PREVIOUS=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fullcore-preparation-20261122/preparation02')
TOP='1b24c915ed628f6d47a382b3aa89fb662884e1a1'
PARENT1280='88ab04dfcc508176cc977096ca0c132299a8a460'
PARENT1536='a8fbd5fa6911160ab0845d75c6096549806af7b7'
REFERENCE_SOURCE=Path('/run/user/1001/zp-csr-unmasked1280-fullcore-20261122-01/source')
FLOW_BASE='59ee4cb119c8eacc364a0e88a949a1b3df70a4bf'
BASE256='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd';BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
TOP_SEED=Path('/home/coyang/zynq-parrot-csr-opt-area768-20261123')
GHOST=Path('/home/coyang/zynq-parrot-linux-capacity/research/csr-unmasked-integration-preparation-20261122/integration-contract.sv')
FLOOR=2*1024**3;require=budget.require;bind=budget.bind;size=budget.size
sys.path.insert(0,str(PREVIOUS));import software_owned_v2 as owned
def git_env(repo):
 marker=Path(repo)/'.git';require(marker.is_dir() or marker.is_file(),'explicit initialized Git before invocation')
 admin=Path(marker.read_text().strip().split(': ',1)[1]) if marker.is_file() else marker
 if not admin.is_absolute():admin=(Path(repo)/admin).resolve()
 env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')};env.update(GIT_DIR=str(admin),GIT_WORK_TREE=str(repo));return env,admin
def git(repo,*args):return subprocess.check_output(['git',*args],cwd=repo,env=git_env(repo)[0],timeout=60)
def plan():
 require(bind(PREVIOUS/'source-plan.json')['sha256']=='71ebe9cf3c0d7a0b57cc6aa4253f9b9ce5feb3df802d396359407f16b5229ab2','fixed525file source blueprint')
 p=json.loads((PREVIOUS/'source-plan.json').read_text())
 flow_names=git(TOP_SEED,'diff','--name-only',BASE256,FLOW_BASE).decode().splitlines()
 require(flow_names==['cosim/mk/Makefile.vivado','cosim/tcl/vivado-utils.tcl'],'exact two opt-only selector files')
 require(git(TOP_SEED,'rev-parse',TOP+'^').decode().strip()==PARENT1280 and git(TOP_SEED,'rev-parse',PARENT1280+'^').decode().strip()==PARENT1536 and git(TOP_SEED,'rev-parse',PARENT1536+'^').decode().strip()==FLOW_BASE and git(TOP_SEED,'rev-parse',FLOW_BASE+'^').decode().strip()==BASE256,'exact source parent chain')
 names=git(TOP_SEED,'diff','--name-only',FLOW_BASE,TOP).decode().splitlines()
 require(names==['cosim/black-parrot-example/Makefile.design'],'ONLY two capacity default lines after opt selector')
 before=git(TOP_SEED,'show',FLOW_BASE+':'+names[0]);after=git(TOP_SEED,'show',TOP+':'+names[0]);require(after==before.replace(b'BP_RETAINED_I_LINES ?= 256',b'BP_RETAINED_I_LINES ?= 768').replace(b'BP_RETAINED_D_LINES ?= 256',b'BP_RETAINED_D_LINES ?= 768'),'exact two768 substitutions')
 require(git(TOP_SEED,'diff','--name-only',PARENT1280,TOP).decode().splitlines()==names,'768 child changes only two capacity defaults')
 parent=git(TOP_SEED,'show',PARENT1280+':'+names[0]);require(after==parent.replace(b'BP_RETAINED_I_LINES ?= 1280',b'BP_RETAINED_I_LINES ?= 768').replace(b'BP_RETAINED_D_LINES ?= 1280',b'BP_RETAINED_D_LINES ?= 768'),'exact1280-to768 child bytes')
 for ref in (BASE256,FLOW_BASE,PARENT1536,PARENT1280,TOP):require(git(TOP_SEED,'ls-tree',ref,'--','import/black-parrot').decode().split()[:3]==['160000','commit',BP],'unchanged exact BP1e7 gitlink')
 require(git(TOP_SEED,'diff','--name-only',BASE256,TOP).decode().splitlines()==sorted(names+flow_names),'no HDL/source/fileset changes beyond exact three files')
 p.update(source=str(SOURCE),TOP=TOP,BP=BP)
 for previous in p['repositories']:
  if previous['relative']:previous['reference']=str(REFERENCE_SOURCE/previous['relative'])
 r=p['repositories'][0];r.update(reference=str(TOP_SEED),commit=TOP)
 for path in names+flow_names:
  line=git(TOP_SEED,'ls-tree','-l',TOP,'--',path).decode().split();r['files'][path]=dict(mode=line[0],blob=line[2],bytes=int(line[3]))
 return p
def verify():
 p=json.loads((budget.BASE/'source-plan.json').read_text());r=json.loads((budget.BASE/'source-preparation.json').read_text());require(r['state'].startswith('PASS'),'actual source preparation');require(bind(budget.BASE/'source-plan.json')==r['plan'],'immutable new source plan')
 for repo in p['repositories']:
  root=SOURCE/repo['relative'];require((root/'.git').is_dir() and git(root,'rev-parse','HEAD').decode().strip()==repo['commit'],'private exact source HEAD')
  require(not git(root,'status','--porcelain','--untracked-files=normal').decode(),'source tracked/untracked cleanliness')
  for name,w in repo['files'].items():
   f=root/name;b=os.readlink(f).encode() if w['mode']=='120000' else f.read_bytes();require(len(b)==w['bytes'] and hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==w['blob'],'source blob '+str(f))
 require(bind(GHOST)['sha256']=='1754071b0512ab5974219a7c9c7d0d834e20ec008405388b16efeeed3f17b3ec','same executed simulation-only contract')
 return r
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--admission',type=Path,required=True);a.add_argument('--admission-sha256',required=True);a.add_argument('--prepare-source',action='store_true',required=True);x=a.parse_args();authority=budget.configure(x.admission,x.admission_sha256);require('source-materialization' in authority['actions'],'ROOT source action');budget.check();p=plan();require(not budget.BASE.exists(),'fresh new768 source; no256 mutation')
 require(Path('/run/user/1001/zp-csr-unmasked1280-fullcore-20261122-01/full01/session.json').is_file(),'ROOT host namespace')
 # Validate parent Gitlink objects before any child clone.
 for r in p['repositories']:
  git(Path(r['reference']),'cat-file','-e',r['commit'])
  if r['relative']:
   parent=max((q for q in p['repositories'] if q['relative']=='' or r['relative'].startswith(q['relative']+'/')),key=lambda q:len(q['relative']));rel=r['relative'][len(parent['relative']):].lstrip('/');require(git(Path(parent['reference']),'ls-tree',parent['commit'],'--',rel).decode().split()[:3]==['160000','commit',r['commit']],'unchanged nested gitlink')
 budget.BASE.mkdir();SOURCE.mkdir();(budget.BASE/'source-plan.json').write_text(json.dumps(p,indent=2)+'\n');rec=dict(state='RUNNING source only',plan=bind(budget.BASE/'source-plan.json'),repositories=[],commands=[]);started=time.monotonic()
 def save():(budget.BASE/'source-preparation.json').write_text(json.dumps(rec,indent=2)+'\n')
 def run(argv,cwd,env):
  require(time.monotonic()-started<600,'600s source phase');entry=dict(argv=list(map(str,argv)));rec['commands'].append(entry);save()
  try:
   with (budget.BASE/('source-%02d.log'%(len(rec['commands'])-1))).open('wb') as f:entry['ownership']=owned.run(entry['argv'],cwd,env,f,120,budget.check,None)
  except BaseException as e:entry['ownership']=getattr(e,'owned_receipt',None);raise
  finally:save()
  require(entry['ownership']['returncode']==0 and not entry['ownership']['owned_group_remaining'],'source command complete')
 try:
  for r in p['repositories']:
   ref=Path(r['reference']);root=SOURCE/r['relative'];root.parent.mkdir(parents=True,exist_ok=True);common=Path(git(ref,'rev-parse','--git-common-dir').decode().strip())
   if not common.is_absolute():common=(ref/common).resolve()
   unchanged=bind(common/'config');env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
   run(['git','clone','--shared','--no-checkout','--no-recurse-submodules',common,root],budget.BASE,env)
   own,admin=git_env(root);require(admin.is_dir() and not (admin/'commondir').exists(),'private clone config, no linked worktree')
   run(['git','update-ref','--no-deref','HEAD',r['commit']],root,own)
   (admin/'info').mkdir(exist_ok=True);(admin/'info/sparse-checkout').write_text('\n'.join('/'+n for n in list(r['files'])+r['children'])+'\n')
   run(['git','-c','core.sparseCheckout=true','-c','core.sparseCheckoutCone=false','read-tree','-mu','HEAD'],root,own)
   require(bind(common/'config')==unchanged,'source common config untouched');alts=admin/'objects/info/alternates';rec['repositories'].append(dict(path=str(root),head=r['commit'],private_git_dir=str(admin),optional_alternates=bind(alts) if alts.is_file() else None))
  rec.update(state='PASS private exact768 source+opt-only selector, no compiler/model/reader',external_inputs=[bind(GHOST)]);save();verify();budget.check()
 except BaseException as e:rec.update(state='FAIL source preparation preserved',error=repr(e));save();raise
 print(budget.BASE/'source-preparation.json')
if __name__=='__main__':main()
