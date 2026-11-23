"""Exact new CSR CAD source/evidence gates, separate from source-only authority."""
import json
from pathlib import Path
from contracts import ART,HERE,TOP,BP,SOURCE,WORK,LOGS,bind,exact,require,profile,native,cad_limits,freeze_records,source_authority,SOURCE_HERE,SOURCE_ART,EVIDENCE_ROOTS,POOL,MODEL_SHA,NATIVE_SHA
OPS=Path('/home/coyang/zynq-parrot-csr-opt-ops-20261122')
SCHEMA='csr768-trace0-ExploreArea-private-fpga-source-cad-v1'
from opt_checks import check_launch,expected_defines,expected_launch

def evidence(row):
 q=exact(row);require(q['schema']=='csr768-CAD-evidence-gates-v1' and q['ROOT_verified'] is True and q['TOP']==TOP and q['BP']==BP,'ROOT final source/evidence gate required')
 n=native(q['native_session']);s=exact(q['actual_source_list'])
 require({k:q['actual_source_list'][k] for k in ('bytes','sha256')}=={k:n['actual_source_list'][k] for k in ('bytes','sha256')},'current actual consumed source list')
 require(q['model_sha256']==n['model']['sha256'],'same complete model, not a stale scoped/base identity')
 for name in ('durable_base_closure','qualified_clone','architectural_regressions'):
  item=q[name];require(item['ROOT_verified'] is True,'ROOT verified prerequisite: '+name)
  require(item['TOP']==TOP and item['BP']==BP and item['native_model_sha256']==MODEL_SHA and item['native_session_sha256']==NATIVE_SHA,'explicit new768 source/native provenance: '+name)
  proof=exact(item['binding']);require(item.get('decision')=='complete-durable' and str(proof.get('state','')).startswith('PASS'),'actual closed prerequisite PASS: '+name)
 # Exact new768 clone/STD chain, never a generic historical PASS label.
 flow=exact(q['qualified_clone_flow']);require(flow['state']=='PASS-one-CSR768-observation-qualification' and q['qualified_clone_flow']['path']==str(POOL/'scoped-csr01/flow.json'),'new768 qualified flow')
 require(flow['qualification']==q['qualified_clone']['binding'],'same completed five-domain qualification')
 clone=exact(flow['qualification']);build=exact(flow['build']);admission=exact(clone['admission']);proposal=exact(admission['proposal'])
 require(clone['state']=='PASS-matched768-cold08-five-domain-literal-equivalence-strict-counter-geometry' and set(clone['domains'])=={'core252','observer_and_geometry','SP_strict162','actual_geometry17','capacity167'} and all(d['literal_bytes_equal'] for d in clone['domains'].values()),'complete literal five-domain768 proof')
 require(flow['admission']==clone['admission']==build['admission'] and admission['schema']=='csr768-observation-only-host-admission-v1' and proposal['original_TOP']==TOP and proposal['original_BP']==BP and proposal['original_model']['sha256']==MODEL_SHA and proposal['original_session']['sha256']==NATIVE_SHA,'new model/source native-to-clone chain')
 require(len(proposal['writer_leaves'])==415 and build['original_model']['sha256']==MODEL_SHA and build['baseline_relink']['sha256']==MODEL_SHA,'actual415 and untouched relink8762')
 sup=exact(q['architectural_supervision']);std=exact(q['architectural_regressions']['binding'])
 require(q['architectural_supervision']['path']==str(POOL/'scoped-csr01/architectural-regressions-supervision.json') and sup['state']=='PASS four-test phase, no hardware/app performance claim' and sup['result']==q['architectural_regressions']['binding'] and sup['clone_admission']==clone['admission'],'same new768 STD supervisor/clone/result')
 require(sup['ownership']['returncode']==0 and sup['ownership']['failure'] is None and not sup['ownership']['owned_group_remaining'],'four-test owned phase complete')
 require(std['model']==build['binary'] and q['architectural_regressions']['binding']['path']==str(POOL/'scoped-csr01/architectural-regressions01/session.json'),'all STD tests ran actual new scoped binary')
 names=['mt_context_csr_rebind_test','mt_umode_nonresident_sv39_data_handoff_test','mt_resident_reseed_irq_test','mt_protected_rpc_hardware_test']
 require([t['test'] for t in std['tests']]==names and all(t['state']=='PASS checked architectural return on new qualified model' and t['argv'][0]==std['model']['path'] for t in std['tests']),'all four unchanged tests, fixed order, same model')
 exact(sup['source'])
 follow=q['capacity_followup'];require(follow['ROOT_verified'] is True,'explicit capacity followup decision')
 proof=exact(follow['binding'])
 if follow['decision']=='complete-durable':require(str(proof.get('state','')).startswith('PASS'),'all768 complete durable prerequisite')
 else:require(follow['decision']=='ROOT-deferred-under-new-budget' and proof.get('ROOT_approved') is True and proof.get('deferred_until_after_CAD') is True and proof.get('TOP')==TOP and proof.get('BP')==BP,'no silent followup omission')
 require(q['ordinary_geometry_policy_unchanged_capacity768_opt_only'] is True,'no ordinary geometry/policy changes')
 return q,n

