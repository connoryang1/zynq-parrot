#!/usr/bin/env python3
"""Source-only prospective clean CAD declarations, never admission promotion."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('immutable_source_reader',HERE.parent/'scratch-trace-profile-preparation02-20261122/materialize.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
from budget import LIMITS

TOP='4dadebbfdddfe958eff432b7f87280cfb9b5d991';BP='7566c67aad9b93f5546fcc5e258e405402a47850'
OPER=Path('/home/coyang/zynq-parrot-linux-cad-carrier')

def bind(p):
    p=Path(p);raw=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def main():
    prep=HERE.parent/'scratch-trace-profile-preparation-20261122/source-materialization.json'
    q=json.loads(prep.read_text());source.require(q['repositories'][0]['head']==TOP,'fixed scratch TOP')
    files={str(Path(row['path']).relative_to(source.SOURCE)):{k:row[k] for k in ('bytes','sha256')} for row in q['files']}
    # CAD-only Tcl/XDC collateral is not consumed by the simulator. Bind it
    # directly to immutable TOP objects, without materializing or staging it.
    listing=source.git(source.SOURCE,'ls-tree','-r','-l',TOP,'--','cosim/tcl','cosim/xdc').decode().splitlines()
    for line in listing:
        fields,name=line.split('\t',1);mode,kind,blob,n=fields.split()
        if kind!='blob':continue
        raw=source.git(source.SOURCE,'show',TOP+':'+name)
        source.require(len(raw)==int(n),'tracked CAD collateral bytes')
        files[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    definitions=dict(BP_RETAINED_BUFFER=1,BP_RETAINED_I_LINES=1792,BP_RETAINED_D_LINES=1792,BP_RETAINED_SETS=256,BP_RETAINED_OBSERVE=1,BP_AXI_RESPONSE_DELAY=0,BP_CACHE_MISS_TRACE=0)
    binding_paths=[HERE/n for n in ('monitor.py','remote_probe.py','budget.py','identity.py')]
    binding_paths += [OPER/'codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh',OPER/'codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh']
    admission=dict(schema='scratch1792-trace0-clean-cad-v1',state='DRAFT SOURCE ONLY NOT LAUNCHABLE',launchable=False,
        top=TOP,bp=BP,configuration=dict(top=TOP,bp=BP,work_root='/run/user/1001/zp-linux-scratch1792-trace0-cad-20261122-01',
            log_root='/home/coyang/fpga-logs-linux-retained-scratch1792-trace0',expected_hostname='blackparrot1',expected_defines=definitions,
            source_files=files,cfg='e_bp_unicore_zynqparrot_prefetch16k_cfg',aclk_mhz=20,rtclk_mhz=8,workers=8,sparse_source=1,
            geometry=dict(i_lines=1792,d_lines=1792,sets=256,epoch=8,line_bytes=64,L1I_bytes=32768,L1D_bytes=32768,L2_bytes=16384,resident=2,logical=4),
            synthesis_mode='clean-no-incremental-reference'),resources=LIMITS,bindings=[bind(p) for p in binding_paths],
        farm_cancellation=str(OPER/'codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh'),
        prerequisites=dict(fullcore=dict(ROOT_verified=True,binding=None,ROOT_reported_actual_sha256='8e5ce91dacd7315e377aa5e1cb761fe8534ba80f0551802a1a545e6f091adedf',
                original_failure_sha256='68f27565809db79e6f69485c14ded19daa6ab666498d876798c638d203dc36dc',model_sha256='3f3e8b766f19746cb434e99200c0bde49853e4c0cc27aeec7a0dbacec7f6b2df',state='actual ROOT PASS, durable independent archive binding pending'),
            uce_area=None,farm_admission=None,operational_carrier=None),
        source_preparation=bind(prep),source_archive_identity='Every declared source plus immutable CAD Tcl/XDC bytes must match actual worker files before child synthesis is accepted.',
        scope='AREA-FIT candidate1792, not selected maximum; no vendor/model/board/stage/upload/fit/application action by preparation.',
        release_requirements='NEW immutable promoted admission only after actual fullcore+ROOT verified UCE area pair+farm admitted trace0+operational carrier identity+idle/free-resource preflight; current launchable remains false.')
    path=HERE/'admission.DRAFT.json';source.require(not path.exists(),'preserve immutable draft')
    path.write_text(json.dumps(admission,indent=2)+'\n')
    lower=dict(state='DRAFT lower-bound fit fallback only, no launch',launchable=False,TOP='596e4677fdcbbf59706be254384f778861f0cc36',BP='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c',
        lines_each=256,sets=256,trace=1,L2_bytes=16384,core_MHz=20,timer_MHz=8,
        fullcore_archive=bind(Path('/home/coyang/fpga-artifacts/context-resume/retained256-qualification-20261122/closed02/archive.json')),
        remaining=['ROOT all256-slot acceptance/closure','new immutable farm/monitor/operational admission','actual CAD idle/resource gate'],
        limits='Existing qualified2c9 source is a potential fitted lower bound. It is not a matched COST capacity arm against scratch/trace0; no old4KiB pooling, launch or final maximum choice.')
    (HERE/'lower-control256.DRAFT.json').write_text(json.dumps(lower,indent=2)+'\n')
    print(path,'launchable=false',len(files),'source identities')

if __name__=='__main__':main()
