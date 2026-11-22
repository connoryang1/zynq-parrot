#!/usr/bin/env python3
"""Prepare new all256 admission only; never a model, reader, compiler or board."""
import argparse
import json
from pathlib import Path
import shutil
import contract as c

SOURCE_PLAN=c.HERE/'source-plan.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true');parser.add_argument('--source-sha',required=True);args=parser.parse_args()
    c.require(args.prepare and c.bind(SOURCE_PLAN)['sha256']==args.source_sha,'ROOT externally reviewed new source plan')
    declared=json.loads(SOURCE_PLAN.read_text())
    c.require(declared['sources']==c.runtime_sources(),'all new/foundation/transitive source bytes frozen before preparation')
    for row in declared['sources']:c.verify(row)
    c.require(c.bind(c.PREFLIGHT)['sha256']=='ca5878f852d05ac4941c9571f0401071f619d0abc4a2dd3d2af6bcb4c82bfe81','actual ROOT fullpool preflight result')
    preflight=json.loads(c.PREFLIGHT.read_text())
    c.CAPS=c.caps(preflight['prospective_cohort_bytes'])
    c.require(c.CAPS['stage_total']==256*1024**2,'ROOT measured actual256MiB subdivision;128 fallback never launched')
    model_bridge=c.bridge.read()
    c.require(not c.BASE.exists(),'fresh exact new matched borrowing cohort only')
    from ledger import budget
    s=budget();before=s.check()
    c.require(before['own_bytes']+c.CAPS['stage_total']<=s.OWN_CAP,'actual total originals/fullclone/inventory plus entire256MiB within768MiB')
    durable=s.source.size(c.bridge.DURABLE)
    c.require(durable+16*1024**2<=s.DURABLE_CAP,'prospective complete cohort16MiB inside existing64MiB after scoped archive')
    c.BASE.mkdir();st=c.BASE.stat()
    compiled=c.BASE/'compiled-sources.json';c.archive.write_json(compiled,model_bridge['compiled_sources'])
    program=json.loads((c.old.HERE/'preparation.DRAFT.json').read_text())['program']
    record=dict(schema='borrow256-complete-allslots-v1',state='ROOT-PREPARED actual qualified borrowing256; native/audit only after explicit ROOT execution',
                stage=str(c.BASE),stage_identity=dict(path=str(c.BASE),device=st.st_dev,inode=st.st_ino),schedule=list(c.ORDER),
                geometry=c.GEOMETRY,caps=c.CAPS,runtime_sources=c.runtime_sources(),source_plan=c.bind(SOURCE_PLAN),
                resource_preflight=c.bind(c.PREFLIGHT),model_bridge=model_bridge,model=model_bridge['model'],
                program=program,compiled_sources=c.bind(compiled),reader=model_bridge['reader'],environment=model_bridge['environment'],linked_libraries=model_bridge['linked_libraries'],
                prospective_durable_subcap=16*1024**2,existing_durable_cap=64*1024**2,existing_pool_cap=768*1024**2,
                resource_snapshot=before,limitations='All256 full64B payload simulation correctness only. Complete D-enabled audit before D-off, complete D-off audit before I-enabled. No fit/physical/application/performance or old-model qualification transfer.')
    path=c.BASE/'preparation.json';c.archive.write_json(path,record)
    c.load(path,c.bind(path)['sha256']);c.check_budget(c.BASE,record)
    print(json.dumps(c.bind(path),sort_keys=True))


if __name__=='__main__':main()
