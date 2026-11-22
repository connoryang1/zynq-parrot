"""Fresh1536 source/CAD contracts. No old live guard or automatic reserve release."""
import hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
FAMILY_ART=Path('/home/coyang/fpga-artifacts/context-resume/csr-opt1536-fpga-preparation-20261122')
ART=FAMILY_ART/'preparation02'
SOURCE_HERE=HERE;SOURCE_ART=ART
TOP='a8fbd5fa6911160ab0845d75c6096549806af7b7'
BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
OPS=Path('/home/coyang/zynq-parrot-csr-opt-ops-20261122')
OPS_HEAD='cfc7fac2a2a0f693809d3a73038164aded1ed719'
SOURCE=Path('/run/user/1001/zp-linux-csr-opt1536-fpga-source-20261122-02')
WORK=Path('/run/user/1001/zp-linux-csr-opt1536-trace0-cad-20261122-02')
LOGS=Path('/home/coyang/fpga-logs-linux-csr-opt1536-trace0-02')
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
 return q['basis_records']+[q['baseline_XPR']]+([q['native_future_disposition']] if q['native_future_disposition'] else [])
def profile(row):
 q=exact(row)
 require(q['schema']=='csr1536-ExploreArea-CAD-resource-profile-v2' and q['ROOT_approved'] is True,'fresh ROOT resource authority required')
 require(q['TOP']==TOP and q['BP']==BP and q['OPS']==OPS_HEAD,'exact source/operations profile')
 require(q['own_CAD']==CAPS and q['own_SOURCE_RUN_bytes']==SOURCE_CAP and q['own_helper_HOME_bytes']==HELPER_CAP,'fixed prospective source128/work512/evidence192/deadline/floors')
 charges=q['OTHER'];require(set(charges)==set(OTHER) and q['all_other_charged_reserves_included'] is True,'all explicit OTHER dimensions')
 for k in OTHER:
  if k not in ('current_native_RUN_bytes','current_native_HOME_bytes'):require(charges[k]==OTHER[k],'unchanged fixed OTHER: '+k)
 for k in ('current_native_RUN_bytes','current_native_HOME_bytes'):require(type(charges[k])is int and charges[k]in (0,OTHER[k]),'native FULL prospective envelope or explicitly finalized zero: '+k)
 disposition=q['native_future_disposition']
 if charges==OTHER:require(disposition is None,'FULL native caps charged, no inferred release')
 else:
  d=exact(disposition);require(d['ROOT_verified'] is True and d['TOP']==TOP and d['BP']==BP and d['future_RUN_bytes']==charges['current_native_RUN_bytes'] and d['future_HOME_bytes']==charges['current_native_HOME_bytes'] and d['all_current_bytes_still_charged'] is True,'actual explicit per-volume native-future disposition, never archive-size inference')
 require(q['source_evidence_is_subset_of_CAD_evidence'] is True and q['source_evidence_cap_bytes']==SOURCE_EVI_CAP,'source8MiB within whole192MiB, not additive')
 require(q['metadata_includes_helpers_and_proof_bytes'] is True and q['no_automatic_discount_or_extension'] is True,'full metadata envelope; no implicit releases')
 require(q['fresh_funding_after_native_infrastructure_stop'] is True,'old unlaunched reservation cannot silently authorize new CAD')
 require(q['basis_records'],'ROOT fresh global-resource disposition must be bound')
 for r in q['basis_records']:exact(r)
 b=q['baseline_XPR'];require(b['bytes']==13805 and b['sha256']=='0aeeb1ddf78a5675559343132cd513398e3f630ac2f3514edb6814351764eba8','exact old strategy/XPR control')
 require(bind(b['path'])==b,'unchanged baseline XPR')
 return q,charges

NATIVE_COMPOSITE_SHA='09cda44f2c27837a4ef69f4aa8851e540eabada3626540f8836512148a871d63'
MODEL_SHA='ac3ad3af06b4db95398ef471585529add0a1fb9099229aff812f6fd8a9c4e5ac'
POOL=Path('/run/user/1001/zp-csr-unmasked1536-fullcore-20261122-01')
PARAMETERS={'retained_store.storage.epoch_width_p':8,'retained_store.storage.sets_p':256,
 'retained_store.storage.i_lines_p':1536,'retained_store.storage.d_lines_p':1536,
 'l2_block_width_p':512,'dcache_block_width_p':512,'icache_block_width_p':512,
 'core_minimal.cache_miss_trace_p':0,'l2_sets_p':64,'dcache_sets_p':64,'icache_sets_p':64,
 'l2_assoc_p':2,'l2_banks_p':2,'num_threads_p':2,'num_contexts_p':4,
 'dcache_assoc_p':8,'icache_assoc_p':8}
