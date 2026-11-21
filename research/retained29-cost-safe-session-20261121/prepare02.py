#!/usr/bin/env python3
"""Reclose transitive functional source bindings without changing prepared01."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import prepare as prior

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'linux-tests'))
import retained29_protocol as base
import retained29_cost_protocol as cost
import retained29_safe_functional_protocol as functional

CRITICAL=('linux-tests/run_retained29_application_session.py','linux-tests/retained29_application_protocol.py')


def inspect():
    actual=prior.inspect()
    actual.update(preparer=base.binding(Path(__file__)),documentation=base.binding(HERE/'FOLLOWUP.md'),
        prior_preparer=base.binding(HERE/'prepare.py'),prior_preparation=base.binding(HERE/'prepared01/verification.json'),
        prior_checkpoint='d75cd31c689daef90dab25980cc15e5864e366d5',
        imported_runtime={name:base.binding(ROOT/name) for name in CRITICAL})
    old=json.loads((HERE/'prepared01/verification.json').read_text())
    for name in CRITICAL:
        base.require(name in functional.SOURCE_FILES and functional.source_hashes()[name]==old['legacy_sources'][name],
            'unchanged critical runtime import now explicitly functional-bound')
    return actual


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--record-host-gate',action='store_true');args=parser.parse_args()
    actual=inspect();out=HERE/'prepared02';path=out/'verification.json'
    if args.record_host_gate:
        base.require(not out.exists(),'fresh prepared02 required');out.mkdir()
        drafts=prior.drafts(out,actual)
        for name in drafts:
            if '-plan.' not in name and '-cohort.' not in name:prior.blocked(out/name)
        snapshots={}
        for name in dict.fromkeys((*prior.NEW,*prior.TEST_FILES,*CRITICAL)):
            target=out/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
            snapshots[name]=base.binding(target)
        command=[sys.executable,'-B','-m','unittest','-v',*prior.TESTS]
        result=subprocess.run(command,cwd=ROOT/'linux-tests',env=dict(os.environ,R29_COST_HOST_FIXTURE_DIR=str(out/'host-fixtures')),
            capture_output=True,text=True,timeout=120)
        (out/'stdout.log').write_text(result.stdout);(out/'stderr.log').write_text(result.stderr)
        base.require(result.returncode==0 and 'Ran 46 tests' in result.stderr and result.stderr.rstrip().endswith('OK'),'46 host checks failed')
        seal=subprocess.run([sys.executable,'-B',str(ROOT/'research/retained-capacity-recovery-v3-20261121/close.py')],
            cwd=ROOT,capture_output=True,text=True,timeout=60)
        (out/'prior-seal.log').write_text(seal.stdout+seal.stderr);base.require(seal.returncode==0,'prior V1/V2/V3/native seal')
        base.require(inspect()==actual,'source changed during final gate')
        value=dict(state='PASS offline COST and safe-functional transitive runtime binding gate only',**actual,
            drafts=drafts,source_snapshots=snapshots,host_command=command,host_tests=46,host_returncode=result.returncode,
            logs={name:base.binding(out/name) for name in ('stdout.log','stderr.log','prior-seal.log')},
            host_fixtures={str(p.relative_to(out)):base.binding(p) for p in sorted((out/'host-fixtures').rglob('*')) if p.is_file()},
            physical_actions=0,model_runs=0,launchable=False,actual_route=None,actual_present=None,
            actual_fixed_functional=None,actual_cost_cohort=None)
        prior.emit(path,value)
    else:
        recorded=json.loads(path.read_text())
        for key,value in actual.items():base.require(recorded[key]==value,'prepared02 source/binding drift '+key)
        for group in ('drafts','source_snapshots','logs','host_fixtures'):
            for row in recorded[group].values():base.verify_binding(row)
        for name in recorded['drafts']:
            if '-plan.' not in name and '-cohort.' not in name:prior.blocked(out/name)
    print('PASS prepared02:46 offline host checks; transitive imports bound; old21/prepared01 unchanged; UNLAUNCHABLE')


if __name__=='__main__':main()
