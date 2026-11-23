#!/usr/bin/env python3
"""Prepare only the fresh96MiB joint native stage after exact ROOT funding/source review."""
import argparse,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
import contract as c
import fixed_shared as fixed
import ledger


def main():
    a=argparse.ArgumentParser(description=__doc__)
    for flag in ('authority','context','profile'):a.add_argument('--'+flag,required=True,type=Path);a.add_argument('--'+flag+'-sha256',required=True)
    a.add_argument('--execute',action='store_true');args=a.parse_args()
    c.require(args.execute,'UNADMITTED source packet; explicit ROOT execution required')
    rows={key:c.bind(getattr(args,key))for key in ('authority','context','profile')}
    for key,row in rows.items():c.require(row['sha256']==getattr(args,key+'_sha256'),'exact ROOT '+key)
    ctx=c.context(args.context,args.context_sha256);authority=c.bridge.read(rows['authority'],args.context)
    policy=fixed.load(args.profile,args.profile_sha256)
    c.verify_prior(authority)
    c.require(policy['base_closure']==authority['base_closure'],'same exact base closure')
    c.require(not c.BASE.exists() and c.BASE.parent.is_dir(),'fresh output outside sealed original pool')
    c.require(c.BASE!=c.bridge.ORIGINAL_POOL and c.bridge.ORIGINAL_POOL not in c.BASE.parents,'sealed pool cannot be written')
    durable=sum(ledger.scan(c.bridge.DURABLE).values());helpers=sum(ledger.scan(c.HERE).values())
    # The full prospective stage is reserved BEFORE mkdir. No old budget import.
    fixed.live_check(dict(policy=policy),0,durable,helpers,c.BASE.parent)
    sources=c.runtime_sources();proposal=json.loads(Path(ctx.ctx.anchors['closed_anchors']['proposal']['path']).read_text())
    c.BASE.mkdir(exist_ok=False)
    try:
        compiled=c.BASE/'compiled-sources.json';c.archive.write_json(compiled,proposal['compiled_sources'])
        st=c.BASE.stat()
        p=dict(schema='csr1280-complete-joint-v1',state='ROOT-PREPARED new1280 JOINT actual model; native/audit only after explicit execution',stage=str(c.BASE),stage_identity=dict(path=str(c.BASE),device=st.st_dev,inode=st.st_ino),caps=c.CAPS,host_accounting=c.bridge.HOST_ACCOUNTING,schedule=list(c.ORDER),source_plan=c.bind(c.HERE/'source-plan.json'),runtime_sources=sources,semantic_context=rows['context'],ROOT_authority=rows['authority'],fixed_reservations=rows['profile'],model=ctx.ctx.anchors['model'],geometry=ctx.ctx.anchors['actual_geometry17'],program=ctx.ctx.anchors['programs']['joint']['manifest'],compiled_sources=c.bind(compiled),environment=proposal['environment'],linked_libraries=proposal['linked_libraries'],reader=proposal['reader'])
        dest=c.BASE/'preparation.json';c.archive.write_json(dest,p)
        c.load(dest,c.bind(dest)['sha256']);c.check_budget(c.BASE,p)
        c.archive.write_json(c.BASE/'prepared.json',dict(state='PASS separately funded JOINT preparation; both1280-lane execution/audit pending',preparation=c.bind(dest)))
        print(json.dumps(c.bind(dest)))
    except BaseException as error:
        c.archive.write_json(c.BASE/'PREPARATION-FAIL.json',dict(state='FAIL preparation; no target',error=repr(error)));raise

if __name__=='__main__':main()