def native(row):
 # Exact accepted ROOT composite only. Never reinterpret either predecessor FAIL
 # as PASS; never accept an adapter/full01 label or a future clone in its place.
 require(row['bytes']==34904 and row['sha256']==NATIVE_COMPOSITE_SHA,'fixed ROOT-reviewed native composite bytes')
 q=exact(row)
 require(q['schema']=='csr1536-complete-native-composite-v1' and q['state']=='PASS COMPOSITE CSR1536 cleanbuild/loader plus complete integrity/cold08 strict512b-eight-real-writes-Iretire-counter-17geometry-source-audits','actual three-part native acceptance')
 require(q['source_endcheck']=='PASS' and q['total_qualified_phases']==11,'ROOT final source and eleven-phase acceptance')
 require(q['old_partial_integrity_explicitly_excluded'] is True and q['old_failed_counter_receipt_explicitly_excluded'] is True,'both failed partial phases preserved/excluded')
 require(q['all_1536_capacity_coverage'] is False and q['scoped_clone_and_STD_pending'] is True and q['no_board_operations'] is True,'native sparse-case limits, not clone/STD/all-slot/physical approval')
 build=exact(q['inherited_build_session']);runtime=exact(q['inherited_runtime_strict_session']);tail=exact(q['original_tail_receipt'])
 require(q['inherited_build_session']['path']==str(POOL/'full01/session.json') and q['inherited_runtime_strict_session']['path']==str(POOL/'full02/session.json') and q['original_tail_receipt']['path']==str(POOL/'full03/session.json'),'original RUN phase authority, not rewritten export paths')
 require(build['state']=='FAIL preserved, no accepted result' and runtime['state']=='FAIL preserve composite continuation; no retry or budget raise' and tail['state']=='FAIL tail protected source/end-resource check','historical failed receipts remain FAIL')
 require(build['commands'][:4]==q['inherited_build_loader_commands'] and runtime['commands'][:5]==q['inherited_runtime_strict_commands'] and tail['commands']==q['commands'],'exact accepted subsequences from each original source')
 require([(c['label'],c['returncode'])for c in build['commands'][4:]]==[('integrity-run',-9)] and [(c['label'],c['returncode'])for c in runtime['commands'][5:]]==[('counter',1)],'exact excluded partial integrity and failed counter')
 phases=q['inherited_build_loader_commands']+q['inherited_runtime_strict_commands']+q['commands']
 require([(c['label'],c['ownership']['returncode'])for c in phases]==PHASES,'exact4+5+2 accepted phases and actual exit codes')
 for c in phases:
  life=c['ownership'];require(life['failure'] is None and not life['owned_group_remaining'],'accepted phase cleanup/source ownership')
 for item in (build,runtime,tail,q):
  require(item['source_tree_baseline']==TOP and item['source_bp']==BP and item['geometry']==GEOMETRY,'same actual1536 source and geometry across all receipts')
  require(item['model']==q['model'] and item['model_stamp']==q['model_stamp'] and item['actual_source_list']==q['actual_source_list'],'same built model/stamp/consumed source list')
 require(q['model']['sha256']==MODEL_SHA and q['model']['bytes']==15839528 and q['model']['path']==str(POOL/'full01/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench'),'actual fixed clean model; no old256 substitution')
 require(q['actual_source_list']['path']==str(POOL/'full01/actual-source-list.json'),'actual full01 source provenance')
 exact(q['actual_source_list']);require(bind(q['model_stamp']['path'])==q['model_stamp'],'exact compiled model stamp')
 require(q['closed_audits']==tail['closed_audits'] and set(q['closed_audits'])=={'strict','counter','parameters'},'same three completed tail audits')
 strict=exact(q['closed_audits']['strict']);counter=exact(q['closed_audits']['counter']);params=exact(q['closed_audits']['parameters'])
 require(q['closed_audits']['strict']['path']==str(POOL/'full02/strict01/verification.json') and q['closed_audits']['counter']['path']==str(POOL/'full03/counter01/verification.json') and q['closed_audits']['parameters']['path']==str(POOL/'full03/parameters01/verification.json'),'actual strict versus fresh tail audit locations')
 require(strict['accepted'] is True and counter['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'full512/eight real winning writes/Iretire and independent firsttouch counters')
 require(params['facts']['values']==PARAMETERS and params['facts']['clean_eof'] is True,'all17 actual1536/ordinary-geometry facts throughEOF')
 require(counter['bindings']['fst']==strict['bindings']['fst'] and strict['bindings']['fst']['path']==str(POOL/'full02/advisory/trace.fst'),'same closed advisory trace')
 require(counter['bindings']['strict']==q['closed_audits']['strict'] and counter['bindings']['run']==q['corrected_run_receipt'],'counter binds actual strict/corrected-sidecar proofs')
 # Keep raw FST/event identities in the proof chain, without repeatedly hashing
 # multi-MiB raw artifacts in each source-materialization guard callback. The
 # pinned ROOT composite already qualified them; complete durable preservation
 # and independent readback remain a separate mandatory CAD evidence gate.
 require(strict['bindings']['compiled_source_list']==q['actual_source_list'],'strict actual compiled-source provenance')
 corrected=exact(q['corrected_run_receipt']);require(q['corrected_run_receipt']['path']==str(POOL/'full03/closed-run-full-bindings.json'),'exact corrected run sidecar, original receipt preserved')
 require(corrected['actual_returncode']==-6,'only known checked postPASS GPIO finalizer')
 require(corrected['trace']==strict['bindings']['fst'] and corrected['counter_values']==['1','1','1','1','8','8'],'same actual trace and six observer values in corrected sidecar')
 exact(q['original_run_receipt']);finalizer=bind(q['ROOT_finalizer']['path']);require(finalizer==q['ROOT_finalizer'],'exact ROOT final source/metadata review')
 review=q['directory_timestamp_review'];require(len(review['changes'])==1 and review['changes'][0]['path']==str(POOL/'full02/advisory'),'only reviewed input-directory timestamp change; no file exception')
 return q

def source_authority(path):
 a=json.loads(Path(path).read_text())
 require(a['schema']=='csr1536-CAD-source-authority-v2' and a['ROOT_approved'] is True and a['TOP']==TOP and a['BP']==BP,'ROOT fresh source-only authority')
 profile(a['resource_profile']);n=native(a['native_session']);s=exact(a['actual_source_list'])
 require(a['model_sha256']==n['model']['sha256'],'actual1536 model identity')
 for r in a['bindings']:require(bind(r['path'])==r,'frozen source helper/carrier')
 require({k:a['actual_source_list'][k] for k in ('bytes','sha256')}=={k:n['actual_source_list'][k] for k in ('bytes','sha256')},'portable actual consumed source bytes')
 require(Path(a['native_session']['path'])==ART/'native-proof/ROOT-composite.json' and Path(a['actual_source_list']['path'])==ART/'native-proof/actual-source-list.json','fresh HOME proof exports')
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
 a=source_authority(authority_path);p,charges=profile(a['resource_profile'])
 require(0<=source_used<=SOURCE_CAP and 0<=evidence_used<=SOURCE_EVI_CAP and 0<=helper_used<=HELPER_CAP,'source128/evidence8/helper1 caps')
 return grouped_require([(SOURCE.parent,CAPS['work_floor_bytes'],SOURCE_CAP-source_used),
  (WORK.parent,CAPS['work_floor_bytes'],CAPS['work_cap_bytes']+charges['base_RUN_bytes']+charges['current_native_RUN_bytes']),
  (HERE,CAPS['home_floor_bytes'],CAPS['evidence_cap_bytes']-evidence_used+sum(charges[k] for k in ('base_HOME_bytes','current_native_HOME_bytes','logging_HOME_bytes','metadata_HOME_bytes'))),
  (Path('/dev/shm'),CAPS['shm_floor_bytes'],charges['base_SHM_bytes'])])

def cad_limits(row):
 p,charges=profile(row)
 return dict(CAPS,source_cap_bytes=SOURCE_CAP,
  other_work_future_bytes=charges['base_RUN_bytes']+charges['current_native_RUN_bytes'],
  other_home_future_bytes=sum(charges[k] for k in ('base_HOME_bytes','current_native_HOME_bytes','logging_HOME_bytes','metadata_HOME_bytes')),
  other_shm_future_bytes=charges['base_SHM_bytes'])
