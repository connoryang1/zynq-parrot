#!/usr/bin/env python3
"""ROOT-only fresh CSR CAD draft from actual readiness and closed evidence; no launch/poll."""
import argparse,copy,json
from pathlib import Path
from contracts import ART,HERE,TOP,BP,SOURCE,WORK,LOGS,bind,exact,require,profile,cad_limits,freeze_records,SOURCE_HERE,SOURCE_ART,EVIDENCE_ROOTS
from cad_checks import evidence,check_bindings,OPS,SCHEMA
from opt_checks import expected_launch,expected_defines
PREDECESSOR=Path('/home/coyang/fpga-artifacts/context-resume/borrow256-fpga-preparation-20261122/preparation01/adapter02/admission01.json')

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--resource-profile',type=Path,required=True);ap.add_argument('--resource-profile-sha256',required=True);ap.add_argument('--evidence-gates',type=Path,required=True);ap.add_argument('--evidence-gates-sha256',required=True);a=ap.parse_args()
 rp=bind(a.resource_profile);eg=bind(a.evidence_gates);require(rp['sha256']==a.resource_profile_sha256 and eg['sha256']==a.evidence_gates_sha256,'exact ROOT resource/evidence pins')
 profile(rp);e,n=evidence(eg);require(bind(PREDECESSOR)['sha256']=='8ad1456667045e9214f7928026d9b182cad5eb8262c1f282d4f70a168bcf75f2','exact prior R9 recipe, not inherited admission')
 setup_row=bind(SOURCE_ART/'actual01/session.json');s=exact(setup_row)
 require(s['state']=='PASS private-clone exact FPGA source/readiness/static Make dryrun; no CAD launch' and s['source']==str(SOURCE) and s['TOP']==TOP and s['BP']==BP,'fresh actual1280 ExploreArea readiness')
 files=exact(s['source_files']);cfg=copy.deepcopy(json.loads(PREDECESSOR.read_text())['configuration'])
 allfiles={str(Path(r['path']).relative_to(SOURCE)):{k:r[k] for k in ('bytes','sha256','mode')} for r in files}
 require(len(allfiles)==len(files),'unique exact tracked source paths')
 cfg.update(evidence_roots=list(map(str,EVIDENCE_ROOTS)),expected_defines=expected_defines(TOP),opt_checks=bind(HERE/'opt_checks.py'),baseline_XPR=profile(rp)[0]['baseline_XPR'],opt_directive='ExploreArea',top=TOP,bp=BP,work_root=str(WORK),log_root=str(LOGS),prepared_source_root=str(SOURCE),prepared_source_files=allfiles,source_files={k:v for k,v in allfiles.items() if not k.startswith('import/bsg_replicant/')})
 private=exact(s['private_generated_inputs']);tools=exact(s['auxiliary']);cfg['auxiliary_bindings']=[r['copy'] for r in private]+[r['binding'] for r in tools]
 # Rebind the live maintained operational carrier by exact FILE bytes. Never
 # carry an old launcher/Tcl hash or infer bytes from a moving HEAD label.
 cfg['operational_root']=str(OPS)
 cfg['operational_files']={name:{k:bind(OPS/name)[k] for k in ('bytes','sha256')} for name in cfg['operational_files']}
 operational=[bind(OPS/name) for name in cfg['operational_files']]
 launch=expected_launch(SOURCE,WORK,LOGS)
 helper_names=['contracts.py','cad_checks.py','prepare_packet.py','prepare_admission.py','monitor_local.py','remote_probe.py','budget.py','identity.py','ownership_ledger.py','cancel_local.sh','opt_checks.py']
 bindings=[bind(HERE/x) for x in helper_names]+[bind(SOURCE_HERE/x) for x in ('contracts.py','prepare_source.py','bind_source_authority.py','software_owned_v2.py')]+operational+freeze_records(rp)+[rp,eg,setup_row]+[s[k] for k in ('source_files','private_generated_inputs','auxiliary','consumed_source_bridge','simulation_only_exclusion','authority')]+cfg['auxiliary_bindings']
 bindings += [e['native_session'],e['actual_source_list']]+[e[x]['binding'] for x in ('durable_base_closure','qualified_clone','architectural_regressions','capacity_followup')]
 bindings += [e['qualified_clone_flow'],e['architectural_supervision']]
 bindings += [c['log'] for c in s['commands'] if c['label'] in ('readiness','make-dryrun')]
 unique={r['path']:r for r in bindings};require(all(unique[r['path']]==r for r in bindings),'no conflicting duplicate bindings')
 q=dict(schema=SCHEMA,state='DRAFT exact new CSR1280 source/readiness/evidence; ROOT fresh resources/native1280/evidence/one-builder release required',launchable=False,top=TOP,bp=BP,configuration=cfg,resources=cad_limits(rp),resource_profile=rp,evidence_gates=eg,bindings=list(unique.values()),operational_bindings=operational,direct_launch=launch,source_preparation=setup_row,
  prerequisites=dict(fullcore=dict(ROOT_verified=True,binding=e['native_session'],model_sha256=n['model']['sha256'],source_archive=e['durable_base_closure']['binding']),fpga_source=dict(ROOT_verified=True,binding=setup_row),root_release=dict(ROOT_verified=False,binding=None)),
  source_archive_identity=dict(native=e['durable_base_closure']['binding'],consumed_bridge=s['consumed_source_bridge'],simulation_only_exclusion=s['simulation_only_exclusion']),
  source_domain_contract=dict(prepared_SOURCE_files=len(allfiles),worker_WORK_files=len(cfg['source_files']),native_actual_sources=len(exact(e['actual_source_list'])['sources']),simulation_only_exclusions=1),
  predecessor_recipe=bind(PREDECESSOR),scope='Fresh1280 I+D CSR unmasked storage, ExploreArea OPT only, unchanged BP/ordinary geometry/2-4/native0/trace0/observe1/static16KiB/20MHz. Area-fit candidate, not fitted/max or application evidence.',
  admission_note='No launch/poll/vendor/board in draft maker. ROOT final exact release, actual preflight and maintained launcher are separate steps; no runtime calls to obsolete native/R9 live budget.')
 check_bindings(q,False)
 ART.mkdir(exist_ok=True)
 dest=ART/'admission.DRAFT.json'
 with dest.open('x') as f:json.dump(q,f,indent=2);f.write('\n')
 print(json.dumps(dict(state='PASS new draft bytes only, no launch',admission=bind(dest),source_counts=q['source_domain_contract']),indent=2))
if __name__=='__main__':main()
