#!/usr/bin/env python3
"""Retain compact private-1RW fullcore correctness evidence without target execution."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'testing/rtl/uce-maintenance'))
from run_endpoint import bind


def main():
    external=Path('/home/coyang/fpga-artifacts/context-resume/retained-private-sp-ram-20261121/full01')
    session=json.loads((external/'session.json').read_text())
    strict=json.loads((external/'advisory-strict01/verification.json').read_text())
    counter=json.loads((external/'advisory-counter01/verification.json').read_text())
    if not session['state'].startswith('PASS clean1280') or strict['accepted'] is not True or not counter['state'].startswith('PASS actual counter transitions'):
        raise ValueError('combined gate incomplete')
    if bind(session['model']['path'])['sha256']!=session['model']['sha256']:raise ValueError('model drift')
    for key in ('strict','run','fst','reader','auditor','selection','events'):
        record=counter['bindings'][key]
        if bind(record['path'])!=record:raise ValueError('counter/strict artifact drift '+key)
    blocks=re.split(r'(?=^%Warning-)',(external/'build.log').read_text(),flags=re.M)
    relevant=[block for block in blocks if block.startswith('%Warning-UNOPTFLAT') and ('retained_maintenance' in block or 'retained_clear' in block)]
    if relevant:raise ValueError('actual build retains maintenance cycle')
    out=HERE/'closed-full001';out.mkdir(exist_ok=False)
    source_paths=[HERE/name for name in ('run_full.py','FULL_RESULTS.md','close_full.py')]
    source_paths += [ROOT/name for name in ('testing/rtl/retained-advisory-trace/validate.py',
        'research/retained-use-observation-20261121/verify_counters.py','testing/check_run.py',
        'import/black-parrot/bp_me/src/v/cce/bp_uce.sv','import/black-parrot/bp_common/src/v/bp_retained_line_store.sv')]
    evidence=[external/name for name in ('session.json','make-preflight.log','clean.log','build.log','loader.log','actual-source-list.json',
       'integrity-run.log','integrity-checker.log','advisory-run.log','advisory-checker.log',
       'verilator/obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat')]
    for kind in ('integrity','advisory'):
        evidence += [external/kind/name for name in ('admission.json','process.json','run.log','verification.json')]
    for kind in ('advisory-strict01','advisory-counter01'):
        evidence += [external/kind/name for name in ('selection.tsv','verification.json','reader.stderr')]
    fixture=Path(strict['bindings']['fixture_manifest']['path'])
    fixture_data=json.loads(fixture.read_text());source_paths += [fixture,Path(fixture_data['source']['path'])]
    geometry=json.loads((external/'geometry.json').read_text())
    evidence += [external/'geometry.json']+[Path(p) for p in geometry['snapshot_paths']]
    source_paths += [Path(geometry['source_auditor']['path'])]+[Path(p['path']) for p in geometry['facts']['geometry_sources']]
    copies=[]
    for source in source_paths+evidence:
        if source in evidence:relative=str(source.relative_to(external))
        elif str(source).startswith(str(ROOT)+'/'):relative='sources/'+str(source.relative_to(ROOT))
        else:relative='frozen-cold08/'+source.name
        target=out/(relative+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(gzip.compress(source.read_bytes(),mtime=0));copies.append(dict(original=bind(source),snapshot=bind(target)))
    large=[bind(Path(session['model']['path']))]
    for kind in ('integrity','advisory'):
        large += [bind(external/kind/name) for name in ('prog.riscv','prog.nbf','trace.fst')]
    large += [bind(external/kind/'selected-events.tsv.gz') for kind in ('advisory-strict01','advisory-counter01')]
    result=dict(state='PASS private-1RW retained RAM clean fullcore integrity/cold08 strict payload+counter correctness; no FPGA/fit/performance claim',
                executed_top=session['source_repositories'][0],executed_bp=session['source_repositories'][1],
                model=session['model'],geometry=session['geometry'],actual_l2=geometry['facts']['l2'],compact_evidence=copies,external_large_artifacts=large,
                actual_build_maintenance_unoptflat=[],firsttouch_counts=counter['firsttouch_counts'],
                scope=session['scope'],
                retained_limitations='Firsttouch only on new source, not rerun all-slot capacity. Original e109 all-slot proofs immutable. Component matrix established cycle equivalence, not new-source all-slot wholecore coverage. Logical single owning-clock 1RW arrays do not guarantee only one physical primitive port. Actual full-system synthesis/fit pending.',
                counter_helper_prose_qualification='Raw helper retains original64/64 calibration wording; actual executed1280/1280 geometry and firsttouch-only scope authoritative here.')
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'manifest.json')


if __name__=='__main__':main()
