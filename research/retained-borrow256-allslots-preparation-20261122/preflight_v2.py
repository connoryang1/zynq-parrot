#!/usr/bin/env python3
"""ROOT read-only source/resource preflight; no native, reader, compiler or stage."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
bridge_path=Path(__file__).resolve().with_name('bridge.py')
if hashlib.sha256(bridge_path.read_bytes()).hexdigest()!='f9a71b3e4f3ccb1ed3204100059b9c9096556f0a0b2f0dc5ddf9457d5a737280':
    raise ValueError('frozen source/model bridge changed before import')
import bridge as b

CAP=768*1024**2
PREP_CAP=1024**2
DURABLE_SUBCAP=16*1024**2


def choose(occupied):
    for allocation in (256*1024**2,128*1024**2):
        if occupied+allocation<=CAP:return allocation
    raise ValueError('unchanged768MiB pool cannot reserve even prospective128MiB cohort')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--preflight',action='store_true');parser.add_argument('--script-sha',required=True);args=parser.parse_args()
    b.require(args.preflight and b.bind(__file__)['sha256']==args.script_sha,'explicit ROOT reviewed preflight only')
    result=b.read()
    sys.path.insert(0,str(b.PREP));budget=b.module(b.PREP/'budget.py','qualified_borrow256_budget_preflight')
    resources=budget.check();home=budget.source.budget()
    future=choose(resources['own_bytes'])
    durable=budget.source.size(b.DURABLE)
    b.require(durable+DURABLE_SUBCAP<=budget.DURABLE_CAP,'prospective16MiB cohort inside original64MiB after full+scoped archives')
    prep=budget.source.size(b.HERE);b.require(prep<=PREP_CAP,'new sibling source/helpers1MiB cap')
    need=home['required_free_bytes']+budget.DURABLE_CAP-durable+PREP_CAP-prep
    b.require(shutil.disk_usage(b.HERE).free>=need,'all existing HOME2.5GiB/source/helper/CAD/durable reservations plus new1MiB')
    b.require(not b.COHORT.exists(),'new cohort has not run')
    path=b.POOL/'allslots-resource-preflight01.json';b.require(not path.exists(),'one new preflight result; preserve all prior outputs')
    record=dict(state='PASS source/resource preflight ONLY; cohort execution pending full driver review',script=b.bind(__file__),bridge_source=b.bind(b.HERE/'bridge.py'),
                qualified_model_bridge=result,resource_snapshot=resources,HOME_snapshot=home,frozen_pool_bytes=resources['own_bytes'],
                prospective_cohort_bytes=future,pool_cap=CAP,prospective_durable_bytes=DURABLE_SUBCAP,existing_durable_bytes=durable,
                prep_cap=PREP_CAP,HOME_required_free_bytes=need,
                raw_per_case=30*1024**2 if future==128*1024**2 else 64*1024**2,
                audit_per_case=8*1024**2 if future==128*1024**2 else 16*1024**2,
                other_total=14*1024**2 if future==128*1024**2 else 16*1024**2,
                scope='No model, compiler, reader, vendor or board launched; source/schema/model/allslot software frozen.')
    with path.open('x') as stream:json.dump(record,stream,indent=2);stream.write('\n')
    print(json.dumps(b.bind(path),sort_keys=True));print(json.dumps({k:record[k] for k in ('frozen_pool_bytes','prospective_cohort_bytes','existing_durable_bytes','HOME_required_free_bytes')},sort_keys=True))


if __name__=='__main__':main()
