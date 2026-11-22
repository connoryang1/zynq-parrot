#!/usr/bin/env python3
"""ROOT fixed-reserve feasibility only; no policy approval, model, reader or stage."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
for name,sha in {'bridge.py':'ae9b71e7ecee71733c5eb10f0701020aaf36eb5cc6386d864d87d0776fa70e24',
                 'fixed_reservations.py':'e26c9b38fc3b9516ce658e68afb34e9a25159e68abbb83612c3f43ea1b04b057'}.items():
    if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()!=sha:raise ValueError('frozen helper changed before import '+name)
import bridge as b
import fixed_reservations as f


def candidate():
    rows={name:b.bind(f.CLOSURES/('r8-freeze-complete.json'if name=='complete'else'r8-'+name+'.json'))for name in ('work','evidence','complete')}
    expected=dict(complete='09075ffd134c175155d9299b498ed9c1bbe0c2d635e463fc941f2fb50880b5c7',work='27dbc7e99783672633e23cb50091430cf6dfb91213427c769c2215f18f855a37',evidence='e5af52fb91c1f93bbf01f23a40eae24cb0bc9d63b6b71fd2ac36d9648e99336c')
    b.require(all(rows[k]['sha256']==v for k,v in expected.items()),'actual ROOT37115 pair, not PENDING')
    return dict(schema='borrow256-fixed-prospective-reservations-v1',state='DRAFT fixed full prospective lower256 CAD reserves; no policy approval',
                old_R8_freeze=rows,preflight=b.bind(f.EXPORT),new_CAD=dict(work_root=str(f.NEW_WORK),work_cap_bytes=f.WORK_CAP,
                evidence_roots=list(map(str,f.NEW_EVIDENCE)),evidence_cap_bytes=f.EVIDENCE_CAP),
                note='Reserved full prospective CAD ceilings; no vendor launch, approval, physical image or native target from this feasibility step.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--preflight',action='store_true');parser.add_argument('--script-sha',required=True);args=parser.parse_args()
    b.require(args.preflight and b.bind(__file__)['sha256']==args.script_sha,'ROOT exact reviewed preflight source')
    result=b.read();p=candidate();f.closed_pair(p,full=True)
    totals={name:sum(sum(f.scan(root).values())for root in roots)for name,roots in f.OTHER_POOLS.items()}
    b.require(all(n<=f.OWN_CAP for n in totals.values()),'all old pool bounds')
    own=sum(f.scan(b.POOL).values());durable=sum(f.scan(b.DURABLE).values())
    helpers=sum(sum(f.scan(root).values())for root in (*b.PREVIOUS_HELPERS,b.HERE))
    b.require(own+256*1024**2<=f.OWN_CAP,'fresh256MiB correctness cohort plus oldfailed/full/clone/inventory within768MiB')
    b.require(durable+16*1024**2<=f.DURABLE_CAP and helpers<=f.HELPER_CAP,'same64MiB durable/16MiB prospective archive/1MiB source family')
    snapshot=dict(other_pool_totals=totals,nonCAD_HOME_base=f.home_base())
    required=f.live_check(snapshot,own,durable,helpers,b.POOL)
    out=b.POOL/'allslots-fixed-reserve-preflight01.json';b.require(not out.exists(),'fresh fixed resource result only')
    record=dict(state='PASS feasibility ONLY; ROOT policy/source/cohort admission still pending',script=b.bind(__file__),fixed_source=b.bind(Path(f.__file__)),bridge_source=b.bind(Path(b.__file__)),
                candidate_policy=p,qualified_model_bridge=result,own_pool_bytes=own,other_pool_totals=totals,durable_bytes=durable,helper_family_bytes=helpers,
                required=required,free=dict(RAM=shutil.disk_usage(b.POOL).free,HOME=shutil.disk_usage(b.HERE).free),
                next='No native/model/reader/tool was run; new monitor remains separately admitted.')
    with out.open('x')as stream:json.dump(record,stream,indent=2);stream.write('\n')
    print(json.dumps(b.bind(out),sort_keys=True));print(json.dumps(record['required'],sort_keys=True))


if __name__=='__main__':main()
