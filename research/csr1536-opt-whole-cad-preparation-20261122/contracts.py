"""Fresh1536 source/CAD contracts. No old live guard or automatic reserve release."""
import hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
FAMILY_ART=Path('/home/coyang/fpga-artifacts/context-resume/csr-opt1536-fpga-preparation-20261122')
ART=FAMILY_ART/'preparation01'
SOURCE_HERE=HERE;SOURCE_ART=ART
TOP='a8fbd5fa6911160ab0845d75c6096549806af7b7'
BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
OPS=Path('/home/coyang/zynq-parrot-csr-opt-ops-20261122')
OPS_HEAD='cfc7fac2a2a0f693809d3a73038164aded1ed719'
SOURCE=Path('/run/user/1001/zp-linux-csr-opt1536-fpga-source-20261122-01')
WORK=Path('/run/user/1001/zp-linux-csr-opt1536-trace0-cad-20261122-01')
LOGS=Path('/home/coyang/fpga-logs-linux-csr-opt1536-trace0')
GHOST=Path('/home/coyang/zynq-parrot-linux-capacity/research/csr-unmasked-integration-preparation-20261122/integration-contract.sv')
SOURCE_CAP=128*1024**2;SOURCE_EVI_CAP=8*1024**2;HELPER_CAP=1024**2
CAPS=dict(work_cap_bytes=512*1024**2,evidence_cap_bytes=192*1024**2,
 work_floor_bytes=1024**3,home_floor_bytes=1792*1024**2,
 shm_floor_bytes=512*1024**2,deadline_seconds=10800)
# These are conservative FULL prospective charges, never inferred live usage.
# ROOT must issue a NEW signed profile after the latest native infrastructure
# stop/disposition. This source-only template itself reserves/launches nothing.
OTHER=dict(base_RUN_bytes=1156926898,current_native_RUN_bytes=1024**3,
 base_HOME_bytes=36260188,current_native_HOME_bytes=32*1024**2,
 logging_HOME_bytes=128*1024**2,metadata_HOME_bytes=4*1024**2,
 base_SHM_bytes=335544320)
GEOMETRY=dict(i_lines=1536,d_lines=1536,sets=256,epoch=8,line_bytes=64,
 observe=1,cache_miss_trace=0,delay=0,resident=2,logical=4,l2_bytes=16384,aclk_mhz=20)
PHASES=[('make-preflight',0),('clean',0),('build',0),('loader',0),
 ('integrity-run',-6),('integrity-checker',0),('advisory-run',-6),
 ('advisory-checker',0),('strict',0),('counter',0),('parameters',0)]

def require(v,m):
 if not v:raise RuntimeError(m)
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def exact(row):
 require(bind(row['path'])==row,'changed bound input: '+row['path']);return json.loads(Path(row['path']).read_text())
def freeze_records(row):
 q=exact(row)
 # Explicit ROOT-priced basis records only; no old/native closure importer or
 # interpretation of an archive/PASS as releasing outstanding future bytes.
 for r in q['basis_records']:exact(r)
 return q['basis_records']+[q['baseline_XPR']]
def profile(row):
 q=exact(row)
 require(q['schema']=='csr1536-ExploreArea-CAD-resource-profile-v1' and q['ROOT_approved'] is True,'fresh ROOT resource authority required')
 require(q['TOP']==TOP and q['BP']==BP and q['OPS']==OPS_HEAD,'exact source/operations profile')
 require(q['own_CAD']==CAPS and q['own_SOURCE_RUN_bytes']==SOURCE_CAP and q['own_helper_HOME_bytes']==HELPER_CAP,'fixed prospective source128/work512/evidence192/deadline/floors')
 require(q['OTHER']==OTHER and q['all_other_charged_reserves_included'] is True,'all fixed prospective OTHER charges')
 require(q['source_evidence_is_subset_of_CAD_evidence'] is True and q['source_evidence_cap_bytes']==SOURCE_EVI_CAP,'source8MiB within whole192MiB, not additive')
 require(q['metadata_includes_helpers_and_proof_bytes'] is True and q['no_automatic_discount_or_extension'] is True,'full metadata envelope; no implicit releases')
 require(q['fresh_funding_after_native_infrastructure_stop'] is True,'old unlaunched reservation cannot silently authorize new CAD')
 require(q['basis_records'],'ROOT fresh global-resource disposition must be bound')
 for r in q['basis_records']:exact(r)
 b=q['baseline_XPR'];require(b['bytes']==13805 and b['sha256']=='0aeeb1ddf78a5675559343132cd513398e3f630ac2f3514edb6814351764eba8','exact old strategy/XPR control')
 require(bind(b['path'])==b,'unchanged baseline XPR')
 return q,OTHER

