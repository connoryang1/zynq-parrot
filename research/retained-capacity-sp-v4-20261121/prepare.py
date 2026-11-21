#!/usr/bin/env python3
"""Prepare an SP-only V4 diagnostic with no allowlist or physical actions."""
import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'linux-tests'))
import retained_capacity_diagnostic_v3 as previous
import retained_capacity_diagnostic_v4 as p

SP=ROOT/'research/native-retained-sp-candidate-bridge-20261121/review01/candidate-bridge.PREPARED.json'


def emit(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def inspect():
    draft=json.loads((HERE/'prepared01/diagnostic.DRAFT.json').read_text());p.verify_programs(draft)
    bridge=p.verify_prepared_sp(draft['candidate_bridge'])
    p.require(draft['schema']==p.SCHEMA and draft['state']=='DRAFT-UNLAUNCHABLE'
        and draft['sources']==p.source_hashes() and not p.REVIEWED_CANDIDATE_BRIDGES,'V4 default offline freeze')
    dependencies=json.loads((HERE/'dependency-manifest.json').read_text())
    p.require(dependencies['runtime_sources']==p.source_hashes() and dependencies['v3_sources']==previous.source_hashes(),
        'frozen dependency/source continuity')
    for name,row in dependencies['capacity_dependencies'].items():
        p.verify_binding(row);p.require(row['sha256']==p.source_hashes()[name],'exact dependency snapshot')
    return dict(state='PASS SP-only V4 offline preparation; empty approval and physical artifacts',
        draft=p.binding(HERE/'prepared01/diagnostic.DRAFT.json'),sources=p.source_hashes(),
        dependency_manifest=p.binding(HERE/'dependency-manifest.json'),prepared_sp=draft['candidate_bridge'],
        candidate=bridge['candidate'],programs=draft['programs'],native_runner=draft['runner'],rollback_runner=draft['rollback_runner'],
        tests=p.binding(ROOT/'linux-tests/test_retained_capacity_diagnostic_v4.py'),
        documentation=p.binding(HERE/'README.md'),preparer=p.binding(Path(__file__)),
        physical_actions=0,new_model_runs=0,allowlist_approved=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--record-host-gate',action='store_true');args=parser.parse_args()
    out=HERE/'prepared01';path=out/'verification.json'
    if args.record_host_gate:
        p.require(not out.exists(),'fresh V4 gate required');out.mkdir()
        old=ROOT/'research/retained-capacity-recovery-v3-20261121/prepared02/diagnostic.DRAFT.json'
        a=json.loads(old.read_text());a.update(schema=p.SCHEMA,sources=p.source_hashes(),candidate_bridge=p.binding(SP),
            unlaunchable_reasons=['EMPTY V4 SP candidate allowlist; root independent review required.',
                'Actual SP routed fit/package/MMIO/elaboration and rollback bindings pending.',
                'Historical all-slot model evidence was not rerun on SP; no physical capacity acceptance yet.'])
        emit(out/'diagnostic.DRAFT.json',a)
        copied={}
        for name in previous.SOURCE_FILES:
            if 'retained_capacity' in name:
                target=HERE/'dependencies'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes());copied[name]=p.binding(target)
        emit(HERE/'dependency-manifest.json',dict(runtime_sources=p.source_hashes(),v3_sources=previous.source_hashes(),
            capacity_dependencies=copied,source_draft=p.binding(old),production_changes='New V4 contract/client only; all dependency bytes unchanged.'))
        actual=inspect();command=[sys.executable,'-B','-m','unittest','-v','test_retained_capacity_diagnostic_v4']
        result=subprocess.run(command,cwd=ROOT/'linux-tests',capture_output=True,text=True,timeout=60)
        (out/'stdout.log').write_text(result.stdout);(out/'stderr.log').write_text(result.stderr)
        p.require(result.returncode==0 and 'Ran 8 tests' in result.stderr and result.stderr.rstrip().endswith('OK'),'eight V4 checks')
        p.require(inspect()==actual,'source changed during V4 host gate')
        actual.update(host_tests=8,host_command=command,returncode=result.returncode,
            logs={name:p.binding(out/name) for name in ('stdout.log','stderr.log')})
        emit(path,actual)
    else:
        actual=inspect();record=json.loads(path.read_text())
        for key,value in actual.items():p.require(record[key]==value,'V4 proof drift '+key)
        for row in record['logs'].values():p.verify_binding(row)
    print('PASS SP-only V4:8 offline checks, frozen V3 recovery; EMPTY allowlist; UNLAUNCHABLE')


if __name__=='__main__':main()
