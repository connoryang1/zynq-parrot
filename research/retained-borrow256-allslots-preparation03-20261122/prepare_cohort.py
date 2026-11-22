#!/usr/bin/env python3
"""Prepare fresh monitoring-only correctness cohort; no model/reader/compiler."""
import argparse,json
from pathlib import Path
import contract as c
import fixed_shared as fixed
import ledger

SOURCE_PLAN=c.HERE/'source-plan.json'
FAILURES=Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow256-native-monitor-failure-20261122/receipts01')
FIXED_PREFLIGHT=FAILURES.parent/'fixed-preflight-export01/allslots-fixed-reserve-preflight01.json'

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true');parser.add_argument('--source-sha',required=True);a=parser.parse_args()
    c.require(a.prepare and c.bind(SOURCE_PLAN)['sha256']==a.source_sha,'ROOT exact new monitoring-only source admission')
    declared=json.loads(SOURCE_PLAN.read_text());c.require(declared['sources']==c.runtime_sources(),'all frozen new/old runtime sources')
    for row in declared['sources']:c.verify(row)
    c.require(c.bind(FIXED_PREFLIGHT)['sha256']=='302aab20afa806f6fffc659f6c7eff7b28227bba8ad8c9a9a14199808ba72c46','actual ROOT54901 fixed resource feasibility')
    failure=json.loads((FAILURES/'manifest.json').read_text())
    for row in failure['copies']:
        current=c.bind(FAILURES/row['relative']);c.require(all(current[k]==row[k]for k in ('bytes','sha256')),'original failed receipts preserved')
    c.require(c.bind(c.PREFLIGHT)['sha256']=='ca5878f852d05ac4941c9571f0401071f619d0abc4a2dd3d2af6bcb4c82bfe81','earlier actual model/source/capacity preflight')
    c.CAPS=c.caps(256*1024**2)
    policy_row=c.bind(fixed.POLICY);fixed.load(policy_row['path'],policy_row['sha256'],full=True)
    snapshot=fixed.snapshot(policy_row);model_bridge=c.bridge.read()
    c.require(not c.BASE.exists(),'fresh allslots02; never retry/overwrite failed allslots01')
    own=sum(ledger.scan(c.bridge.POOL).values());durable=sum(ledger.scan(c.bridge.DURABLE).values())
    helpers=sum(sum(ledger.scan(root).values())for root in (c.HERE,*c.bridge.PREVIOUS_HELPERS))
    c.require(own+c.CAPS['stage_total']<=snapshot['policy']['native']['pool_cap_bytes'],'entire new256MiB plus allfailed/full/clone/input bytes inside original768MiB')
    resources=fixed.live_check(snapshot,own,durable,helpers,c.bridge.POOL)
    c.BASE.mkdir();st=c.BASE.stat()
    compiled=c.BASE/'compiled-sources.json';c.archive.write_json(compiled,model_bridge['compiled_sources'])
    program=json.loads((c.old.HERE/'preparation.DRAFT.json').read_text())['program']
    record=dict(schema='borrow256-complete-allslots-v1',state='ROOT-PREPARED actual qualified borrowing256; native/audit only after explicit ROOT execution',
        stage=str(c.BASE),stage_identity=dict(path=str(c.BASE),device=st.st_dev,inode=st.st_ino),schedule=list(c.ORDER),geometry=c.GEOMETRY,caps=c.CAPS,
        runtime_sources=c.runtime_sources(),source_plan=c.bind(SOURCE_PLAN),resource_preflight=c.bind(c.PREFLIGHT),fixed_resource_preflight=c.bind(FIXED_PREFLIGHT),
        fixed_reservations=policy_row,archive_deferral_note=c.bind(fixed.NOTE),model_bridge=model_bridge,model=model_bridge['model'],
        program=program,compiled_sources=c.bind(compiled),reader=model_bridge['reader'],environment=model_bridge['environment'],linked_libraries=model_bridge['linked_libraries'],
        previous_monitor_failure=c.bind(FAILURES/'manifest.json'),failed_native_preparation=c.bind(FAILURES/'preparation.json'),
        prospective_durable_subcap=16*1024**2,existing_durable_cap=64*1024**2,existing_pool_cap=768*1024**2,
        resource_snapshot=dict(own_pool_bytes=own,other_pool_totals=snapshot['other_pool_totals'],durable_bytes=durable,helper_family_bytes=helpers,required=resources),
        archive_policy='DEFER durable archival until concurrent CAD terminal and formal freeze; this driver has NO archive helper',
        limitations='Monitoring-only source correction. Same model/062a/program/Validator/full167/caps/times; fresh D-on/audit/D-off/audit/I/audit. No fit/FPGA/application/performance claim.')
    path=c.BASE/'preparation.json';c.archive.write_json(path,record)
    c.load(path,c.bind(path)['sha256']);c.check_budget(c.BASE,record)
    print(json.dumps(c.bind(path),sort_keys=True))

if __name__=='__main__':main()
