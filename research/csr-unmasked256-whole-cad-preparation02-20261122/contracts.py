"""Fresh CSR CAD authority/profile checks; never call an obsolete live guard."""
import hashlib,json,os,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
FAMILY_ART=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fpga-preparation-20261122')
ART=FAMILY_ART/'preparation02'
PREVIOUS_HELPER=HERE.parent/'csr-unmasked256-whole-cad-preparation-20261122'
TOP='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd';BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
SOURCE=Path('/dev/shm/zp-linux-csr-unmasked256-fpga-source-20261122-02')
WORK=Path('/run/user/1001/zp-linux-csr-unmasked256-trace0-cad-20261122-01')
LOGS=Path('/home/coyang/fpga-logs-linux-csr-unmasked256-trace0')
GHOST=Path('/home/coyang/zynq-parrot-linux-capacity/research/csr-unmasked-integration-preparation-20261122/integration-contract.sv')
CLOSURES=Path('/home/coyang/fpga-artifacts/context-resume/reservation-closures-20261122')
BASE_PROFILE=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fullcore-preparation-20261122/preparation02/ROOT-resource-profile02.json')
BASE_SHA='e7a234ff8f61dfd4e684c2b4c2965089cc658ba23d541c557841733932eee25e'
NATIVE_CLOSED=Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow256-trace0-fullcore-20261122/obsolete-profile-closed01/reservation-complete.json')
SOURCE_CAP=128*1024**2;SOURCE_EVI_CAP=8*1024**2;HELPER_CAP=1024**2
CAPS=dict(work_cap_bytes=2684354560,evidence_cap_bytes=201326592,work_floor_bytes=1073741824,home_floor_bytes=2415919104,shm_floor_bytes=536870912,deadline_seconds=10800)

def require(v,m):
 if not v:raise RuntimeError(m)
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def exact(row):
 require(bind(row['path'])==row,'changed bound input: '+row['path']);return json.loads(Path(row['path']).read_text())
def freeze_records():
 marker=CLOSURES/'r9-freeze-complete.json';require(bind(marker)['sha256']=='d520e5060940f394c8c75ad7d4f54f9e16ae50921238051b8f178cf2bcbd36e4','complete R9 immutable freeze')
 q=json.loads(marker.read_text());rows=[bind(marker)]
 for k,sha in [('work','212a93cb8e57b59e02f7159e98fd1804326b059685659e0ee39732c06899f56d'),('evidence','368f3cff2c4860219ec2ac56474f72afe64ad6d9d6aeaa54a7c2e0cdc5d57dd4')]:
  r=q[k];require(r['sha256']==sha,'exact R9 family receipt');f=exact(r)
  require(f['freeze_pair_id']==q['freeze_pair_id'] and f['future_growth_reserved_bytes']==0 and f['original_allocation_limit_unchanged'] is True,'same R9 frozen pair, no future growth')
  require(f['requires_complete_marker']==dict(path=str(marker),freeze_pair_id=q['freeze_pair_id']),'no half-pair release');rows.append(r)
 require(bind(NATIVE_CLOSED)['sha256']=='65fd0aeebfbaa12f821f852319f4c22b3c3c5b5313685ce0cde419a1c34aaec3','old native finalized future release')
 q=json.loads(NATIVE_CLOSED.read_text());require(q['future_native_POOL_bytes']==q['future_native_HOME_bytes']==0 and q['all_current_bytes_still_charged'] is True,'old occupied bytes retained')
 return rows+[bind(NATIVE_CLOSED)]
def profile(row):
 q=exact(row);require(q['schema']=='csr256-CAD-rollforward-profile-v1' and q['ROOT_approved'] is True,'ROOT fresh profile countersign required')
 require(q['basis_profile']==bind(BASE_PROFILE) and bind(BASE_PROFILE)['sha256']==BASE_SHA,'exact current resource lineage')
 base=json.loads(BASE_PROFILE.read_text());require(base['all_other_charged_reserves_included'] is True,'full old OTHER envelope')
 require(q['old_frozen_records']==freeze_records(),'exact finalized R9/old-native closures only')
 require(q['own_CAD']==CAPS and q['own_source_cap_bytes']==SOURCE_CAP and q['own_helper_cap_bytes']==HELPER_CAP,'fresh prospective bounds, no old admission edit')
 a=q['source_reserve_attribution'];require(a==dict(ROOT_approved=True,existing_OTHER_SHM_bytes=335544320,new_SOURCE_within_existing_bytes=134217728,remaining_OTHER_SHM_bytes=201326592,total_global_reserve_unchanged=True),'explicit ROOT source attribution within old extra256MiB, not extra source double-charge')
 require(base['other_SHM_bytes']==a['existing_OTHER_SHM_bytes'],'same total existing SHM envelope')
 f=q['current_CSR_native_future'];require(set(f)=={'RUN','HOME','helper','zero_authority'},'explicit current native future caps')
 if (f['RUN'],f['HOME'],f['helper'])==(1073741824,33554432,1048576):require(f['zero_authority'] is None,'active native full cap charged')
 else:
  require((f['RUN'],f['HOME'],f['helper'])==(0,0,0) and f['zero_authority'],'future zero requires finalized receipt')
  closed=exact(f['zero_authority']);require(closed['ROOT_verified'] is True and closed['TOP']==TOP and closed['BP']==BP and closed['future_RUN_bytes']==closed['future_HOME_bytes']==closed['future_helper_bytes']==0 and closed['all_current_bytes_still_charged'] is True,'ROOT finalized native/clone/regression closure, never inferred from PASS/archive alone')
 for r in q['additional_basis_records']:exact(r)
 return q,base

