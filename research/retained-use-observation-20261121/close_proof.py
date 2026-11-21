#!/usr/bin/env python3
"""Retain compact closed observation evidence; never build/run a model or board."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
EXTERNAL=Path('/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121')


def bind(path):
    path=Path(path).resolve();data=path.read_bytes()
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def main():
    out=HERE/'closed-proof001';out.mkdir(exist_ok=False)
    sources=[ROOT/name for name in ('cosim/v/bp_retained_use_counters.sv','cosim/black-parrot-example/v/top_zynq.sv',
        'cosim/black-parrot-example/Makefile.design','cosim/black-parrot-example/Makefile.hardware',
        'cosim/black-parrot-example/ps.cpp','cosim/black-parrot-example/ps.hpp')]
    sources+=sorted((ROOT/'testing/rtl/retained-use-counters').glob('*.cpp'))+sorted((ROOT/'testing/rtl/retained-use-counters').glob('*.py'))
    sources+=sorted(HERE.glob('*.py'))+[HERE/'README.md']
    snapshots=[]
    for source in sources:
        target=out/'sources'/(str(source.relative_to(ROOT))+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(gzip.compress(source.read_bytes(),mtime=0));snapshots.append(dict(original=bind(source),snapshot=bind(target)))
    files={'unit01':['command.json','build.log'],
           'unit02':['command.json','build.log','run.log','verification.json'],
           'full01':['status.json','source-before.json','clean.log','build.log','build-accepted.json','actual-source-list.json',
                     'verilator/obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat'],
           'firsttouch01':['admission.json','process.json','run.log','verification.json'],
           'strict-firsttouch-audit01':['verification.json','selection.tsv'],
           'counter-audit02':['verification.json','selection.tsv'],
           'default0-lint01':['command.json','verification.json','lint.log','make-dryrun.log']}
    records=[]
    for directory,names in files.items():
        for name in names:
            source=EXTERNAL/directory/name;target=out/(directory+'/'+name+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(gzip.compress(source.read_bytes(),mtime=0));records.append(dict(original=bind(source),snapshot=bind(target)))
    # Tool executable identity survives loss of the private-RAM build path.
    durable=EXTERNAL/'fst-reader';durable.mkdir(exist_ok=False);aliases=[]
    for suffix in ('','.build.json','.build.log'):
        source=Path('/dev/shm/retained-use-observer-20261121/fst_events'+suffix);target=durable/('fst_events'+suffix)
        shutil.copyfile(source,target)
        if not suffix:target.chmod(0o755)
        if bind(source)['sha256']!=bind(target)['sha256']:raise ValueError('durable reader copy changed')
        aliases.append(dict(historical=bind(source),durable=bind(target)))
    proof=json.loads((EXTERNAL/'counter-audit02/verification.json').read_text())
    if not proof['state'].startswith('PASS actual counter transitions'):raise ValueError('counter proof incomplete')
    if json.loads((EXTERNAL/'default0-lint01/verification.json').read_text())['state'].split()[0]!='PASS':raise ValueError('default lint incomplete')
    bp=ROOT/'import/black-parrot'
    if subprocess.check_output(['git','-C',str(bp),'status','--porcelain'],text=True):raise ValueError('BP sources changed')
    report=dict(state='PASS optional observer scoped fulltop correctness/GP0/closed-trace closure; no FPGA/fit/capacity/performance claim',
        base_top=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
        bp_revision=subprocess.check_output(['git','-C',str(bp),'rev-parse','HEAD'],text=True).strip(),
        source_snapshots=snapshots,closed_text_evidence=records,durable_reader_aliases=aliases,
        raw_large_artifacts=[bind(EXTERNAL/path) for path in ('firsttouch01/trace.fst','full01/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench',
            'unit02/obj/VRetainedUse','unit02/unit.fst','counter-audit02/selected-events.tsv.gz','strict-firsttouch-audit01/selected-events.tsv.gz')],
        rejected_preflights=[dict(name='unit01',reason='Packed disjoint clock lanes trigger MULTIDRIVEN; fixed lane-local registers'),
            dict(name='full01 metadata verifier',reason='ctime/mtime column ordering reversed; preserved FAIL, separate strict recheck same compiled model'),
            dict(name='counter-audit01',reason='Three-field compared with six-field binding; refused before FST read; corrected full-field check in audit02')],
        actual_gp0_counts={'i':[1,1,8],'d':[1,1,8]},field_order=['accepted_hits','published_insertions','real_retained_SRAM_beats'],
        limits='Default0; observation1 must be present in actual packaged/elaborated RTL and final route. No physical host build/install or board action. Costs unknown until route.')
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'manifest.json')


if __name__=='__main__':main()
