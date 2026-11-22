#!/usr/bin/env python3
"""ROOT-only fresh all256 preparation; metadata/resource checks, no tools."""
import argparse,json
from pathlib import Path
import contract as c
import fixed_shared as fixed
import ledger


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepare',action='store_true');ap.add_argument('--source-sha',required=True);ap.add_argument('--authority-sha',required=True);args=ap.parse_args()
    source=c.HERE/'source-plan.json';authority=c.HERE/'ROOT-authority.json'
    c.require(args.prepare and c.bind(source)['sha256']==args.source_sha,'explicit ROOT exact source preparation')
    declared=json.loads(source.read_text());c.require(declared['runtime_sources']==c.runtime_sources(),'all frozen current/semantic source bytes')
    for row in declared['runtime_sources']:c.verify(row)
    c.require(c.bind(authority)['sha256']==args.authority_sha,'explicit ROOT authority SHA, DRAFT cannot execute')
    a=json.loads(authority.read_text());c.require(a['ROOT_approved'] is True,'ROOT actual base/qualification/resources approval')
    model_bridge=c.bridge.read(c.bind(authority));row=a['resource_profile']
    c.require(row==c.bind(fixed.POLICY),'one fixed new current resource file')
    profile=fixed.load(row['path'],row['sha256']);c.require(profile['base_closure']==model_bridge['archive'],'same actual base closure before any new case')
    c.require(not c.BASE.exists() and not c.bridge.DELTA.exists(),'fresh cohort; fresh16MiB delta is reserved, not written here')
    whole=sum(ledger.scan(c.bridge.POOL).values());base=sum(ledger.scan(c.bridge.DURABLE).values())
    helpers=sum(sum(ledger.scan(root).values())for root in (c.HERE,*c.bridge.OTHER_HELPERS))
    c.require(whole+c.CAPS['stage_total']<=profile['limits']['pool_cap_bytes'],'all256MiB fits INSIDE existing1GiB; no new RUN allocation')
    snapshot=fixed.snapshot(row);resources=fixed.live_check(snapshot,whole,base,helpers,c.bridge.POOL)
    c.BASE.mkdir();st=c.BASE.stat()
    compiled=c.BASE/'compiled-sources.json';c.archive.write_json(compiled,model_bridge['compiled_sources'])
    program=dict(path='/home/coyang/fpga-artifacts/context-resume/retained-capacity1792-fixtures-20261121/preparation01/build01/manifest.json',bytes=196913,sha256='88546c8afc17c482e42cb731459f44c2a40f2f6aeee2c172321534c872dabd72')
    c.verify(program)
    p=dict(schema='csr-unmasked256-complete-allslots-v1',state='ROOT-PREPARED new CSR256 actual model; native/audit only after explicit execution',stage=str(c.BASE),stage_identity=dict(path=str(c.BASE),device=st.st_dev,inode=st.st_ino),schedule=list(c.ORDER),geometry=c.GEOMETRY,caps=c.CAPS,runtime_sources=c.runtime_sources(),source_plan=c.bind(source),ROOT_authority=c.bind(authority),fixed_reservations=row,model_bridge=model_bridge,model=model_bridge['model'],program=program,compiled_sources=c.bind(compiled),reader=model_bridge['reader'],environment=model_bridge['environment'],linked_libraries=model_bridge['linked_libraries'],resource_snapshot=dict(whole_pool_bytes=whole,closed_base_HOME_bytes=base,helper_bytes=helpers,required=resources),prospective_durable_delta_bytes=16*1024**2,old_base_cap_unchanged=32*1024**2,archive_policy='No archive helper or concurrent durable writes; ROOT serializes delta archive after all six complete phases',scope='new exact256 full64B capacity correctness only; no fit/FPGA/application/performance claim')
    path=c.BASE/'preparation.json';c.archive.write_json(path,p);c.load(path,c.bind(path)['sha256']);c.check_budget(c.BASE,p)
    print(json.dumps(c.bind(path),sort_keys=True))


if __name__=='__main__':main()
