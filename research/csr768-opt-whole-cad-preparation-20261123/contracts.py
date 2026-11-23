"""Fresh768 source/CAD contracts. No old live guard or automatic reserve release."""
import hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
FAMILY_ART=Path('/home/coyang/fpga-artifacts/context-resume/csr-opt768-fpga-preparation-20261123')
ART=FAMILY_ART/'preparation01'
SOURCE_HERE=HERE;SOURCE_ART=ART
TOP='1b24c915ed628f6d47a382b3aa89fb662884e1a1'
BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
OPS=Path('/home/coyang/zynq-parrot-csr-opt-ops-20261122')
OPS_HEAD='cfc7fac2a2a0f693809d3a73038164aded1ed719'
SOURCE=Path('/run/user/1001/zp-linux-csr-opt768-fpga-source-20261123-01')
WORK=Path('/run/user/1001/zp-linux-csr-opt768-trace0-cad-20261123-01')
LOGS=Path('/home/coyang/fpga-logs-linux-csr-opt768-trace0')
EVIDENCE_ROOTS=(FAMILY_ART,LOGS)
GHOST=Path('/home/coyang/zynq-parrot-linux-capacity/research/csr-unmasked-integration-preparation-20261122/integration-contract.sv')
SOURCE_CAP=128*1024**2;SOURCE_EVI_CAP=8*1024**2;HELPER_CAP=1024**2
CAPS=dict(work_cap_bytes=1536*1024**2,evidence_cap_bytes=192*1024**2,
 work_floor_bytes=1024**3,home_floor_bytes=1792*1024**2,
 shm_floor_bytes=512*1024**2,deadline_seconds=10800)
# These are conservative FULL prospective charges, never inferred live usage.
# ROOT must issue a NEW signed profile for this source/capacity and current
# disposition. This source-only template itself reserves/launches nothing.
OTHER=dict(base_RUN_bytes=1156926898,current_native_RUN_bytes=1024**3,
 base_HOME_bytes=36260188,current_native_HOME_bytes=32*1024**2,
 logging_HOME_bytes=128*1024**2,metadata_HOME_bytes=4*1024**2,
 base_SHM_bytes=335544320)
