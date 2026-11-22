#!/usr/bin/env python3
"""Prepare only from actual ROOT FPGA-source readiness; never poll or launch."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PREV=HERE.parent/'borrow-trace0-cad-home2500-20261122'
SETUP=HERE.parent/'borrow-fpga-source-preparation-20261122/actual02'
SOURCE='/dev/shm/zp-linux-borrow-fpga-source-20261122-01'
SETUP_SHA='9b19423de98ebbf2d179cf93fcad0868c2f443d7f260f1cafcb44988bebcfe73'

def bind(p):
    p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def require(ok,message):
    if not ok:raise RuntimeError(message)

def main():
    require(not (HERE/'admission.DRAFT.json').exists() and not (HERE/'ROOT-release.PENDING.json').exists(),'preserve any prior generated admission')
    source=json.loads((SETUP/'session.json').read_text())
    require(source['state']=='PASS private-clone exact FPGA source/readiness/static Make dryrun; no CAD launch','actual source setup must PASS')
    require(source['script']['sha256']==SETUP_SHA,'fixed reviewed source preparer')
    require(source['source']==SOURCE and len(source['repositories'])==9,'actual isolated complete source')
    require(all(c['ownership']['returncode']==0 and not c['ownership']['owned_group_remaining'] and c['ownership']['failure'] is None for c in source['commands']),'all source/readiness groups complete')
    require([c['label'] for c in source['commands']][-2:]==['readiness','make-dryrun'],'real readiness/dryrun required')
    require((SETUP/'readiness.log').read_text().rstrip().endswith('BUILD READY'),'actual readiness text')
    require(bind(PREV/'admission.DRAFT.json')['sha256']=='dc6ea2ec02ae1b7b9de3545034d5728d7df42d75d0f82c95f0d50ad713f14d8b','exact previous unlaunched draft')
    q=json.loads((PREV/'admission.DRAFT.json').read_text())
    require(source['TOP']==q['top'] and source['BP']==q['bp'],'same actual source revision')
    for name in ('budget.py','identity.py','cancel_local.sh','prepare_admission.py'):
        (HERE/name).write_bytes((PREV/name).read_bytes())
    s=(PREV/'monitor_local.py').read_text().replace('borrow1792-trace0-local-clean-cad-v1','borrow1792-trace0-private-fpga-source-cad-v1')
    s=s.replace('/home/coyang/zynq-parrot-linux-borrow-profile',SOURCE).replace("FPGA_NUM_THREADS='2',FPGA_NUM_CONTEXTS='4'","FPGA_NUM_THREADS='',FPGA_NUM_CONTEXTS=''")
    s=s.replace("('fullcore','root_release')","('fullcore','fpga_source','root_release')")
    point=" full=json.loads(Path(admission['prerequisites']['fullcore']['binding']['path']).read_text())"
    s=s.replace(point,""" prepared_source=json.loads(Path(admission['prerequisites']['fpga_source']['binding']['path']).read_text())
 if prepared_source['state']!='PASS private-clone exact FPGA source/readiness/static Make dryrun; no CAD launch' or prepared_source['source']!='"""+SOURCE+"""' or prepared_source['script']['sha256']!='"""+SETUP_SHA+"""':raise RuntimeError('wrong actual private FPGA source readiness')
 if prepared_source['TOP']!=config['top'] or prepared_source['BP']!=config['bp'] or len(prepared_source['repositories'])!=9:raise RuntimeError('private source/configuration mismatch')
"""+point)
    (HERE/'monitor_local.py').write_text(s)
    s=(PREV/'remote_probe.py').read_text()
    needle=" result['memory_kB']="
    extra=""" result['auxiliary_source_identity']=[]
 for expected in CONFIG['auxiliary_bindings']:
  p=Path(expected['path'])
  if not p.is_file():result['identity_violations'].append(dict(kind='missing_private_or_tool_auxiliary',expected=expected));continue
  actual=binding(p)[0];result['auxiliary_source_identity'].append(actual)
  if actual!=expected:result['identity_violations'].append(dict(kind='changed_private_or_tool_auxiliary',actual=actual,expected=expected))
"""
    require(needle in s,'exact prior probe anchor');s=s.replace(needle,extra+needle)
    s=s.replace('def process_table():',"""def source_record(p,expected):
 mode='120000' if p.is_symlink() else '100755' if p.stat().st_mode & 0o111 else '100644'
 raw=os.readlink(p).encode() if mode=='120000' else p.read_bytes()
 return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),mode=mode)

