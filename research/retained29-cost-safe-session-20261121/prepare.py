#!/usr/bin/env python3
"""Retain new COST/safe-wrapper offline evidence; no target or build actions."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'linux-tests'))
import retained29_protocol as base
import retained29_cost_protocol as cost
import retained29_safe_functional_protocol as functional
import retained29_safe_session as safe
from test_retained29_cost_admission import programs

TESTS=('test_retained29_cost_protocol','test_retained29_cost_admission','test_retained29_safe_session')
NEW=tuple(name for name in cost.SOURCE_FILES if name not in cost.FROZEN)
TEST_FILES=tuple('linux-tests/'+name+'.py' for name in TESTS)


def emit(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def inspect():
    actual=programs();cost.validate_programs(actual)
    before=base.ROOT/'research/retained-trigger-accounting-20261121/closed-cost01/verification.json'
    proof=json.loads(before.read_text())
    original=next(row['original'] for row in proof['snapshots'] if row['original']['path'].endswith('/manifest.json'))
    base.verify_binding(original);manifest=json.loads(Path(original['path']).read_text())
    base.require(manifest['legacy_sources_before']==manifest['legacy_sources_after']==cost.original.source_hashes(),
        'all21 old application source bytes unchanged')
    return dict(programs=actual,legacy_sources=cost.original.source_hashes(),sources=cost.source_hashes(),
        functional_sources=functional.source_hashes(),tests={name:base.binding(ROOT/name) for name in TEST_FILES},
        preparer=base.binding(Path(__file__)),documentation=base.binding(HERE/'README.md'))


def drafts(out,actual):
    reasons=['Actual selected routed bit/package/fit binding pending; canceled r2 and AREA diagnostic fits cannot qualify.',
        'Actual successful new-safe present probe and unchanged fixed functional on exact selected bit pending.',
        'Actual verified previous overlay rollback triplet and reviewed V2 staging admission pending.',
        'Independent reviewed plan/cohort/visit chronology pending; drafts are not preregistration or acquisition.']
    for role in functional.ROLES:
        old=ROOT/'research/retained29-session-preparation-20261121/closed-preparation-002'/(role+'.DRAFT.json')
        emit(out/(role+'.DRAFT.json'),dict(schema=functional.ADMISSION_SCHEMA,state='DRAFT-UNLAUNCHABLE',role=role,
            stage_admission=None,supervisor_sources=actual['functional_sources'],prior_safe_present=None,
            original_guest_template=base.binding(old),unlaunchable_reasons=reasons))
    hardware=dict(cfg='e_bp_unicore_zynqparrot_prefetch16k_cfg',l1i_bytes=32768,l1d_bytes=32768,l2_bytes=16384,
        retained=dict(i_lines=1280,d_lines=1280,set_log2=8))
    for work in (None,*cost.WORKLOADS):
        role='cost-pilot-functional' if work is None else 'cost-performance-acquisition';plan=cost.plan_for(role,work)
        label='pilot' if work is None else work
        a=dict(schema=cost.SCHEMA,state='DRAFT-UNLAUNCHABLE',role=role,host='xilinx@192.168.4.35',runtime_ms=3600000,
            one_guest_boot=True,runner_sha256=base.RUNNER_SHA,board_helper_sha256=base.HELPER_SHA,plan=plan,
            hardware=hardware,hardware_binding_state='proposed geometry only, no selected route/capability proof',
            artifacts=None,capability_gate=None,functional_gate=None,stage_admission=None,plan_record=None,cohort_record=None,visit_id=None,
            sources=actual['sources'],legacy_sources=actual['legacy_sources'],unlaunchable_reasons=reasons,**actual['programs'])
        emit(out/(label+'.DRAFT.json'),a)
        emit(out/(label+'-plan.DRAFT.json'),dict(schema=cost.PLAN_SCHEMA,state='DRAFT-UNLAUNCHABLE',declared_utc=None,
            plan=plan,sources=actual['sources'],elf_sha256=cost.ELF_SHAS,primary='WHOLE',secondary='steady',effect_selection='none'))
        emit(out/(label+'-cohort.DRAFT.json'),dict(schema='bp-retained29-cost-cohort-v1',state='DRAFT-UNLAUNCHABLE',
            declared_utc=None,sources=actual['sources'],elf_sha256=cost.ELF_SHAS,artifacts=None,visits=[],
            requirements='Explicit fixed visits/order, >=2 independent boots per performance workload; no automatic reruns.'))
    return {path.name:base.binding(path) for path in sorted(out.glob('*.DRAFT.json'))}


def blocked(path):
    a=json.loads(path.read_text())
    try:
        (functional if a['schema']==functional.ADMISSION_SCHEMA else cost).validate_admission(a)
    except ValueError as error:
        base.require('UNLAUNCHABLE' in str(error),'draft refusal reason');return
    raise ValueError('draft became launchable')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--record-host-gate',action='store_true');args=parser.parse_args()
    actual=inspect();out=HERE/'prepared01';record_path=out/'verification.json'
    if args.record_host_gate:
        base.require(not out.exists(),'fresh output required');out.mkdir()
        records=drafts(out,actual)
        for path in out.glob('*.DRAFT.json'):
            if '-plan.' not in path.name and '-cohort.' not in path.name:blocked(path)
        source_records={}
        for name in (*NEW,*TEST_FILES):
            target=out/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
            source_records[name]=base.binding(target)
        command=[sys.executable,'-B','-m','unittest','-v',*TESTS]
        env=dict(os.environ,R29_COST_HOST_FIXTURE_DIR=str(out/'host-fixtures'))
        result=subprocess.run(command,cwd=ROOT/'linux-tests',env=env,capture_output=True,text=True,timeout=120)
        (out/'stdout.log').write_text(result.stdout);(out/'stderr.log').write_text(result.stderr)
        base.require(result.returncode==0 and result.stderr.rstrip().endswith('OK'),'host gate failed; preserve failure output')
        prior=subprocess.run([sys.executable,'-B',str(ROOT/'research/retained-capacity-recovery-v3-20261121/close.py')],cwd=ROOT,capture_output=True,text=True,timeout=60)
        (out/'prior-seal.log').write_text(prior.stdout+prior.stderr);base.require(prior.returncode==0,'prior capacity V1/V2/V3/native seal')
        base.require(inspect()==actual,'source changed during host gate; preserve this attempt and repeat offline')
        forensic=Path('/home/coyang/fpga-artifacts/context-resume/linux-host-test-recovery-20261121/stuck-unittest01.json')
        base.require(forensic.is_file(),'bound root forensic receipt required')
        record=dict(state='PASS offline COST and separately safe unchanged functional preparation only',**actual,
            drafts=records,source_snapshots=source_records,host_command=command,host_returncode=result.returncode,
            logs={name:base.binding(out/name) for name in ('stdout.log','stderr.log','prior-seal.log')},
            failed_host_fixture=dict(forensic=base.binding(forensic),exec_session=50449,actual_exit=137,
                cause='Missing mock outer entered held recovery. Fixture corrected; unexpected default test waits now stop boundedly.'),
            host_fixtures={str(path.relative_to(out)):base.binding(path) for path in sorted((out/'host-fixtures').rglob('*')) if path.is_file()},
            physical_actions=0,model_runs=0,new_compiles='Host mocked C only; fixed RV64 ELFs unchanged',
            launchable=False,actual_route=None,actual_present=None,actual_fixed_functional=None,actual_cost_cohort=None)
        emit(record_path,record)
    else:
        record=json.loads(record_path.read_text())
        for key,value in actual.items():base.require(record[key]==value,'source/binding drift '+key)
        for group in ('drafts','source_snapshots','logs','host_fixtures'):
            for row in record[group].values():base.verify_binding(row)
        base.verify_binding(record['failed_host_fixture']['forensic'])
        for name in record['drafts']:
            if '-plan.' not in name and '-cohort.' not in name:blocked(out/name)
    print('PASS offline COST/safe-functional host gate; old21 unchanged; DRAFT UNLAUNCHABLE; no physical actions')


if __name__=='__main__':main()
