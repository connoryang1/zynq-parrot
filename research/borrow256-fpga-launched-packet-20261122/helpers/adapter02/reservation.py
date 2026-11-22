"""Exact shared resource/freeze records only. No old budget implementation."""
import hashlib,json
from pathlib import Path
ROOT=Path('/home/coyang/fpga-artifacts/context-resume/reservation-closures-20261122')
MARKER=ROOT/'r8-freeze-complete.json'
MARKER_SHA='09075ffd134c175155d9299b498ed9c1bbe0c2d635e463fc941f2fb50880b5c7'
WORK_SHA='27dbc7e99783672633e23cb50091430cf6dfb91213427c769c2215f18f855a37'
EVIDENCE_SHA='e5af52fb91c1f93bbf01f23a40eae24cb0bc9d63b6b71fd2ac36d9648e99336c'
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def require(v,m):
 if not v:raise RuntimeError(m)
def check_freeze():
 require(bind(MARKER)['sha256']==MARKER_SHA,'exact complete R8 freeze marker')
 m=json.loads(MARKER.read_text());require(m['schema']=='r8-work-evidence-freeze-complete-v1' and m['state'].startswith('PASS ROOT old R8'),'complete frozen pair state')
 for name,sha in [('work',WORK_SHA),('evidence',EVIDENCE_SHA)]:
  r=m[name];require(r['sha256']==sha and bind(r['path'])==r,'both exact R8 receipt bytes')
  f=json.loads(Path(r['path']).read_text());require(f['freeze_pair_id']==m['freeze_pair_id'] and f['future_growth_reserved_bytes']==0 and f['original_allocation_limit_unchanged'] is True,'same frozen pair and zero future growth')
  require(f['requires_complete_marker']==dict(path=str(MARKER),freeze_pair_id=m['freeze_pair_id']),'receipt cannot independently release allocation')
 return [bind(MARKER),m['work'],m['evidence']]
POLICY=Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/retained-borrow256-shared-budget-preparation-20261122/policy.json')
POLICY_SHA='865f8008175d2049a0c9e7e362962b75a5bedc4600a12ef8cc2cdf1d2a8ca10a'
def check_policy(limits):
 rows=check_freeze();require(bind(POLICY)['sha256']==POLICY_SHA,'exact shared new resource policy')
 p=json.loads(POLICY.read_text());require(p['schema']=='borrow256-shared-reserve-policy-v1','shared resource schema')
 freeze=p['old_R8_freeze'];require(freeze['all_three_required'] is True and freeze['old_caps_unchanged'] is True,'no half-freeze/old-cap change')
 require([freeze[k] for k in ('complete','work','evidence')]==rows,'shared exact three-file freeze bindings')
 require(freeze['freeze_pair_id']==json.loads(MARKER.read_text())['freeze_pair_id'],'shared same freeze pair')
 own=p['new_CAD'];mapping={'work_cap_bytes':'work_cap_bytes','evidence_cap_bytes':'evidence_cap_bytes','work_floor_bytes':'work_floor_bytes','HOME_floor_bytes':'home_floor_bytes','shm_floor_bytes':'shm_floor_bytes','deadline_seconds':'deadline_seconds'}
 require(all(own[k]==limits[v] for k,v in mapping.items()),'all own bounds equal shared policy')
 require(own['work_root']=='/run/user/1001/zp-linux-borrow256-trace0-cad-20261122-01' and own['evidence_roots']==['/home/coyang/fpga-logs-linux-retained-borrow256-trace0','/home/coyang/fpga-artifacts/context-resume/borrow256-fpga-preparation-20261122/preparation01'],'whole fixed evidence union')
 other=p['fixed_other_for_CAD_monitor'];require(other['RAM_bytes']==limits['other_work_future_bytes']==1928678834 and other['HOME_bytes']==limits['other_home_future_bytes']==49424582,'explicit conservative other RAM/HOME charges')
 require(p['native']['pool_cap_bytes']==805306368 and p['native']['new_cohort_cap_inside_pool_bytes']==268435456,'full768MiB pool already includes new256MiB cohort')
 return rows+[bind(POLICY)]
