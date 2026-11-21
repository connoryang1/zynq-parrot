#!/usr/bin/env python3
"""Close the concrete offline v2 absent admission; never invoke board helpers."""
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'linux-tests'))
import retained29_protocol as p
import retained29_stage_v2 as stage
import run_retained29_session_v2 as client


def write(path,obj):path.write_text(json.dumps(obj,indent=2)+'\n')


def main():
    output=HERE/'closed-preparation-001';p.require(not output.exists(),'new output required')
    old=ROOT/'research/retained29-session-preparation-20261121/closed-preparation-002'
    base_path=old/'probe-absent.admission.json';base=json.loads(base_path.read_text())
    p.validate_admission(base)
    maintenance=Path('/home/coyang/fpga-artifacts/context-resume/retained29-board-storage-20261121/maintenance02')
    proof=json.loads((maintenance/'maintenance.json').read_text())
    p.require(proof['state']=='PASS-own-staging-recovered-intended-overlay' and proof['guest_boots']==0
              and proof['intended_bit_sha256']==base['artifacts']['bit']['sha256'] and proof.get('released_utc'),'closed maintenance context')
    prior=p.binding(maintenance/'stage.log');stage.verify_prior_durable_stage(base,prior)
    admission=dict(schema=client.SCHEMA,state='bound-functional-only',base_admission=p.binding(base_path),
                   sources=client.new_sources(),package_bundle=stage.local_bundle(base),load_stem='blackparrot_bd_1',
                   rollback=None,prior_durable_stage=prior)
    output.mkdir();path=output/'probe-absent-v2.admission.json';write(path,admission)
    client.validate_outer(path)
    tests=subprocess.run([sys.executable,'-m','unittest','-v','test_retained29_session.py',
                          'test_retained29_stage_v2.py','test_retained29_session_v2.py'],
                         cwd=ROOT/'linux-tests',capture_output=True,text=True)
    (output/'host-tests.log').write_text(tests.stdout+tests.stderr)
    p.require(tests.returncode==0,'host tests failed')
    sources=[ROOT/name for name in (*client.NEW_SOURCES,'linux-tests/test_retained29_stage_v2.py','linux-tests/test_retained29_session_v2.py')]+[Path(__file__).resolve(),HERE/'README.md']
    for source in sources:
        target=output/'source'/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(source.read_bytes())
    # Retain small closed maintenance context, never its images or mutable data.
    context=[]
    for name in ('maintenance.json','stage.log','restore-intended-load_pynq_overlay.log','remote-identity.log'):
        source=maintenance/name;target=output/'prior-maintenance02'/name;target.parent.mkdir(exist_ok=True)
        target.write_bytes(source.read_bytes());context.append(p.binding(source))
    write(output/'manifest.json',dict(state='PASS offline v2 preparation; no board call or target result',
        tests=36,tests_scope='15 unchanged-v1 +21new host tests; physical steps mocked, exact audit body tested locally only',
        admission=p.binding(path),sources=[p.binding(source) for source in sources],base_preparation_manifest=p.binding(old/'manifest.json'),
        frozen_v1_sources_unchanged=base['sources'],prior_closed_maintenance=context,
        outputs=[p.binding(file) for file in sorted(output.rglob('*')) if file.is_file()],
        command=['python3','linux-tests/run_retained29_session_v2.py',str(path),'--execute','NEW_EXTERNAL_OUTPUT_REQUIRES_ROOT_LAUNCH'],
        scope='One absent functional probe; no present/benchmark/routed-capacity/retained-hit/performance claim; no uploads on exact cache hit; explicit sync and two subsequent full hash audits mandatory.'))
    print(output/'manifest.json')


if __name__=='__main__':main()
