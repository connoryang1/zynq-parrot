#!/usr/bin/env python3
"""ROOT-only exact private sparse clones; source and Make-n only, no build."""
import argparse,hashlib,json,os,resource,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
import budget,software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
SOURCE=budget.BASE/'source'
TOP='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd'
BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
PREVIOUS=HERE
FLOOR=2415919104
GHOST=Path('/home/coyang/zynq-parrot-linux-capacity/research/csr-unmasked-integration-preparation-20261122/integration-contract.sv')
require=budget.require;bind=budget.bind;size=budget.size

def git(repo,*args):
 repo=Path(repo);marker=repo/'.git';require(marker.is_file() or marker.is_dir(),'initialized .git required, never parent discovery')
 admin=Path(marker.read_text().strip().split(': ',1)[1]) if marker.is_file() else marker
 if not admin.is_absolute():admin=(repo/admin).resolve()
 env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')};env.update(GIT_DIR=str(admin),GIT_WORK_TREE=str(repo.resolve()))
 return subprocess.check_output(['git',*args],cwd=repo,env=env,timeout=60)

def verify():
 plan=json.loads((HERE/'source-plan.json').read_text());record=json.loads((budget.BASE/'source-preparation.json').read_text())
 require(record['state'].startswith('PASS private source'),'actual source preparation required')
 require(bind(HERE/'source-plan.json')==record['plan'],'source plan drift')
 for r in plan['repositories']:
  target=SOURCE/r['relative'];require((target/'.git').is_dir(),'actual private clone marker')
  require(git(target,'rev-parse','HEAD').decode().strip()==r['commit'],'source HEAD')
  require(not git(target,'status','--porcelain','--untracked-files=normal').decode(),'source clean')
  for n,w in r['files'].items():
   p=target/n;raw=os.readlink(p).encode() if w['mode']=='120000' else p.read_bytes()
   require(len(raw)==w['bytes'] and hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==w['blob'],'source blob '+str(p))
 for r in record['external_inputs']:require(bind(r['path'])==r,'external support/software drift')
 return record

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--admission',type=Path,required=True);ap.add_argument('--admission-sha256',required=True);ap.add_argument('--prepare-source',action='store_true',required=True);a=ap.parse_args()
 authority=budget.configure(a.admission,a.admission_sha256);require('source-materialization' in authority['actions'],'ROOT source authority');budget.check();require(not budget.BASE.exists(),'fresh ROOT source stage; preserve failures')
 # Explicit host namespace sentinel, not an agent-private RAM allocation.
 require(Path('/run/user/1001/zp-retained-borrow256-trace0-fullcore-20261122-01/full01/session.json').is_file(),'real ROOT host namespace')
 plan=json.loads((HERE/'source-plan.json').read_text());require(plan['TOP']==TOP and plan['BP']==BP and plan['source']==str(SOURCE),'candidate source pin')
 # Parent Gitlinks are validated from objects before ANY child Git/clone invocation.
 for r in plan['repositories']:
  require(git(r['reference'],'cat-file','-t',r['commit']).strip()==b'commit','selected commit exists in initialized seed')
  if r['relative']:
   parent=max((q for q in plan['repositories'] if r['relative'].startswith(q['relative']+'/') or q['relative']==''),key=lambda q:len(q['relative']))
   rel=r['relative'][len(parent['relative']):].lstrip('/');line=git(parent['reference'],'ls-tree',parent['commit'],'--',rel).decode().split()
   require(len(line)==4 and line[:3]==['160000','commit',r['commit']],'exact parent gitlink '+r['relative'])
 budget.BASE.mkdir();SOURCE.mkdir();record=dict(state='RUNNING private source preparation only',plan=bind(HERE/'source-plan.json'),admission=bind(a.admission),commands=[],repositories=[],external_inputs=[bind(GHOST)])
 def save(): (budget.BASE/'source-preparation.json').write_text(json.dumps(record,indent=2)+'\n')
 def command(argv):
  i=len(record['commands']);log=budget.BASE/('source-%02d.log'%i);row=dict(argv=list(map(str,argv)));record['commands'].append(row);save()
  try:
   with log.open('wb') as f:row['ownership']=owned.run(row['argv'],budget.BASE,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),f,120,budget.check,lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
  except BaseException as e:row['ownership']=getattr(e,'owned_receipt',None);raise
  finally:row['log']=bind(log);save()
  require(row['ownership']['returncode']==0,'source command failed')
 try:
  for r in plan['repositories']:
   target=SOURCE/r['relative'];target.parent.mkdir(parents=True,exist_ok=True)
   # No shared config/worktree registration mutation: each clone owns .git/config.
   ref=Path(r['reference']);marker=ref/'.git';admin=Path(marker.read_text().strip().split(': ',1)[1]) if marker.is_file() else marker
   if not admin.is_absolute():admin=(ref/admin).resolve()
   common=Path(git(ref,'rev-parse','--git-common-dir').decode().strip())
   if not common.is_absolute():common=(ref/common).resolve()
   command(['git','clone','--shared','--no-checkout',str(common),str(target)])
   require((target/'.git').is_dir(),'private clone, never shared worktree')
   git(target,'config','core.sparseCheckout','true');git(target,'config','core.sparseCheckoutCone','false')
   info=target/'.git/info';info.mkdir(exist_ok=True);(info/'sparse-checkout').write_text('\n'.join('/'+n for n in list(r['files'])+r['children'])+'\n')
   command(['git','-C',str(target),'checkout','--detach',r['commit']])
   record['repositories'].append(dict(path=str(target),head=r['commit']))
  record['state']='PASS private source materialized; no compiler/model/reader'
  save();verify();record['resources']=budget.check();save()
 except BaseException as e:record.update(state='FAIL source preparation preserved',error=repr(e));save();raise
 print(budget.BASE/'source-preparation.json')
if __name__=='__main__':main()