"""+'def process_table():')
    s=s.replace("  if p.is_file():\n   actual=binding(p)[0]", "  if p.is_file() or p.is_symlink():\n   actual=source_record(p,expected)\n   if actual['mode']!=expected['mode']:result['identity_violations'].append(dict(kind='snapshot_source_mode',path=relative,actual=actual['mode'],expected=expected['mode']))")
    prepared=""" result['prepared_source_identity']=dict(verified=0,expected=len(CONFIG['prepared_source_files']))
 for relative,expected in CONFIG['prepared_source_files'].items():
  p=Path(CONFIG['prepared_source_root'])/relative
  if not (p.is_file() or p.is_symlink()):result['identity_violations'].append(dict(kind='missing_prepared_source',path=str(p)));continue
  actual=source_record(p,expected)
  if any(actual[k]!=expected[k] for k in ('bytes','sha256','mode')):result['identity_violations'].append(dict(kind='changed_prepared_source',path=str(p),actual=actual,expected=expected))
  else:result['prepared_source_identity']['verified']+=1
 result['cadenv_stub']=[]
 for p in (Path(CONFIG['prepared_source_root'])/'bsg_cadenv/cadenv.mk',WORK/'bsg_cadenv/cadenv.mk'):
  if p.is_file():
   record,_=binding(p);result['cadenv_stub'].append(record)
   if record['bytes']!=0:result['identity_violations'].append(dict(kind='unexpected_nonempty_cadenv',actual=record))
  elif str(p).startswith(CONFIG['prepared_source_root']+'/'):result['identity_violations'].append(dict(kind='missing_prepared_empty_cadenv',path=str(p)))
"""
    s=s.replace(" result['memory_kB']=",prepared+" result['memory_kB']=")
    (HERE/'remote_probe.py').write_text(s)
    q.update(schema='borrow1792-trace0-private-fpga-source-cad-v1',state='DRAFT actual FPGA readiness passed; ROOT CAD release pending',launchable=False,predecessor_draft=bind(PREV/'admission.DRAFT.json'))
    files=json.loads(Path(source['source_files']['path']).read_text())
    require(bind(source['source_files']['path'])==source['source_files'],'source file inventory bytes')
    allfiles={str(Path(r['path']).relative_to(SOURCE)):{k:r[k] for k in ('bytes','sha256','mode')} for r in files}
    require(len(allfiles)==5255,'full prepared source inventory')
    q['configuration'].update(prepared_source_files=allfiles,prepared_source_root=SOURCE,source_files={k:v for k,v in allfiles.items() if not k.startswith('import/bsg_replicant/')})
    require(len(q['configuration']['source_files'])==4523,'exact maintained worker materialization domain')
    q['source_domain_contract']=dict(prepared_SOURCE_files=5255,worker_WORK_files=4523,explicit_worker_exclusion='import/bsg_replicant: extra prepared source only; maintainedworkerdoesnotinitializeit andactualnative396containszeroinputsfromit',evidence='Exact3dae cosim/black-parrot-example/tcl andhardwaremakefiles have no retainedreplicant source; onlygenericunused environment/include paths',cadenv='Actual Make-n remade optional includedfile, attemptedread-only ls-remote andcreatedemptyprivatecadenv; no clone/dependencyadvance. Actual source/worker cadenvmustremainempty; no inventedenvcarrier.')
    private=json.loads(Path(source['private_generated_inputs']['path']).read_text())
    tools=json.loads(Path(source['auxiliary']['path']).read_text())
    auxiliary=[r['copy'] for r in private]+[r['binding'] for r in tools]
    q['configuration']['auxiliary_bindings']=auxiliary
    launch=q['direct_launch'];launch['working_directory']=SOURCE
    launch['environment'].update(ZP_REPO_DIR=SOURCE,ZP_FPGA_SEED_REPO_DIR=SOURCE,FPGA_NUM_THREADS='',FPGA_NUM_CONTEXTS='')
    q['prerequisites']['fpga_source']=dict(ROOT_verified=True,binding=bind(SETUP/'session.json'))
    q['source_preparation']=bind(SETUP/'session.json')
    q['bindings']=[bind(HERE/n) for n in ('monitor_local.py','remote_probe.py','budget.py','identity.py','cancel_local.sh','prepare_admission.py','prepare_packet.py')]
    previous=json.loads((PREV/'admission.DRAFT.json').read_text())
    q['bindings'] += [r for r in previous['bindings'] if Path(r['path']).parent!=PREV]
    q['bindings']+=auxiliary
    q['bindings']+=[source[k] for k in ('source_files','private_generated_inputs','auxiliary','consumed_source_bridge')]
    q['bindings'] += [c['log'] for c in source['commands'] if c['label'] in ('readiness','make-dryrun')]
    q['source_setup_contract']='Actual private local shared-object clones; private generated PLIC/bootrom;392native consumed sources byte-equal with normalized root;4external/generated bytes unchanged. Native source/config preserved. Empty dimension overrides select exact static2/4 config.'
    archive=bind(Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow-trace0-fullcore-20261122/closed01/archive.json'))
    require(archive['sha256']=='4c7d0c341c1aa4d98bb2001733d14d5111685193dc0a78d68b0d8ce49634d7f8','ROOT lossless fullcore archive')
    q['prerequisites']['fullcore']['source_archive']=archive;q['bindings'].append(archive)
    q['prerequisites']['fullcore']['state']='ROOT actual11phase fullcore PASS13eeb; ROOT lossless archive4c7d closed; no new FST replay by preparation'
    release=json.loads((PREV/'ROOT-release.PENDING.json').read_text());release['launch']=launch
    with (HERE/'admission.DRAFT.json').open('x') as f:json.dump(q,f,indent=2);f.write('\n')
    with (HERE/'ROOT-release.PENDING.json').open('x') as f:json.dump(release,f,indent=2);f.write('\n')
    print(json.dumps(dict(state='DRAFT only no launch',admission=bind(HERE/'admission.DRAFT.json')),indent=2))

if __name__=='__main__':main()
