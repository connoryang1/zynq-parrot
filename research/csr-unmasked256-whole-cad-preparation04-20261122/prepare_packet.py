#!/usr/bin/env python3
"""ROOT-only fresh CSR CAD draft from actual readiness and closed evidence; no launch/poll."""
import argparse,copy,json
from pathlib import Path
from contracts import ART,HERE,TOP,BP,SOURCE,WORK,LOGS,bind,exact,require,profile,cad_limits,freeze_records,SOURCE_HERE,SOURCE_ART
from cad_checks import evidence,check_bindings,OPS,SCHEMA
PREDECESSOR=Path('/home/coyang/fpga-artifacts/context-resume/borrow256-fpga-preparation-20261122/preparation01/adapter02/admission01.json')

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--resource-profile',type=Path,required=True);ap.add_argument('--resource-profile-sha256',required=True);ap.add_argument('--evidence-gates',type=Path,required=True);ap.add_argument('--evidence-gates-sha256',required=True);a=ap.parse_args()
 rp=bind(a.resource_profile);eg=bind(a.evidence_gates);require(rp['sha256']==a.resource_profile_sha256 and eg['sha256']==a.evidence_gates_sha256,'exact ROOT resource/evidence pins')
 profile(rp);e,n=evidence(eg);require(bind(PREDECESSOR)['sha256']=='8ad1456667045e9214f7928026d9b182cad5eb8262c1f282d4f70a168bcf75f2','exact prior R9 recipe, not inherited admission')
 setup_row=bind(SOURCE_ART/'actual01/session.json');s=exact(setup_row)
 require(s['state']=='PASS private-clone exact FPGA source/readiness/static Make dryrun; no CAD launch' and s['source']==str(SOURCE) and s['TOP']==TOP and s['BP']==BP,'fresh actual a44/1e7 readiness')
 files=exact(s['source_files']);cfg=copy.deepcopy(json.loads(PREDECESSOR.read_text())['configuration'])
 allfiles={str(Path(r['path']).relative_to(SOURCE)):{k:r[k] for k in ('bytes','sha256','mode')} for r in files}
 require(len(allfiles)==len(files),'unique exact tracked source paths')
 cfg.update(top=TOP,bp=BP,work_root=str(WORK),log_root=str(LOGS),prepared_source_root=str(SOURCE),prepared_source_files=allfiles,source_files={k:v for k,v in allfiles.items() if not k.startswith('import/bsg_replicant/')})
 private=exact(s['private_generated_inputs']);tools=exact(s['auxiliary']);cfg['auxiliary_bindings']=[r['copy'] for r in private]+[r['binding'] for r in tools]
 # Rebind the live maintained operational carrier by exact FILE bytes. Never
 # carry an old launcher/Tcl hash or infer bytes from a moving HEAD label.
 cfg['operational_root']=str(OPS)
 cfg['operational_files']={name:{k:bind(OPS/name)[k] for k in ('bytes','sha256')} for name in cfg['operational_files']}
 operational=[bind(OPS/name) for name in cfg['operational_files']]
 launch=dict(working_directory=str(SOURCE),environment=dict(ZP_REPO_DIR=str(SOURCE),ZP_FPGA_SEED_REPO_DIR=str(SOURCE),ZP_FPGA_LOG_ROOT=str(LOGS),ZP_FPGA_WORK_ROOT=str(WORK),FPGA_CFG='e_bp_unicore_zynqparrot_prefetch16k_cfg',FPGA_VIVADO_THREADS='8',FPGA_NUM_THREADS='',FPGA_NUM_CONTEXTS='',FPGA_ACLK_MHZ='20',FPGA_SPARSE_SOURCE='1',FPGA_CACHE_MISS_TRACE='0'),argv=[str(OPS/'codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh'),'start'])
 helper_names=['contracts.py','cad_checks.py','prepare_packet.py','prepare_admission.py','monitor_local.py','remote_probe.py','budget.py','identity.py','ownership_ledger.py','cancel_local.sh']
 bindings=[bind(HERE/x) for x in helper_names]+[bind(SOURCE_HERE/x) for x in ('contracts.py','prepare_source.py','bind_source_authority.py','software_owned_v2.py')]+operational+freeze_records(rp)+[rp,eg,setup_row]+[s[k] for k in ('source_files','private_generated_inputs','auxiliary','consumed_source_bridge','simulation_only_exclusion','authority')]+cfg['auxiliary_bindings']
 bindings += [e['native_session'],e['actual_source_list']]+[e[x]['binding'] for x in ('durable_base_closure','qualified_clone','architectural_regressions','capacity_followup')]
 bindings += [c['log'] for c in s['commands'] if c['label'] in ('readiness','make-dryrun')]
 unique={r['path']:r for r in bindings};require(all(unique[r['path']]==r for r in bindings),'no conflicting duplicate bindings')
 q=dict(schema=SCHEMA,state='DRAFT exact new CSR source/readiness/evidence; ROOT fresh resources/one-builder release required',launchable=False,top=TOP,bp=BP,configuration=cfg,resources=cad_limits(rp),resource_profile=rp,evidence_gates=eg,bindings=list(unique.values()),operational_bindings=operational,direct_launch=launch,source_preparation=setup_row,
  prerequisites=dict(fullcore=dict(ROOT_verified=True,binding=e['native_session'],model_sha256=n['model']['sha256'],source_archive=e['durable_base_closure']['binding']),fpga_source=dict(ROOT_verified=True,binding=setup_row),root_release=dict(ROOT_verified=False,binding=None)),
  source_archive_identity=dict(native=e['durable_base_closure']['binding'],consumed_bridge=s['consumed_source_bridge'],simulation_only_exclusion=s['simulation_only_exclusion']),
  source_domain_contract=dict(prepared_SOURCE_files=len(allfiles),worker_WORK_files=len(cfg['source_files']),native_actual_sources=len(exact(e['actual_source_list'])['sources']),simulation_only_exclusions=1),
  predecessor_recipe=bind(PREDECESSOR),scope='Fresh lower256 CSR snapshot-storage implementation, unchanged retained architecture/ordinary caches/2-4/native0/trace0/observe1/static16KiB/20MHz. No I-alias or capacity-policy composition; no fitted hardware/application claim.',
  admission_note='No launch/poll/vendor/board in draft maker. ROOT final exact release, actual preflight and maintained launcher are separate steps; no runtime calls to obsolete native/R9 live budget.')
 check_bindings(q,False)
 ART.mkdir(exist_ok=True)
 dest=ART/'admission.DRAFT.json'
 with dest.open('x') as f:json.dump(q,f,indent=2);f.write('\n')
 print(json.dumps(dict(state='PASS new draft bytes only, no launch',admission=bind(dest),source_counts=q['source_domain_contract']),indent=2))
if __name__=='__main__':main()
