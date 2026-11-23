#!/usr/bin/env python3
"""ROOT-only new768 source/model binding AFTER actual clean fullPASS; no tools."""
import argparse,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'helper'))
from native_input import bind,verify,require,read_fullcore,FULL
STD=HERE.parent/'csr768-regression-preparation02-20261123'
OWNED=Path('/home/coyang/fpga-artifacts/context-resume/csr1536-composite-continuation-preparation-20261122/preparation01/software_owned_v2.py')
LINEAGE=Path('/home/coyang/fpga-artifacts/context-resume/retained-canonical-scoped-20261121')


def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--fullcore-sha',required=True);ap.add_argument('--resource-profile',type=Path,required=True);ap.add_argument('--resource-sha',required=True);ap.add_argument('--bind-only',required=True,action='store_true');a=ap.parse_args()
    model_input=HERE/'model-input.ROOT.json'
    require(not model_input.exists() and not (HERE/'preparation-source.json').exists() and not (STD/'source-plan.json').exists(),'fresh768 binding only; no overwrite/retry')
    accepted=read_fullcore(a.fullcore_sha);resource=bind(a.resource_profile);require(resource['sha256']==a.resource_sha,'fresh ROOT selected resource profile')
    q=json.loads(a.resource_profile.read_text());require(q['ROOT_approved']is True and q['schema']=='csr768-native-resource-profile-v1' and q['all_other_charged_reserves_included']is True,'fresh ROOT priced768 resources, not old1536 profile')
    own=bind(OWNED);require(own['sha256']=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5','same qualified ownership implementation')
    # Set the future model identity through a new immutable metadata input,
    # before the first common import. No imported module/global is patched.
    save(model_input,dict(schema='csr768-observation-model-input-v1',state='ROOT-BOUND actual768 fullPASS; no clone execution authority',fullcore=bind(FULL/'session.json'),model={k:accepted['model'][k]for k in ('path','bytes','sha256')},TOP=accepted['source_tree_baseline'],BP=accepted['source_bp']))
    from common import producer,MODEL_SHA,GEOMETRY_TOOL,SP
    accepted=producer()
    paths=[*sorted((HERE/'helper').glob('*.py')),HERE/'bind_sources.py',HERE/'README.md',HERE/'domains.json.gz',model_input,STD/'launch.py',STD/'regressions.py',STD/'README.md',STD/'software-recipe.json',STD/'software-sources.json',OWNED,LINEAGE/'proposal.json',LINEAGE/'admission.json',GEOMETRY_TOOL,SP/'testing/check_run.py',SP/'testing/rtl/retained-advisory-trace/validate.py']
    rows=[bind(p)for p in paths]
    recipe=json.loads((STD/'software-recipe.json').read_text())
    for row in recipe['inputs']:verify(row)
    installed=next(r for r in recipe['inputs']if r['path'].endswith('/riscv64-unknown-elf/include/bp_utils.h'));local=SP/'software/include/bp_utils.h'
    if local.is_file():
        row=bind(local);require((row['bytes'],row['sha256'])==(installed['bytes'],installed['sha256']),'actual first include override same accepted header');rows.append(row)
    rows += [resource,bind(FULL/'session.json'),accepted['actual_source_list'],accepted['selection'],accepted['software_proof'],*accepted['closed_audits'].values(),*accepted['inputs']]
    rows=[{k:r[k]for k in ('path','bytes','sha256')}for r in rows]
    source=dict(schema='csr768-observation-source-v1',state='SOURCE BOUND after actual new768 eleven-phase PASS; separate ROOT prepare/clone approval required',model_sha=MODEL_SHA,model_bytes=accepted['model']['bytes'],source_TOP=accepted['source_tree_baseline'],source_BP=accepted['source_bp'],fullcore_proof=bind(FULL/'session.json'),model_input=bind(model_input),ROOT_resource_profile=resource,owned=own,inputs=rows,new_source_cap_bytes=160*1024,new_source_inside_existing_logging_envelope=True,whole_pool_bytes=1024**3,whole_durable_bytes=32*1024**2,scope='768 cold08 observation equivalence+unchanged4STD only; no all768/physical/fit/performance')
    save(HERE/'preparation-source.json',source)
    save(STD/'source-plan.json',dict(schema='csr768-four-unchanged-architectural-tests-source-v1',state='SOURCE BOUND; actual new768 scopedPASS required',inputs=rows+[bind(HERE/'preparation-source.json')]+[{k:r[k]for k in ('path','bytes','sha256')}for r in recipe['inputs']],clone_source=bind(HERE/'preparation-source.json'),ROOT_resource_profile=resource))
    print(json.dumps(dict(observation=bind(HERE/'preparation-source.json'),STD=bind(STD/'source-plan.json'),model=bind(model_input))))

if __name__=='__main__':main()