def native(row):
 q=exact(row);require(q['state']=='PASS CSR unmasked256 trace0 clean fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-geometry-source-audits','exact new fullcore acceptance')
 require(q['source_tree_baseline']==TOP and q['source_bp']==BP and q['model']['sha256']=='9c69a2f83539ca7a3f2c74c3be0502dbbf929d09ea95f1d75bfd2bd7172fc1fd','exact new native source/model lineage')
 require([(c['label'],c['returncode']) for c in q['commands']]==[('make-preflight',0),('clean',0),('build',0),('loader',0),('integrity-run',-6),('integrity-checker',0),('advisory-run',-6),('advisory-checker',0),('strict',0),('counter',0),('parameters',0)],'all11 actual phases; -6 only known postPASS finalizers')
 require(q['geometry']==dict(i_lines=256,d_lines=256,sets=256,epoch=8,line_bytes=64,observe=1,cache_miss_trace=0,delay=0,resident=2,logical=4,l2_bytes=16384,aclk_mhz=20),'same exact geometry/profile')
 return q

def source_authority(path):
 a=json.loads(Path(path).read_text());require(a['schema']=='csr256-CAD-source-authority-v1' and a['ROOT_approved'] is True and a['TOP']==TOP and a['BP']==BP,'ROOT exact source-only authority')
 profile(a['resource_profile']);n=native(a['native_session']);s=exact(a['actual_source_list'])
 require(a['model_sha256']==n['model']['sha256'] and len(a['model_sha256'])==64,'exact full new model identity')
 for r in a['bindings']:require(bind(r['path'])==r,'frozen source preparation helper')
 require({k:a['actual_source_list'][k] for k in ('bytes','sha256')}=={k:n['actual_source_list'][k] for k in ('bytes','sha256')},'actual native source-list portable export bytes')
 require(Path(a['native_session']['path'])==ART/'native-proof/session.json' and Path(a['actual_source_list']['path'])==ART/'native-proof/actual-source-list.json','fresh HOME proof paths, no active tree scan')
 require(a['simulation_only_ghost']==bind(GHOST),'exact intentional simulation-only bind source')
 require(str(GHOST) in s['sources'],'ghost exclusion must be explicit actual source input')
 return a

def grouped_require(entries):
 groups={}
 for path,floor,remaining in entries:
  p=Path(path)
  while not p.exists():p=p.parent
  d=p.stat().st_dev;free=shutil.disk_usage(p).free
  g=groups.setdefault(d,dict(device=d,paths=[],floor=0,remaining=0,free=free));g['paths'].append(str(path));g['floor']=max(g['floor'],floor);g['remaining']+=remaining;g['free']=min(g['free'],free)
 for g in groups.values():require(g['free']>=g['floor']+g['remaining'],'actual-volume remaining allocation refusal: '+repr(g))
 return list(groups.values())

def source_resources(authority_path,source_used,evidence_used,helper_used):
 a=source_authority(authority_path);p,b=profile(a['resource_profile']);f=p['current_CSR_native_future'];require(source_used<=SOURCE_CAP and evidence_used<=SOURCE_EVI_CAP and helper_used<=HELPER_CAP,'source/readiness fixed caps')
 return grouped_require([(WORK.parent,1073741824,b['other_RUN_bytes']+f['RUN']),
  (HERE,2415919104,b['other_HOME_bytes']+f['HOME']+f['helper']+max(0,SOURCE_EVI_CAP-evidence_used)+max(0,HELPER_CAP-helper_used)),
  (SOURCE.parent,536870912,p['source_reserve_attribution']['remaining_OTHER_SHM_bytes']+max(0,SOURCE_CAP-source_used))])

def cad_limits(profile_row):
 p,b=profile(profile_row);f=p['current_CSR_native_future']
 return dict(CAPS,other_work_future_bytes=b['other_RUN_bytes']+f['RUN'],other_home_future_bytes=b['other_HOME_bytes']+f['HOME']+f['helper']+HELPER_CAP,other_shm_future_bytes=b['other_SHM_bytes'])
