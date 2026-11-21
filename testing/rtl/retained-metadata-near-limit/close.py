#!/usr/bin/env python3
"""Close only the three source-bound capacity component cases; no execution."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from cohort import HERE, ROOT, validate_sources, bind, check_resources, CAPACITIES


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--external',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();external=a.external.resolve();out=a.out.resolve()
    assert external.parent==Path('/home/coyang/fpga-artifacts/context-resume/retained-metadata-near-limit-20261121')
    assert out.parent==HERE and not out.exists()
    s=json.loads((external/'session.json').read_text());ad=json.loads((external/'admission.json').read_text())
    assert s['state']=='PASS-three-near-limit-capacities-six-clock-runs-component-only'
    assert s['admission']==bind(external/'admission.json') and ad['capacities']==list(CAPACITIES)
    assert validate_sources()==ad['sources']
    assert [r['capacity'] for r in s['closed']]==list(CAPACITIES)
    groups={r['owned_pgid'] for r in s['closed']};active=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:fields=(proc/'stat').read_text().rpartition(')')[2].split()
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
        if int(fields[2]) in groups:active.append(int(proc.name))
    assert not active,'owned test-process group remains'
    out.mkdir();copies=[];runs=[]
    for name in ('admission.json','session.json'):
        shutil.copyfile(external/name,out/name);copies.append(dict(original=bind(external/name),snapshot=bind(out/name)))
    for cap,case in zip(CAPACITIES,s['closed']):
        assert case['returncode']==0
        assert case['manifest']==bind(Path(case['manifest']['path']))
        d=external/('s256-i%d-d%d-e8'%(cap,cap));m=json.loads((d/'manifest.json').read_text())
        assert m['state']=='PASS-metadata-cycle-payload-coherence-miter'
        assert m['parameters']['sets']==256 and m['parameters']['epoch_width']==8
        assert m['parameters']['i_lines']==m['parameters']['d_lines']==cap
        assert [r['mode'] for r in m['runs']]==['inverted','different-periods']
        compiled=Path(m['compiled_reference']['path']);assert bind(compiled)==m['compiled_reference']
        assert compiled.read_text()==(HERE/'reference-d766.sv').read_text().replace('module bp_retained_line_store\n','module bp_retained_line_store_reference\n')
        dst=out/d.name;dst.mkdir()
        for name in ('manifest.json','build.log','version.log','run-inverted.log','run-different-periods.log'):
            shutil.copyfile(d/name,dst/name);copies.append(dict(original=bind(d/name),snapshot=bind(dst/name)))
        for run in m['runs']:
            trace=Path(run['fst']['path']);assert bind(trace)==run['fst']
            text=(d/('run-'+run['mode']+'.log')).read_text()
            assert text.count('RETAINED_METADATA_MITER_PASS I=%d D=%d SETS=256 clock=%s'%(cap,cap,run['mode']))==1
            assert text.count('RETAINED_METADATA_RANDOM_PASS deterministic_ticks=80000 seed=0x71b49a23')==1
            assert text.count('RETAINED_METADATA_HAZARDS_PASS geometry_conditional=1')==1
            assert text.count('RETAINED_TEST_EXIT_CLEAN')==1
            assert re.findall(r'RETAINED_CAPACITY_CHECK lane=(\d) lines=(\d+) full64B=1',text)==[('0',str(cap)),('1',str(cap))]
            counts=re.findall(r'RETAINED_COUNTS lane=(\d) queries=(\d+) responses=(\d+) inserts=(\d+) terminals=(\d+) published=(\d+)',text)
            assert len(counts)==2 and all(r[1]==r[2] and r[3]==r[4] for r in counts)
            runs.append(dict(capacity_per_side=cap,bytes_per_side=cap*64,retained_sets=256,epoch_width=8,clock=run['mode'],counts_since_last_reset=counts,closed_fst=run['fst']))
    report=dict(state='PASS-six-near-limit-full-payload-cycle-coherence-component-runs',admission=bind(external/'admission.json'),session=bind(external/'session.json'),sources=validate_sources(),copies=copies,runs=runs,randomized_ticks=6*80000,no_owned_process_groups=active,resources=check_resources(external),scope='Actual full64B slots and tested cycle/payload/coherence equivalence only; no unique-useful capacity, inference/BRAM mapping, area/timing/routed fit, fullcore/application/FPGA or performance claim.')
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['state'])

if __name__=='__main__':main()
