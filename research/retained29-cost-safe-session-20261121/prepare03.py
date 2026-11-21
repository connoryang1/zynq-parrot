#!/usr/bin/env python3
"""Close the self-contained COST host gate in an isolated integration tree."""
import argparse
import gzip
import json
from pathlib import Path
import sys

import prepare as first
import prepare02 as second
import portable_gate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'linux-tests'))
import retained29_protocol as base
import retained29_cost_protocol as cost
import retained29_safe_functional_protocol as functional
import test_retained29_safe_session as fixture


def inspect():
    value=second.inspect()
    value.update(preparer=base.binding(Path(__file__)),documentation=base.binding(HERE/'PORTABILITY.md'),
        portable_checker=base.binding(HERE/'portable_gate.py'),prior_preparation=base.binding(HERE/'prepared02/verification.json'),
        prior_checkpoint='08d8ea43fd1b22e0129a9ba25b5d37dcc8bc82d4',
        inert_runners=dict(accepted=base.binding(fixture.OLD_RUNNER),observer=base.binding(fixture.OBSERVER_RUNNER)),
        native_compile_receipt=base.binding(Path('/home/coyang/fpga-artifacts/context-resume/native-retained-observer-host-20261121/compile02/session.json')))
    handoff=json.loads((HERE/'handoff02.json').read_text())
    base.require(value['sources']==handoff['sources'] and value['functional_sources']==handoff['functional_sources'],
        'production runtime/source map must remain handoff02 exact')
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--record-host-gate',action='store_true');args=parser.parse_args()
    actual=inspect();out=HERE/'prepared03';path=out/'verification.json'
    if args.record_host_gate:
        base.require(not out.exists(),'fresh prepared03 required');out.mkdir()
        drafts=first.drafts(out,actual)
        for name in drafts:
            if '-plan.' not in name and '-cohort.' not in name:first.blocked(out/name)
        snapshots={}
        for name in dict.fromkeys((*first.NEW,*first.TEST_FILES,*second.CRITICAL)):
            target=out/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
            snapshots[name]=base.binding(target)
        failure=Path('/home/coyang/zynq-parrot-linux-capacity/research/retained29-cost-safe-session-20261121/integration-main/host-tests.log')
        raw=failure.read_bytes();archive=out/'integration-main-import-failure.log.gz';archive.write_bytes(gzip.compress(raw,mtime=0))
        base.require(gzip.decompress(archive.read_bytes())==raw,'lossless integration failure retention')
        failed=dict(source=base.binding(failure),archive=base.binding(archive),cause='Unintegrated capacity V3 test/draft dependency; host import failure, no target action.')
        portable=portable_gate.run(out/'portable-tree')
        base.require(inspect()==actual,'source changed during portable gate')
        record=dict(state='PASS portable isolated46 COST host checks; production map unchanged; no physical actions',**actual,
            drafts=drafts,source_snapshots=snapshots,portable_gate=portable,failed_integration=failed,
            host_tests=46,physical_actions=0,model_runs=0,launchable=False,
            actual_route=None,actual_present=None,actual_fixed_functional=None,actual_cost_cohort=None)
        first.emit(path,record)
    else:
        record=json.loads(path.read_text())
        for key,value in actual.items():base.require(record[key]==value,'prepared03 source/binding drift '+key)
        for group in ('drafts','source_snapshots'):
            for row in record[group].values():base.verify_binding(row)
        base.verify_binding(record['portable_gate']);portable=json.loads(Path(record['portable_gate']['path']).read_text())
        base.require(portable['returncode']==0 and portable['capacity_modules_present'] is False
            and portable['capacity_research_present'] is False,'isolated portable46 result')
        for row in portable['logs'].values():base.verify_binding(row)
        base.verify_binding(record['failed_integration']['archive'])
        for name in record['drafts']:
            if '-plan.' not in name and '-cohort.' not in name:first.blocked(out/name)
    print('PASS prepared03:46 isolated portable checks; production runtime unchanged; UNLAUNCHABLE')


if __name__=='__main__':main()
