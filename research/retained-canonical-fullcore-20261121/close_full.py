#!/usr/bin/env python3
"""Retain compact private-1RW fullcore correctness evidence without target execution."""
import gzip
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import shutil
import tarfile

ROOT=Path('/dev/shm/zp-linux-canonical-fulltop-20261121-01')
OLD_ROOT=Path('/home/coyang/zynq-parrot-retained-dense')
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'testing/rtl/uce-maintenance'))
from run_endpoint import bind


def durable_guard():
    used=sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())
    if used>128*1024**2 or shutil.disk_usage(HERE).free<3*1024**3+max(0,128*1024**2-used):
        raise ValueError('128MiB totaldurable cap /3GiB HOME reserve')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();external=args.external.resolve()
    if external.parent!=Path('/dev/shm/zp-linux-canonical-fullcore-20261121-01'):raise ValueError('metadata artifacts only')
    session=json.loads((external/'session.json').read_text())
    strict=json.loads((external/'advisory-strict01/verification.json').read_text())
    counter=json.loads((external/'advisory-counter01/verification.json').read_text())
    if session['state']!='PASS canonical1792 fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-geometry-source-audits' or strict['accepted'] is not True or not counter['state'].startswith('PASS actual counter transitions'):
        raise ValueError('combined gate incomplete')
    if bind(session['model']['path'])['sha256']!=session['model']['sha256']:raise ValueError('model drift')
    for key in ('strict','run','fst','reader','auditor','selection','events'):
        record=counter['bindings'][key]
        if bind(record['path'])!=record:raise ValueError('counter/strict artifact drift '+key)
    blocks=re.split(r'(?=^%Warning-)',(external/'build.log').read_text(),flags=re.M)
    relevant=[block for block in blocks if block.startswith('%Warning-UNOPTFLAT') and ('retained_maintenance' in block or 'retained_clear' in block)]
    if relevant:raise ValueError('actual build retains maintenance cycle')
    parameters=json.loads((external/'actual-parameters01/verification.json').read_text())
    if parameters['facts']['clean_eof'] is not True:raise ValueError('actual parameter/EOF proof missing')
    for key,record in session['closed_audits'].items():
        if bind(record['path'])!=record:raise ValueError('audit drift '+key)
    if session['source_bp']!='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c':raise ValueError('metadata BP pin')
    out=args.out.resolve()
    if out.parent!=HERE:raise ValueError('own compact output only')
    out.mkdir(exist_ok=False)
    source_paths=[HERE/name for name in ('run_full.py','README.md','close_full.py','geometry.py','test_flow.py')]
    source_paths += [ROOT/name for name in ('testing/rtl/retained-advisory-trace/validate.py',
        'testing/check_run.py','testing/check_run.py',
        'import/black-parrot/bp_me/src/v/cce/bp_uce.sv','import/black-parrot/bp_common/src/v/bp_retained_line_store.sv')]
    evidence=[external/name for name in ('session.json','make-preflight.log','clean.log','build.log','loader.log','actual-source-list.json',
       'integrity-run.log','integrity-checker.log','advisory-run.log','advisory-checker.log',
       'verilator/obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat')]
    for kind in ('integrity','advisory'):
        evidence += [external/kind/name for name in ('admission.json','process.json','run.log','verification.json')]
    for kind in ('advisory-strict01','advisory-counter01'):
        evidence += [external/kind/name for name in ('selection.tsv','verification.json','reader.stderr')]
    fixture=Path(strict['bindings']['fixture_manifest']['path'])
    fixture_data=json.loads(fixture.read_text());source_paths += [fixture,Path(fixture_data['source']['path']),OLD_ROOT/'research/retained-use-observation-20261121/verify_counters.py']
    geometry=json.loads((external/'geometry.json').read_text())
    evidence += [external/'geometry.json',external/'actual-parameters01/verification.json',external/'actual-parameters01/selection.tsv',external/'actual-parameters01/events.tsv']+[Path(p) for p in geometry['snapshot_paths']]
    source_paths += [Path(geometry['source_auditor']['path'])]+[Path(p['path']) for p in geometry['facts']['geometry_sources']]
    copies=[]
    for source in dict.fromkeys(source_paths+evidence):
        durable_guard()
        if source in evidence:relative=str(source.relative_to(external))
        elif str(source).startswith(str(ROOT)+'/'):relative='sources/'+str(source.relative_to(ROOT))
        else:relative='frozen-cold08/'+source.name
        target=out/(relative+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(gzip.compress(source.read_bytes(),mtime=0));copies.append(dict(original=bind(source),snapshot=bind(target)))
    # Retain exact model, both full rawFSTs and every consumed source on HOME.
    durable=out/'durable';durable.mkdir()
    model_gz=durable/'model.gz'
    durable_guard()
    with Path(session['model']['path']).open('rb') as src,gzip.open(model_gz,'wb') as dst:
        shutil.copyfileobj(src,dst,1024*1024)
    actual=json.loads((external/'actual-source-list.json').read_text())['sources']
    source_archive=durable/'consumed-sources.tar.gz'
    with tarfile.open(source_archive,'w:gz') as tar:
        for index,(name,record) in enumerate(sorted(actual.items())):
            durable_guard()
            if bind(name)['sha256']!=record['sha256']:raise ValueError('consumed source drift before preservation')
            tar.add(name,arcname='sources/'+str(index)+'/'+Path(name).name,recursive=False)
    if hashlib.sha256(gzip.decompress(model_gz.read_bytes())).hexdigest()!=session['model']['sha256']:
        raise ValueError('lossless model archive mismatch')
    with tarfile.open(source_archive,'r:gz') as tar:
        if len(tar.getmembers())!=len(actual):raise ValueError('source archive member count')
        for index,(name,record) in enumerate(sorted(actual.items())):
            raw=tar.extractfile('sources/'+str(index)+'/'+Path(name).name).read()
            if len(raw)!=record['bytes'] or hashlib.sha256(raw).hexdigest()!=record['sha256']:
                raise ValueError('lossless consumed source archive mismatch')
    durable_copies=[dict(original=bind(session['model']['path']),snapshot=bind(model_gz)),dict(index=bind(external/'actual-source-list.json'),snapshot=bind(source_archive))]
    for kind in ('integrity','advisory'):
        source=external/kind/'trace.fst';target=durable/(kind+'-trace.fst')
        durable_guard()
        shutil.copyfile(source,target)
        if bind(source)['sha256']!=bind(target)['sha256']:raise ValueError('rawFST copy mismatch')
        durable_copies.append(dict(original=bind(source),snapshot=bind(target)))
        for suffix in ('riscv','nbf'):
            source=external/kind/('prog.'+suffix);target=durable/(kind+'-prog.'+suffix+'.gz')
            target.write_bytes(gzip.compress(source.read_bytes(),mtime=0))
            durable_copies.append(dict(original=bind(source),snapshot=bind(target)))
    header=external/'verilator/obj_dir/Vbsg_nonsynth_zynq_testbench___024root.h'
    target=durable/'generated-root.h.gz';target.write_bytes(gzip.compress(header.read_bytes(),mtime=0))
    durable_copies.append(dict(original=bind(header),snapshot=bind(target)))
    durable_guard()
    large=[bind(Path(session['model']['path']))]
    for kind in ('integrity','advisory'):
        large += [bind(external/kind/name) for name in ('prog.riscv','prog.nbf','trace.fst')]
    large += [bind(external/kind/'selected-events.tsv.gz') for kind in ('advisory-strict01','advisory-counter01')]
    result=dict(state='PASS canonical epoch clean fullcore integrity/cold08 strict payload+counter+actual-parameter correctness; no FPGA/fit/performance claim',
                executed_top=session['source_repositories'][0],executed_bp=session['source_repositories'][1],
                durable_copies=durable_copies,model=session['model'],geometry=session['geometry'],actual_l2=geometry['facts']['l2'],compact_evidence=copies,external_large_artifacts=large,
                actual_build_maintenance_unoptflat=[],firsttouch_counts=counter['firsttouch_counts'],
                scope=session['scope'],
                retained_limitations='Firsttouch fullcore correctness only; no all-slot fullcore/application/FPGA claim. Component metadata equivalence is separate from actual production-options inference and full-system routed fit.',
                counter_helper_prose_qualification='Raw helper retains original64/64 calibration wording; actual executed1792/1792 geometry and firsttouch-only scope authoritative here.')
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'manifest.json')


if __name__=='__main__':main()