def native(row):
 q=exact(row)
 require(q['state']=='PASS CSR1536 complete eleven-phase native integrity/cold08; scoped/STD/all1536 pending','fresh authoritative1536 adapter PASS, never historical256 label alone')
 old=exact(q['inherited_qualified_receipt'])
 require(old['state']=='PASS CSR unmasked256 trace0 clean fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-geometry-source-audits','exact inherited phase receipt label')
 for item in (old,q):
  require(item['source_tree_baseline']==TOP and item['source_bp']==BP and item['geometry']==GEOMETRY,'actual1536 source and all17 literal topology checks')
  require([(c['label'],c['returncode']) for c in item['commands']]==PHASES,'all11 actual phases; -6 only checked known postPASS finalizers')
  require(item['model']['sha256'] and len(item['model']['sha256'])==64 and item['model']['bytes']>0,'actual built/qualified model')
  exact(item['actual_source_list'])
  require(item['closed_audits'],'all actual strict/counter/parameters audit records required')
  for r in item['closed_audits'].values():exact(r)
 # Adapter may add its label/provenance only; no altered commands/model/audits.
 for k in ('source_tree_baseline','source_bp','model','geometry','commands','actual_source_list','closed_audits'):
  require(q[k]==old[k],'adapter cannot reinterpret inherited qualification: '+k)
 return q

def source_authority(path):
 a=json.loads(Path(path).read_text())
 require(a['schema']=='csr1536-CAD-source-authority-v1' and a['ROOT_approved'] is True and a['TOP']==TOP and a['BP']==BP,'ROOT fresh source-only authority')
 profile(a['resource_profile']);n=native(a['native_session']);s=exact(a['actual_source_list'])
 require(a['model_sha256']==n['model']['sha256'],'actual1536 model identity')
 for r in a['bindings']:require(bind(r['path'])==r,'frozen source helper/carrier')
 require({k:a['actual_source_list'][k] for k in ('bytes','sha256')}=={k:n['actual_source_list'][k] for k in ('bytes','sha256')},'portable actual consumed source bytes')
 require(Path(a['native_session']['path'])==ART/'native-proof/adapter-session.json' and Path(a['actual_source_list']['path'])==ART/'native-proof/actual-source-list.json','fresh HOME proof exports')
 require(a['simulation_only_ghost']==bind(GHOST) and str(GHOST) in s['sources'],'exact actual simulation-only exclusion')
 return a

def grouped_require(entries):
 groups={}
 for path,floor,remaining in entries:
  p=Path(path)
  while not p.exists():p=p.parent
  device=p.stat().st_dev;free=shutil.disk_usage(p).free
  g=groups.setdefault(device,dict(device=device,paths=[],floor=0,remaining=0,free=free))
  g['paths'].append(str(path));g['floor']=max(g['floor'],floor);g['remaining']+=remaining;g['free']=min(g['free'],free)
 for g in groups.values():require(g['free']>=g['floor']+g['remaining'],'actual-volume full remaining reserve refusal: '+repr(g))
 return list(groups.values())

def source_resources(authority_path,source_used,evidence_used,helper_used):
 a=source_authority(authority_path);profile(a['resource_profile'])
 require(0<=source_used<=SOURCE_CAP and 0<=evidence_used<=SOURCE_EVI_CAP and 0<=helper_used<=HELPER_CAP,'source128/evidence8/helper1 caps')
 return grouped_require([(SOURCE.parent,CAPS['work_floor_bytes'],SOURCE_CAP-source_used),
  (WORK.parent,CAPS['work_floor_bytes'],CAPS['work_cap_bytes']+OTHER['base_RUN_bytes']+OTHER['current_native_RUN_bytes']),
  (HERE,CAPS['home_floor_bytes'],CAPS['evidence_cap_bytes']-evidence_used+sum(OTHER[k] for k in ('base_HOME_bytes','current_native_HOME_bytes','logging_HOME_bytes','metadata_HOME_bytes'))),
  (Path('/dev/shm'),CAPS['shm_floor_bytes'],OTHER['base_SHM_bytes'])])

def cad_limits(row):
 profile(row)
 return dict(CAPS,source_cap_bytes=SOURCE_CAP,
  other_work_future_bytes=OTHER['base_RUN_bytes']+OTHER['current_native_RUN_bytes'],
  other_home_future_bytes=sum(OTHER[k] for k in ('base_HOME_bytes','current_native_HOME_bytes','logging_HOME_bytes','metadata_HOME_bytes')),
  other_shm_future_bytes=OTHER['base_SHM_bytes'])