GEOMETRY=dict(i_lines=768,d_lines=768,sets=256,epoch=8,line_bytes=64,
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
 return q['basis_records']+[q['baseline_XPR'],q['predecessor_terminal_receipt'],q['predecessor_no_orphans'],q['predecessor_complete_preservation']]+([q['native_future_disposition']] if q['native_future_disposition'] else [])+([q['base_RUN_stop_receipt']] if q['base_RUN_stop_receipt'] else [])+list(q['base_RUN_stop_execution'].values())
def validate_BASE_stop(q,charges):
 # Old full BASE stays charged unless the exact separately ROOT-reviewed stop
 # operation completes. A small value/template/archive is never its authority.
 base=charges['base_RUN_bytes'];row=q['base_RUN_stop_receipt'];execution=q['base_RUN_stop_execution']
 require(type(base)is int and base in (1156926898,33554432),'only oldFULL BASE or exact retained Iarea residual')
 if base==1156926898:
  require(row is None and execution=={},'no stop/release inferred while old full BASE charged');return
 require(row['path']=='/home/coyang/fpga-artifacts/context-resume/obsolete-native-RUN-freeze-20261123-03/completion.json','exact ROOT stop03 receipt namespace')
 r=exact(row);require(r['schema']=='obsolete-native-RUN-freeze-completion-v3' and r['state']=='PASS ROOT-approved unused RUN writes stopped; all actual files kept and coverage classified' and r['ROOT_verified'] is True,'actual complete three-family stop03, not template/FAIL')
 require(r['old_BASE_RUN_bytes']==1156926898 and r['new_BASE_RUN_bytes']==33554432 and r['unused_fixed_RUN_future_withdrawn_bytes']==1123372466 and r['pending_Iarea_bytes_still_charged']==33554432,'exact BASE arithmetic, Iarea not canonical component')
 wanted={'matched':329830081,'scratch':397346275,'borrow1792':396196110}
 require(set(r['families'])==set(wanted),'all and only three obsolete families')
 for name,n in wanted.items():
  f=r['families'][name];require(f['original_cap_bytes']==805306368 and f['closed_fixed_future_charge_bytes']==n and f['new_future_RUN_bytes']==0 and isinstance(f['roots'],list)and f['roots'],'unchanged original family cap and actual stopped future '+name)
 require(r['current768_and_canonical_unchanged'] is True and r['all_current_actual_bytes_still_charged'] is True and r['physical_bytes_reclaimed']==0 and r['original_caps_unchanged'] is True and r['new_writes_need_fresh_admission'] is True,'future-only stop; no cleanup/cap/coverage/current-scope credit')
 require(set(execution)=={'outer','ROOT_acceptance'},'actual outer0 and reviewed completion required')
 outer=exact(execution['outer']);life=outer.get('ownership',outer.get('owned',outer))
 require(life['returncode']==0 and life['owned_group_remaining'] is False and life['failure'] is None,'actual worker/outer exit0 and closed owned groups')
 accepted=exact(execution['ROOT_acceptance']);require(accepted['ROOT_verified'] is True and accepted['actual_command_exitcode']==0 and accepted['completion']==row and accepted['outer_execution']==execution['outer'],'ROOT actual reviewed stop and outer result pins')

def profile(row):
 q=exact(row)
 require(q['schema']=='csr768-ExploreArea-CAD-resource-profile-v1' and q['ROOT_approved'] is True,'fresh ROOT resource authority required')
 require(q['TOP']==TOP and q['BP']==BP and q['OPS']==OPS_HEAD,'exact source/operations profile')
 require(q['own_CAD']==CAPS and q['own_SOURCE_RUN_bytes']==SOURCE_CAP and q['own_helper_HOME_bytes']==HELPER_CAP,'fresh prospective source128/work1536/shared evidence192/deadline/floors')
 charges=q['OTHER'];require(set(charges)==set(OTHER) and q['all_other_charged_reserves_included'] is True,'all explicit OTHER dimensions')
 for k in OTHER:
  if k not in ('base_RUN_bytes','current_native_RUN_bytes','current_native_HOME_bytes'):require(charges[k]==OTHER[k],'unchanged fixed OTHER: '+k)
 for k in ('current_native_RUN_bytes','current_native_HOME_bytes'):require(type(charges[k])is int and charges[k]in (0,OTHER[k]),'native FULL prospective envelope or explicitly finalized zero: '+k)
 validate_BASE_stop(q,charges)
 extra=q['additional_OTHER'];require(set(extra)=={'RUN_bytes','HOME_bytes','SHM_bytes'} and all(type(v)is int and v>=0 for v in extra.values()),'separately priced current component/other reserves, never BASE credit')
 disposition=q['native_future_disposition']
 if charges['current_native_RUN_bytes']==OTHER['current_native_RUN_bytes'] and charges['current_native_HOME_bytes']==OTHER['current_native_HOME_bytes']:require(disposition is None,'FULL native caps charged, no inferred release')
 else:
  require(disposition['sha256']=='4714a03cbc1e4694d514439f3b23c6247a372ae6ffbe003dd8a5d243e218227c','only actual4714 current768 native freeze permits zero')
  d=exact(disposition);require(d['ROOT_verified'] is True and d['TOP']==TOP and d['BP']==BP and d['future_RUN_bytes']==charges['current_native_RUN_bytes'] and d['future_HOME_bytes']==charges['current_native_HOME_bytes'] and d['all_current_bytes_still_charged'] is True,'actual explicit per-volume native-future disposition, never archive-size inference')
 require(q['evidence_roots']==list(map(str,EVIDENCE_ROOTS)) and q['one_shared_family_evidence_allocation'] is True,'fresh768 family+logs single192MiB')
 terminal=exact(q['predecessor_terminal_receipt']);require(q['predecessor_terminal_receipt']['sha256']=='ad53e06d16efe20a64bf99495df080b35249eb8d8887d4b1a81c6a2a332f3c21' and terminal['status']=='FAIL' and terminal['bound_violations']==[] and terminal['identity_violations']==[],'preserved1280 placementFAIL, not bound/owner failure or768 approval')
 require(terminal['features']=='PASS actual seven defines/three contexts/20MHz-8MHz/source' and terminal['opt']=='PASS additional opt-only actual config/property/XPR/child gates','actual prior common flow; not fit transfer')
 gone=exact(q['predecessor_no_orphans']);require(q['predecessor_no_orphans']['sha256']=='020fcabd4f4b6f3c8a791216ad8ba7b9994527d841252de9ed7250897a40a930' and gone['ROOT_verified'] is True and gone['all_owned_children_absent'] is True and gone['global_vendor_absent'] is True,'exact prior terminal identity/absence receipt')
 captured=exact(q['predecessor_complete_preservation']);require(str(captured.get('state','')).startswith('PASS') and q['ROOT_verified_complete_predecessor_preservation'] is True,'prior1280 complete preservation, no cleanup assumption')
 require(q['predecessor_complete_preservation']['sha256']=='020fcabd4f4b6f3c8a791216ad8ba7b9994527d841252de9ed7250897a40a930' and captured['current_case_future_SOURCE_WORK_RUN_bytes']==0 and captured['current_case_shared_family_future_HOME_bytes']==0 and captured['all_actual_originals_retained'] is True,'exact ROOT current1280 full lossless closure/future0, not a new fit')
 require(q['old_attempt_unchanged'] is True and q['old_actual_bytes_still_charged'] is True and type(q['old_future_SOURCE_WORK_bytes'])is int and q['old_future_SOURCE_WORK_bytes']==0 and type(q['old_future_HOME_evidence_bytes'])is int and q['old_future_HOME_evidence_bytes']==0,'explicit ROOT old RUN/HOME future disposition with all actual bytes charged')
 require(q['source_evidence_is_subset_of_CAD_evidence'] is True and q['source_evidence_cap_bytes']==SOURCE_EVI_CAP,'source8MiB within whole192MiB, not additive')
 require(q['metadata_includes_helpers_and_proof_bytes'] is True and q['no_automatic_discount_or_extension'] is True,'full metadata envelope; no implicit releases')
 require(q['no_prior_CAD_authority_reused'] is True,'no1536/native or old CAD authority transfer')
 require(q['fresh_funding_for_new768_CAD'] is True,'fresh768 funding; no old1280 resource/native approval transfer')
 require(q['basis_records'],'ROOT fresh global-resource disposition must be bound')
 for r in q['basis_records']:exact(r)
 b=q['baseline_XPR'];require(b['bytes']==13805 and b['sha256']=='0aeeb1ddf78a5675559343132cd513398e3f630ac2f3514edb6814351764eba8','exact old strategy/XPR control')
 require(bind(b['path'])==b,'unchanged baseline XPR')
 return q,charges

NATIVE_SHA='c230d6a38cad5d152b2b588af93a0b354ce52daaeade2be8cf3562c4ddc789da'
MODEL_SHA='8762ddb27740970892245ca7c067fcfff4c89da8dbbce392f2407979dbc5f964'
POOL=Path('/run/user/1001/zp-csr-unmasked768-fullcore-20261123-01')
PARAMETERS={'retained_store.storage.epoch_width_p':8,'retained_store.storage.sets_p':256,
 'retained_store.storage.i_lines_p':768,'retained_store.storage.d_lines_p':768,
 'l2_block_width_p':512,'dcache_block_width_p':512,'icache_block_width_p':512,
 'core_minimal.cache_miss_trace_p':0,'l2_sets_p':64,'dcache_sets_p':64,'icache_sets_p':64,
 'l2_assoc_p':2,'l2_banks_p':2,'num_threads_p':2,'num_contexts_p':4,
 'dcache_assoc_p':8,'icache_assoc_p':8}
def native(row):
 # One actual new768 native PASS. No1536 composite or historical768 model
 # can satisfy this exact byte/model/source chain.
 require(row['bytes']==43247 and row['sha256']==NATIVE_SHA,'fixed ROOT-reviewed768 single eleven-phase receipt')
 q=exact(row)
 require(q['state']=='PASS CSR unmasked768 trace0 clean fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-17geometry-source-audits' and q['source_endcheck']=='PASS','actual source-specific768 native acceptance')
 require('inherited_build_session'not in q and 'inherited_qualified_receipt'not in q,'not an inherited/composite approval')
 require(q['source_tree_baseline']==TOP and q['source_bp']==BP and q['geometry']==GEOMETRY,'exact new768 source/all ordinary geometry')
 require([(c['label'],c['returncode'])for c in q['commands']]==PHASES,'exact eleven actual phases, only two checked postPASS-6 finalizers')
 for c in q['commands']:
  require(c['ownership']['returncode']==c['returncode'] and c['ownership']['failure'] is None and not c['ownership']['owned_group_remaining'],'complete owned phase and cleanup')
 require(q['model']['sha256']==MODEL_SHA and q['model']['bytes']==15839528 and q['model']['path']==str(POOL/'full01/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench'),'actual8762 model, not old1280/ac3')
 require(q['actual_source_list']['path']==str(POOL/'full01/actual-source-list.json') and q['actual_source_list']['bytes']==195087 and q['actual_source_list']['sha256']=='4a89b6d3eaeecca5594fc9165e2d12db32e4620df826fef33b47e6d4b2906e55','actual new768 consumed source list')
 exact(q['actual_source_list']);require(bind(q['model_stamp']['path'])==q['model_stamp'],'exact new model stamp')
 require(set(q['closed_audits'])=={'strict','counter','parameters','generated_l2'},'all four native closed audits')
 strict=exact(q['closed_audits']['strict']);counter=exact(q['closed_audits']['counter']);params=exact(q['closed_audits']['parameters']);l2=exact(q['closed_audits']['generated_l2'])
 for key,name in [('strict','strict01/verification.json'),('counter','counter01/verification.json'),('parameters','parameters01/verification.json'),('generated_l2','generated-geometry.json')]:require(q['closed_audits'][key]['path']==str(POOL/'full01'/name),'actual new768 audit path: '+key)
 require(strict['accepted'] is True and counter['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'same strict full512/eight real writes/I-retirement and independent counters')
 require(params['facts']['values']==PARAMETERS and params['facts']['clean_eof'] is True,'all seventeen actual768 geometry facts throughEOF')
 require(l2['state']=='PASS actual generated STATIC16KiB L2 geometry' and l2['facts']['model']==q['model'] and l2['facts']['compiled_sources']==q['actual_source_list'] and l2['facts']['l2']['total_bytes']==16384,'actual generated static16KiB common L2')
 require(strict['bindings']['compiled_source_list']==q['actual_source_list'] and counter['bindings']['strict']==q['closed_audits']['strict'] and counter['bindings']['fst']==strict['bindings']['fst'],'same actual source/strict/counter trace chain')
 require(strict['bindings']['fst']['path']==str(POOL/'full01/advisory/trace.fst') and counter['bindings']['run']['path']==str(POOL/'full01/advisory/verification.json'),'original single native run, not corrected inherited sidecar')
 run=exact(counter['bindings']['run']);require(run['actual_returncode']==-6 and run['trace']==strict['bindings']['fst'] and run['counter_values']==['1','1','1','1','8','8'],'same complete native observer proof')
 require(len(run['files'])==6 and all(set(('path','bytes','sha256','inode','mtime_ns','ctime_ns'))<=set(r) for r in run['files']),'six full run-input bindings from outset')
 require(q['protected_native_inputs']['path']==str(POOL/'full01/protected-native-inputs.json') and q['protected_native_inputs']['sha256']=='cc4d2031f89b812125b5599ca9c654ba23a59f87cf5200fd7f3bcb8505db6d1a','actual accepted file-metadata/membership lifecycle contract')
 return q

def source_authority(path):
 a=json.loads(Path(path).read_text())
 require(a['schema']=='csr768-CAD-source-authority-v1' and a['ROOT_approved'] is True and a['TOP']==TOP and a['BP']==BP,'ROOT fresh source-only authority')
 profile(a['resource_profile']);n=native(a['native_session']);s=exact(a['actual_source_list'])
 require(a['model_sha256']==n['model']['sha256'],'actual768 model identity')
 for r in a['bindings']:require(bind(r['path'])==r,'frozen source helper/carrier')
 require({k:a['actual_source_list'][k] for k in ('bytes','sha256')}=={k:n['actual_source_list'][k] for k in ('bytes','sha256')},'portable actual consumed source bytes')
 require(Path(a['native_session']['path'])==ART/'native-proof/session.json' and Path(a['actual_source_list']['path'])==ART/'native-proof/actual-source-list.json','fresh HOME proof exports')
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

def source_resources(authority_path,source_used,own_source_evidence_used,family_evidence_used,helper_used):
 a=source_authority(authority_path);p,charges=profile(a['resource_profile'])
 require(0<=source_used<=SOURCE_CAP and 0<=own_source_evidence_used<=SOURCE_EVI_CAP and 0<=family_evidence_used<=CAPS['evidence_cap_bytes'] and own_source_evidence_used<=family_evidence_used and 0<=helper_used<=HELPER_CAP,'own SOURCE128MiB/ART01source8MiB/helper1MiB and whole family192MiB are separate caps')
 return grouped_require([(SOURCE.parent,CAPS['work_floor_bytes'],SOURCE_CAP-source_used),
  (WORK.parent,CAPS['work_floor_bytes'],CAPS['work_cap_bytes']+charges['base_RUN_bytes']+charges['current_native_RUN_bytes']+p['additional_OTHER']['RUN_bytes']),
  (HERE,CAPS['home_floor_bytes'],CAPS['evidence_cap_bytes']-family_evidence_used+sum(charges[k] for k in ('base_HOME_bytes','current_native_HOME_bytes','logging_HOME_bytes','metadata_HOME_bytes'))+p['additional_OTHER']['HOME_bytes']),
  (Path('/dev/shm'),CAPS['shm_floor_bytes'],charges['base_SHM_bytes']+p['additional_OTHER']['SHM_bytes'])])

def cad_limits(row):
 p,charges=profile(row)
 return dict(CAPS,source_cap_bytes=SOURCE_CAP,
  other_work_future_bytes=charges['base_RUN_bytes']+charges['current_native_RUN_bytes']+p['additional_OTHER']['RUN_bytes'],
  other_home_future_bytes=sum(charges[k] for k in ('base_HOME_bytes','current_native_HOME_bytes','logging_HOME_bytes','metadata_HOME_bytes'))+p['additional_OTHER']['HOME_bytes'],
  other_shm_future_bytes=charges['base_SHM_bytes']+p['additional_OTHER']['SHM_bytes'])
