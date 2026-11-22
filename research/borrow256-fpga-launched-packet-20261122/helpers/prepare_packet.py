#!/usr/bin/env python3
"""ROOT-only draft generation after actual source readiness; never launch/poll."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ORIGINAL=Path('/home/coyang/fpga-artifacts/context-resume/native1792-borrow-trace0-cad-20261122/admission02.json')
SOURCE='/dev/shm/zp-linux-borrow256-fpga-source-20261122-01'
TOP='1008854d30e5d923c86c3232fc22af039467d552'
BP='bb575a764c200f07c6f3259a179bdc861dd7593f'
SETUP=HERE/'actual01'
SETUP_SHA='6e8c18085ac85767a7d5442c63edec76153ef9e1866855233527e502b52e88fb'
SCRIPT_SHA='5e04a6e89f465d5ff692c19e99e521194dfa32d22759672c79b4e4e742775015'
FULL=HERE/'native-proof/session.json'
ARCHIVE=Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow256-trace0-fullcore-20261122/closed01/archive.json')
def require(v,m):
 if not v:raise RuntimeError(m)
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def main():
 require(not (HERE/'admission.DRAFT.json').exists() and not (HERE/'ROOT-release.PENDING.json').exists(),'fresh lower256 draft, preserve all prior bytes')
 require(bind(ORIGINAL)['sha256']=='10bf45af53ec9a14813082d93f93c5682dbc5b1f3030f86cf594b1ea20870a96','exact validatedR8 predecessor')
 require(bind(SETUP/'session.json')['sha256']==SETUP_SHA,'actual source/readiness receipt')
 s=json.loads((SETUP/'session.json').read_text());require(s['state']=='PASS private-clone exact FPGA source/readiness/static Make dryrun; no CAD launch' and s['source']==SOURCE and s['TOP']==TOP and s['BP']==BP and s['script']['sha256']==SCRIPT_SHA and len(s['repositories'])==9,'exact actual lower256 source readiness')
 require([c['label'] for c in s['commands']][-2:]==['readiness','make-dryrun'] and all(c['ownership']['returncode']==0 and not c['ownership']['owned_group_remaining'] and c['ownership']['failure'] is None for c in s['commands']),'all source/readiness commands actual0/cleaned')
 require((SETUP/'readiness.log').read_text().rstrip().endswith('BUILD READY'),'maintained readiness text')
 require(bind(FULL)['sha256']=='ccd530d02b959ac6d5da98d7ad08310d4c65c77942724e9e6136473e86542f4b' and bind(ARCHIVE)['sha256']=='9918f125af54570e183d249d22eef995f8da1d826d4992fcf24e568721669c59','closed lower256 fullcore/durable proof')
 from budget import LIMITS
 q=json.loads(ORIGINAL.read_text());q.update(schema='borrow256-trace0-private-fpga-source-cad-v1',state='DRAFT actual lower256 source/readiness PASS; ROOT resource/release pending',launchable=False,top=TOP,bp=BP,resources=LIMITS,predecessor_draft=bind(ORIGINAL))
 cfg=q['configuration'];cfg.update(top=TOP,bp=BP,work_root='/run/user/1001/zp-linux-borrow256-trace0-cad-20261122-01',log_root='/home/coyang/fpga-logs-linux-retained-borrow256-trace0',prepared_source_root=SOURCE)
 cfg['expected_defines'].update(BP_RETAINED_I_LINES=256,BP_RETAINED_D_LINES=256);cfg['geometry'].update(i_lines=256,d_lines=256)
 require(bind(s['source_files']['path'])==s['source_files'],'actual full tracked-source inventory')
 files=json.loads(Path(s['source_files']['path']).read_text());allfiles={str(Path(r['path']).relative_to(SOURCE)):{k:r[k] for k in ('bytes','sha256','mode')} for r in files};require(len(allfiles)==5255,'all5255 prepared source files')
 cfg['prepared_source_files']=allfiles;cfg['source_files']={k:v for k,v in allfiles.items() if not k.startswith('import/bsg_replicant/')};require(len(cfg['source_files'])==4523,'all4523 maintained worker source files')
 private=json.loads(Path(s['private_generated_inputs']['path']).read_text());tools=json.loads(Path(s['auxiliary']['path']).read_text());cfg['auxiliary_bindings']=[r['copy'] for r in private]+[r['binding'] for r in tools]
 launch=q['direct_launch'];launch['working_directory']=SOURCE;launch['environment'].update(ZP_REPO_DIR=SOURCE,ZP_FPGA_SEED_REPO_DIR=SOURCE,ZP_FPGA_LOG_ROOT=cfg['log_root'],ZP_FPGA_WORK_ROOT=cfg['work_root'],FPGA_NUM_THREADS='',FPGA_NUM_CONTEXTS='',FPGA_CACHE_MISS_TRACE='0')
 q['prerequisites']={'fullcore':dict(ROOT_verified=True,binding=bind(FULL),model_sha256='695e53dccdf418dac6e40ec1c652752e82fb7187c834dbd689ac80233445a80c',source_archive=bind(ARCHIVE),scope='lower256 fullcore only; no fitted image/allslot/application acceptance'),'fpga_source':dict(ROOT_verified=True,binding=bind(SETUP/'session.json')),'root_release':dict(ROOT_verified=False,binding=None)}
 q['source_preparation']=bind(SETUP/'session.json');q['source_archive_identity']=dict(native=bind(ARCHIVE),consumed_bridge=s['consumed_source_bridge'])
 q['scope']='Capacity-only lower256 clean whole-device fit experiment; validatedbb575/trace0/observe1/static16KiB/20MHz/2-4 frozen. No application/performance claim and no lower routed acceptance yet.'
 names=('prepare_source.py','prepare_packet.py','prepare_admission.py','monitor_local.py','remote_probe.py','budget.py','identity.py','ownership_ledger.py','cancel_local.sh','software_owned_v2.py')
 q['bindings']=[bind(HERE/n) for n in names]+[bind(FULL),bind(HERE/'native-proof/actual-source-list.json'),bind(ARCHIVE)]
 q['bindings'] += [dict(path=str(Path(cfg['operational_root'])/name),bytes=row['bytes'],sha256=row['sha256']) for name,row in cfg['operational_files'].items()]
 q['bindings'] += cfg['auxiliary_bindings']+[s[k] for k in ('source_files','private_generated_inputs','auxiliary','consumed_source_bridge')]+[c['log'] for c in s['commands'] if c['label'] in ('readiness','make-dryrun')]
 q['source_setup_contract']='Actual private-clone lower256 source;392native consumed paths plus4external/generated identities, unchanged native packages/ELFs, exact TOP defaults only.'
 q['source_domain_contract'].update(prepared_SOURCE_files=5255,worker_WORK_files=4523)
 q['resource_policy_change']='NEW lower256 prospective192MiB evidence; originalR8 limits/receipts unchanged. ROOT exact reservation/release required.'
 q['cancellation_derivation']='Exact maintained cancellation only after fresh PID/start/SID/PGID/current-parent or immutable-ledger proof for every job process and no foreign tools; no pgrp/token-only authorization.'
 for path,value in [(HERE/'admission.DRAFT.json',q),(HERE/'ROOT-release.PENDING.json',dict(state='ROOT RELEASE PENDING',holds_released=False,top=TOP,bp=BP,launch=launch,resources=LIMITS,operational_bindings=q['operational_bindings'],ROOT_basis='Pending exact resource reservation and global vendor-idle release; no launch by preparer'))]:
  with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
 print(json.dumps(dict(state='DRAFT only, ROOT resource/release required',admission=bind(HERE/'admission.DRAFT.json')),indent=2))
if __name__=='__main__':main()
