#!/usr/bin/env python3
"""Archive closed POWER-only fullcore correctness without running a target."""
import gzip
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'testing/rtl/uce-maintenance'))
from run_endpoint import bind


def require(value,message):
    if not value:raise ValueError(message)


def main():
    external=Path('/home/coyang/fpga-artifacts/context-resume/retained-maintenance-power-20261121/full01')
    session=json.loads((external/'session.json').read_text());strict=json.loads((external/'advisory-strict01/verification.json').read_text())
    counter=json.loads((external/'advisory-counter01/verification.json').read_text())
    require(session['state']=='PASS clean1280+observe1 integrity/advisory execution; closed trace audits pending'
        and strict['accepted'] is True and counter['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'complete runtime/strict/observer gates')
    require(bind(session['model']['path'])['sha256']==session['model']['sha256'],'model drift')
    for key in ('strict','run','fst','reader','auditor','selection','events'):
        record=counter['bindings'][key];require(bind(record['path'])==record,'counter artifact drift '+key)
    blocks=re.split(r'(?=^%Warning-)',(external/'build.log').read_text(),flags=re.M)
    require(not any(b.startswith('%Warning-UNOPTFLAT') and ('retained_maintenance' in b or 'retained_clear' in b) for b in blocks),'maintenance cycle in actual build')
    bp=ROOT/'import/black-parrot';parent='20c74bfb1633c6580945c047828546d723384def';backend='bp_common/src/v/bp_retained_line_store.sv'
    old=subprocess.check_output(['git','-C',str(bp),'show',parent+':'+backend]);new=(bp/backend).read_bytes()
    require(new.count(b'ram_decomp = "power"')==2 and new.replace(b'ram_decomp = "power"',b'ram_decomp = "area"')==old,'only two attribute values')
    require(subprocess.check_output(['git','-C',str(bp),'diff','--name-only',parent,'HEAD'],text=True).splitlines()==[backend],'other BP file changed')
    require(bind(bp/backend)['sha256']=='a4ba1711c90b8f1c0468af0354e3b10682d856f74320d49a374d6e52b78f2c46','exact POWER backend')
    spec=importlib.util.spec_from_file_location('geometry',ROOT/'research/retained-maintenance-acyclic-20261121/bind_geometry.py')
    geometry=importlib.util.module_from_spec(spec);spec.loader.exec_module(geometry)
    facts,headers=geometry.inspect(external,session['model']['sha256'])
    out=HERE/'closed-full001';out.mkdir(exist_ok=False)
    paths=[HERE/name for name in ('run_power.py','RESULTS.md','close_power.py','source-preparation.json')]
    paths += [ROOT/name for name in ('testing/rtl/retained-advisory-trace/validate.py','research/retained-use-observation-20261121/verify_counters.py',
        'testing/check_run.py','research/retained-maintenance-acyclic-20261121/bind_geometry.py','import/black-parrot/bp_me/src/v/cce/bp_uce.sv',
        'import/black-parrot/bp_common/src/v/bp_retained_line_store.sv')]
    evidence=[external/name for name in ('session.json','make-preflight.log','clean.log','build.log','loader.log','actual-source-list.json',
        'integrity-run.log','integrity-checker.log','advisory-run.log','advisory-checker.log','verilator/obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat')]
    for kind in ('integrity','advisory'):
        evidence += [external/kind/name for name in ('admission.json','process.json','run.log','verification.json')]
    for kind in ('advisory-strict01','advisory-counter01'):
        evidence += [external/kind/name for name in ('selection.tsv','verification.json','reader.stderr')]
    evidence+=headers
    paths += [Path(row['path']) for row in facts['geometry_sources']]
    copies=[]
    for source in paths+evidence:
        relative=str(source.relative_to(external)) if source in evidence else 'sources/'+str(source.relative_to(ROOT))
        target=out/(relative+'.gz');target.parent.mkdir(parents=True,exist_ok=True);data=source.read_bytes()
        target.write_bytes(gzip.compress(data,mtime=0));require(gzip.decompress(target.read_bytes())==data,'archive roundtrip')
        copies.append(dict(original=bind(source),snapshot=bind(target)))
    large=[bind(session['model']['path'])]
    for kind in ('integrity','advisory'):large += [bind(external/kind/name) for name in ('prog.riscv','prog.nbf','trace.fst')]
    for kind in ('advisory-strict01','advisory-counter01'):large.append(bind(external/kind/'selected-events.tsv.gz'))
    result=dict(state='PASS POWER-only clean1280 fullcore integrity/cold08 strict512b+SRAM+Iretire+observer/source-ingestion gates; no FPGA/fit/performance claim',
        executed_top=session['source_repositories'][0],executed_bp=session['source_repositories'][1],model=session['model'],geometry=session['geometry'],
        source_delta_parent_bp=parent,source_delta='exactly two ram_decomp attribute values area to power; no other BP source edit',
        actual_backend=bind(bp/backend),actual_build_maintenance_unoptflat=[],static_l2=facts,firsttouch_counts=counter['firsttouch_counts'],
        compact_evidence=copies,external_large_artifacts=large,scope=session['scope'],old_allslot_rerun_on_new_model=False,physical_actions=0,
        retained_limitations='New firsttouch only; original e109 all-slot evidence historical. Global runtime BP assertions after reset active; documented library/timezero guards excluded. No actual full-system synthesis/routing/FPGA capacity or application benefit acceptance.75c physical/recovery draft unchanged/unlaunchable.')
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'manifest.json')


if __name__=='__main__':main()
