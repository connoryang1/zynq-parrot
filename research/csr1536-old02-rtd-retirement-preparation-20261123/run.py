#!/usr/bin/env python3
"""Bounded ROOT owner for archived RTD review or separately approved retirement."""
import argparse,hashlib,json,os,resource,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
OUT=Path('/home/coyang/fpga-artifacts/context-resume/csr1536-old02-rtd-retirement-20261123')
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def guard(a):
 r=a['ROOT_resource_profile'];need(sha(r['path'])==r['sha256'],'ROOT fixed profile');q=json.loads(Path(r['path']).read_text());need(q['ROOT_approved'] is True and q['all_other_charged_reserves_included'] is True,'funded all-reserve ROOT authority')
 need(q['helper_cap_bytes']==65536 and sum(max(p.stat().st_size,p.stat().st_blocks*512) for p in HERE.rglob('*') if p.is_file())<=65536,'fixed64KiB helper/authority family')
 used=sum(max(p.stat().st_size,p.stat().st_blocks*512) for p in OUT.rglob('*') if p.is_file()) if OUT.exists() else 0
 need(used<=2097152 and q['output_cap_bytes']==2097152 and q['HOME_floor_bytes']==1879048192,'fixed2MiB whole output/floor')
 for root,key,extra in [('/home/coyang','required_HOME_free_excluding_own_remaining',max(0,2097152-used)),('/run/user/1001','required_RUN_free_bytes',0),('/dev/shm','required_SHM_free_bytes',0)]:
  s=os.statvfs(root);need(s.f_bavail*s.f_frsize>=q[key]+extra,'all unchanged future allocations '+root)
 mem=next(int(v.split()[1])*1024 for v in Path('/proc/meminfo').read_text().splitlines() if v.startswith('MemAvailable:'));need(mem>=q['required_MemAvailable_bytes'],'physical memory includes1GiB worker allowance')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);p.add_argument('--phase',choices=['review','retire'],required=True);p.add_argument('--review-sha256');p.add_argument('--ROOT-review-approval',type=Path);p.add_argument('--ROOT-review-approval-sha256');x=p.parse_args();need(sha(x.admission)==x.admission_sha256,'exact ROOT admission');a=json.loads(x.admission.read_text());need(a['ROOT_approved'] is True and x.phase in a['actions'],'ROOT selected phase')
 for r in a['inputs']:need(sha(r['path'])==r['sha256'] and Path(r['path']).stat().st_size==r['bytes'],'exact source bindings')
 guard(a);OUT.mkdir(parents=True,exist_ok=True);receipt=OUT/(x.phase+'-owned.json');need(not receipt.exists(),'one phase attempt, preserve prior output');argv=[sys.executable,'-B',str(HERE/'retire.py'),'--admission',str(x.admission),'--admission-sha256',x.admission_sha256,'--phase',x.phase]
 if x.phase=='retire':need(x.review_sha256 and x.ROOT_review_approval and x.ROOT_review_approval_sha256,'separate review/ROOT unlink approval');argv+=['--review-sha256',x.review_sha256,'--ROOT-review-approval',str(x.ROOT_review_approval),'--ROOT-review-approval-sha256',x.ROOT_review_approval_sha256]
 def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824));resource.setrlimit(resource.RLIMIT_FSIZE,(2097152,2097152))
 rec=dict(state='RUNNING ROOT-owned '+x.phase,argv=argv,admission_sha256=x.admission_sha256)
 try:
  with (OUT/(x.phase+'.log')).open('xb') as log:rec['ownership']=owned.run(argv,HERE,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,180,lambda:guard(a),limits)
  need(rec['ownership']['returncode']==0 and rec['ownership']['failure'] is None and not rec['ownership']['owned_group_remaining'],'complete owned phase');rec['state']='PASS ROOT-owned '+x.phase;guard(a)
 except BaseException as e:rec.update(state='FAIL preserved '+x.phase,error=repr(e));rec.setdefault('ownership',getattr(e,'owned_receipt',None));raise
 finally:receipt.write_text(json.dumps(rec,indent=2)+'\n')
 print(rec['state'])
if __name__=='__main__':main()
