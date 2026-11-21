#!/usr/bin/env python3
"""Verify and losslessly archive the already closed private-RAM synthesis case."""
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
ROOT=BASE.parents[1]
CASE=BASE/'store-private-sp-prod01'
BP='d766d42cdf04ee43ca1e915fb9da06f5cc117dde'
SHA='aa36581844c5563f77bcc12f531776a4c858b1470a202d8f8394c7a02a7f8ea7'


def bind(path):
    path=Path(path).resolve();raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def check_binding(record):
    path=Path(record['path'])
    if not path.is_absolute():path=ROOT/path
    actual=bind(path)
    assert (actual['bytes'],actual['sha256'])==(record['bytes'],record['sha256']), str(path)


def main():
    assert not (HERE/'verification.json').exists(), 'new closure required'
    session=json.loads((CASE/'session.json').read_text())
    assert session['state']=='PASS standalone actual-store production-option synthesis only; no routed-fit claim'
    assert session['bp']==BP and session['source_sha256']==SHA and session['physical_operations']==0
    assert session['threads']==8
    assert datetime.fromisoformat(session['closed_utc'])>datetime.fromisoformat(session['started_utc'])
    for record in session['inputs']+list(session['outputs'].values()):check_binding(record)
    assert [c['label'] for c in session['commands']]==['admission','upload','synthesis','collect','no-orphans']
    for command in session['commands']:
        assert command['returncode']==0
        check_binding(command['log'])
    assert session['commands'][-1]['argv'][-1]=='! pgrep -x vivado'
    assert (CASE/'no-orphans.log').read_bytes()==b''
    source=(CASE/'source.sv').read_bytes()
    assert hashlib.sha256(source).hexdigest()==SHA
    original=subprocess.check_output(['git','-C','/home/coyang/zynq-parrot-retained-sp/import/black-parrot',
        'show',BP+':bp_common/src/v/bp_retained_line_store.sv'])
    assert source==original==(CASE/'remote/source.sv').read_bytes()
    assert source.count(b'ram_decomp = "area"')==2
    assert (CASE/'probe.tcl').read_bytes()==(CASE/'remote/probe.tcl').read_bytes()
    tcl=(CASE/'probe.tcl').read_text()
    synth='synth_design -top bp_retained_line_store -part xc7z020clg400-1 -directive AreaOptimized_high -global_retiming on -control_set_opt_threshold 1 -generic i_lines_p=1280 -generic d_lines_p=1280 -generic sets_p=256'
    assert synth in tcl and tcl.startswith('set_param general.maxThreads 8\n')
    log=(CASE/'remote/vivado.log').read_text()
    assert synth in log and 'synth_design completed successfully' in log
    assert "The checkpoint '/tmp/linux-retained-store-private-sp-prod-20261121-01/synthesized.dcp' has been generated." in log
    assert 'ERROR:' not in log and 'SIGSEGV' not in log
    utilization=(CASE/'remote/utilization.rpt').read_text()
    row=re.search(r'^\| bp_retained_line_store\s*\|\s*\(top\)\s*\|([^\n]+)\|$',utilization,re.M)
    assert row
    values=list(map(int,[p.strip() for p in row[1].split('|')]))
    assert values==[6259,6259,0,0,7903,40,2,0]
    counts=Counter();ports=Counter();rows=[]
    for line in (CASE/'remote/primitives.tsv').read_text().splitlines():
        fields=line.split(chr(9));assert len(fields)==7
        name,kind,mode,*widths=fields
        match=re.fullmatch(r'lane_fsm\[([01])\]\.(payload|tag)_mem_reg(?:__\d+)?',name)
        assert match and kind in ('RAMB36E1','RAMB18E1') and mode=='TDP'
        lane,group=match.groups();dims=list(map(int,widths))
        assert dims[0]==dims[1] and dims[0] in (2,9,18)
        assert dims[2:]==([0,0] if lane=='0' else dims[:2])
        counts[f'lane{lane}/{group}/{kind}']+=1
        ports['/'.join([f'lane{lane}',group,kind,mode]+widths)]+=1
        rows.append(dict(instance=name,primitive=kind,ram_mode=mode,
            read_width_a=dims[0],write_width_a=dims[1],read_width_b=dims[2],write_width_b=dims[3]))
    assert len(rows)==42 and len({r['instance'] for r in rows})==42
    expected={f'lane{lane}/{group}/{kind}':n for lane in range(2)
        for group,kind,n in [('payload','RAMB36E1',18),('payload','RAMB18E1',1),('tag','RAMB36E1',2)]}
    assert dict(counts)==expected
    snapshots=[]
    inputs=sorted(p for p in CASE.rglob('*') if p.is_file() and p.suffix!='.dcp')
    inputs.append(BASE/'run_sp_control.py')
    for path in inputs:
        relative=Path('run_sp_control-used.py') if path==BASE/'run_sp_control.py' else path.relative_to(CASE)
        target=HERE/(str(relative)+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        assert not target.exists()
        raw=path.read_bytes();target.write_bytes(gzip.compress(raw,mtime=0))
        assert gzip.decompress(target.read_bytes())==raw
        snapshots.append(dict(original=bind(path),snapshot=bind(target)))
    report=dict(state='PASS independently verified closed actual private-logical-1RW store synthesis; no full-system fit claim',
        bp=BP,source_sha256=SHA,resources=dict(LUT=6259,FF=7903,RAMB36=40,RAMB18=2,tile_equivalents=41),
        payload_tiles=37,tag_tiles=4,counts=dict(counts),primitive_port_histogram=dict(ports),primitive_rows=rows,
        production_options=synth,threads=8,geometry=dict(i_lines=1280,d_lines=1280,sets=256,line_bytes=64),
        closed_commands=[dict(label=c['label'],returncode=c['returncode']) for c in session['commands']],
        no_orphans_scope='Recorded successful no-Vivado-process check at case closure; no new remote query or synthesis performed by this verifier.',
        closed_utc=session['closed_utc'],snapshots=snapshots,
        external_generated_artifacts=[bind(CASE/'remote/synthesized.dcp')],verifier=bind(__file__),
        limitations=['Standalone all-variable input module, no production XDC; resource counts are not additive to a CPU baseline because production constants can prune logic.',
          'One owning-clock logical 1RW source interface per lane does not imply a single physical primitive port. All42 recorded primitives have RAM_MODE=TDP; I B widths are0, D B widths equal A. TSV does not record physical clock-net connectivity.',
          'Synthesis completion and packing only, not routed timing, FPGA deployment, application benefit or physical all-slot correctness. No tool, source or old evidence bytes changed.'],
        physical_operations=0)
    (HERE/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    whitelist=sorted(str(p.relative_to(ROOT)) for p in HERE.rglob('*') if p.is_file())
    checkpoint=BASE/'checkpoint-files-sp.json';assert not checkpoint.exists()
    whitelist.append(str(checkpoint.relative_to(ROOT)))
    checkpoint.write_text(json.dumps(sorted(whitelist),indent=2)+'\n')
    print(json.dumps(dict(verification=bind(HERE/'verification.json'),whitelist=bind(checkpoint),files=len(whitelist)),indent=2))


if __name__=='__main__':main()
