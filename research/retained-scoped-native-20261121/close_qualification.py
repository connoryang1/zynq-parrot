#!/usr/bin/env python3
"""Archive compact CLOSED qualification proof; never runs a model or edits inputs."""
import json
from pathlib import Path
import shutil
from common import HERE,PROPOSAL,bind,verify,save,require
from qualify import validate


def main():
    out=HERE/'closed-qualification01'
    require(not out.exists(),'preserve existing closure')
    admission=HERE/'admission.json';a=json.loads(admission.read_text());a['_path']=str(admission)
    validate(a,bind(admission)['sha256'])
    journal=HERE/'qualification01/qualification.json';q=json.loads(journal.read_text())
    require(q['state']=='PASS-BOTH-original-arm-complete-output-and-all252-leaf-byte-equivalence',
            'complete two-arm qualification required')
    require([r['mode'] for r in q['modes']]==[0,15],'wrong mode order/count')
    out.mkdir();copies={};rows=[];external=[]
    def copy(path,target):
        before=bind(path);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        after=bind(target)
        require((before['bytes'],before['sha256'])==(after['bytes'],after['sha256']),'compact copy changed bytes')
        copies[str(target.relative_to(out))]=dict(original=before,copy=after)
    copy(journal,out/'qualification.json')
    for row in q['modes']:
        require(row['state']=='PASS-complete-output-and-all252-leaf-byte-equivalence','failed/partial arm')
        mode=row['mode'];folder=HERE/'qualification01'/('mode%d'%mode)
        for key in ('log','guest','trace'):verify(row[key])
        for key in ('original_canonical','filtered_canonical'):
            verify(row[key]['canonical_file']);external.append(row[key]['canonical_file'])
        old,new=row['original_canonical'],row['filtered_canonical']
        for key in ('sha256','events','changes_by_index','first_tick','final_tick','timescale','clean_EOF'):
            require(old[key]==new[key],'closed event equality metadata changed')
        for name in ('run.log','guest-observations.json','loader-preflight.log'):
            copy(folder/'runtime'/name,out/('mode%d'%mode)/name)
        copy(folder/'filtered-canonical/hierarchy.tsv',out/('mode%d'%mode)/'hierarchy.tsv')
        for kind in ('original','filtered'):
            save(out/('mode%d'%mode)/(kind+'-canonical.json'),row[kind+'_canonical'])
            copy(folder/(kind+'-canonical')/'reader.stderr',out/('mode%d'%mode)/(kind+'-reader.stderr'))
        guest=json.loads(Path(row['guest']['path']).read_text())
        reference=a['references'][str(mode)]
        rows.append(dict(mode=mode,whole_cycles=guest['phases']['whole_cycles'],ring_cycles=guest['phases']['ring_cycles'],
            original_FST=reference['trace'],filtered_FST=row['trace'],original_FST_bytes=reference['trace']['bytes'],
            filtered_FST_bytes=row['trace']['bytes'],canonical_events=old['events'],canonical_sha256=old['sha256'],
            literal_uncompressed_bytes_equal=True,exact252_leaf_hierarchy=True,complete_protocol_equal=True,
            finalized_original_clock_endpoints_equal=True,source_inventory_rechecks_passed=True,
            native_elapsed_seconds=row['elapsed_seconds'],native_returncode=row['returncode']))
        external += [reference['trace'],row['trace']]
    geometry=HERE.parent/'retained-native-l2-geometry-20261121/final-proof.json'
    result=dict(state='CLOSED-PASS-BOTH-OBSERVATION-ONLY-ARMS',journal=bind(journal),admission=bind(admission),
        builder_proof=a['build'],proposal=bind(PROPOSAL),model=a['copied_model'],original_model=a['original_model'],
        source=bind(__file__),copies=copies,results=rows,external_raw_immutable=external,
        total_original_FST_bytes=sum(r['original_FST_bytes'] for r in rows),
        total_filtered_FST_bytes=sum(r['filtered_FST_bytes'] for r in rows),
        geometry_erratum=bind(geometry),model_L2_bytes=4096,model_L2_banks=1,ordinary_L1_I_bytes=32768,ordinary_L1_D_bytes=32768,
        budgets=q['budget'],attempts_per_arm=1,retries=0,budget_extensions=0,
        scope='Complete observation equivalence of pinned ef0c→f1 clone only; no new performance sample, no FPGA/DRAM projection, no effect bridge to static16KiB model. No new9/6/N40/200/application/row target admission.',
        assertion_scope='Same original TRACE1/post-initialization BP/runtime assertions and documented support as original model; global library/timezero parameter checks remain excluded.',
        terminal='Both native processes match original knownGPIO finalization exit−6 AFTER complete guest/CORE/hostPASS; qualifier process exits0. Not relabeled native clean exit0.')
    save(out/'manifest.json',result)
    paths=[str(p.relative_to(HERE.parents[1])) for p in out.rglob('*') if p.is_file()]
    paths += [str(Path(__file__).resolve().relative_to(HERE.parents[1])),str((HERE/'QUALIFICATION_CLOSED.md').relative_to(HERE.parents[1])),str((out/'checkpoint-whitelist.json').relative_to(HERE.parents[1]))]
    save(out/'checkpoint-whitelist.json',sorted(paths))
    print(bind(out/'manifest.json'));print(bind(out/'checkpoint-whitelist.json'))


if __name__=='__main__':main()