def check_bindings(a,require_launch=True):
 require(a['schema']==SCHEMA and a['top']==TOP and a['bp']==BP,'exact new CSR candidate')
 require(a.get('launchable') is (True if require_launch else False),'correct draft/released state')
 require(a['resources']==cad_limits(a['resource_profile']),'all fresh own/OTHER resource sums')
 for r in a['bindings']:require(bind(r['path'])==r,'changed bound source/evidence: '+r['path'])
 cfg=a['configuration'];require(cfg['top']==TOP and cfg['bp']==BP and cfg['prepared_source_root']==str(SOURCE) and cfg['work_root']==str(WORK) and cfg['log_root']==str(LOGS),'fresh source/work/log identities')
 require(cfg['expected_defines']==expected_defines(TOP),'all7 fixed compiled flags')
 require(cfg['evidence_roots']==list(map(str,EVIDENCE_ROOTS)),'fresh768 family/log single192MiB')
 require(cfg['opt_checks']==bind(HERE/'opt_checks.py') and cfg['baseline_XPR']==profile(a['resource_profile'])[0]['baseline_XPR'] and cfg['opt_directive']=='ExploreArea','actual extra OPT gate and exact XPR control')
 require(cfg['operational_root']==str(OPS) and 'codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh' in cfg['operational_files'],'bound actual isolated maintained launcher')
 launch=a['direct_launch'];check_launch(launch,SOURCE,WORK,LOGS,TOP,BP)
 setup=exact(a['source_preparation']);require(setup['state']=='PASS private-clone exact FPGA source/readiness/static Make dryrun; no CAD launch' and setup['source']==str(SOURCE) and setup['TOP']==TOP and setup['BP']==BP and len(setup['repositories'])==9,'fresh actual source/readiness')
 require(setup['script']==bind(SOURCE_HERE/'prepare_source.py') and [c['label'] for c in setup['commands']][-2:]==['readiness','make-dryrun'],'exact source helper/maintained gates')
 require(all(c['ownership']['returncode']==0 and c['ownership']['failure'] is None and not c['ownership']['owned_group_remaining'] for c in setup['commands']),'all source/readiness commands actual0/reaped')
 authority=source_authority(Path(setup['authority']['path']));require(bind(setup['authority']['path'])==setup['authority'],'source authority immutable')
 e,n=evidence(a['evidence_gates']);require(n['source_tree_baseline']==TOP and n['source_bp']==BP,'same fullcore source')
 require(a['prerequisites']['fullcore']['binding']==e['native_session'] and a['prerequisites']['fullcore']['model_sha256']==n['model']['sha256'],'exact native qualification')
 require(a['prerequisites']['fullcore']['source_archive']==e['durable_base_closure']['binding'],'fresh durable closure, not old9918')
 require(a['source_archive_identity']['simulation_only_exclusion']==setup['simulation_only_exclusion'],'exact one ghost exclusion receipt')
 exclusions=exact(setup['simulation_only_exclusion']);require(len(exclusions)==1,'no broad source exclusion')
 require(a['source_domain_contract']['prepared_SOURCE_files']==len(cfg['prepared_source_files']) and a['source_domain_contract']['worker_WORK_files']==len(cfg['source_files']),'fresh derived inventories, no inherited5255/4523')
 if require_launch:
  release=exact(a['prerequisites']['root_release']['binding'])
  for k,v in [('state','ROOT ADMITTED local clean CSR CAD'),('top',TOP),('bp',BP),('launch',launch),('resources',a['resources'])]:require(release.get(k)==v,'ROOT exact launch release: '+k)
  require(release['holds_released'] is True and release['single_vendor_builder']=='bp1' and release['board_unreserved'] is True,'ROOT final builder/board ownership gates')
  require(release['operational_bindings']==a['operational_bindings'] and release['evidence_gates']==a['evidence_gates'] and release['resource_profile']==a['resource_profile'],'exact released source/gates/profile')
 return a
