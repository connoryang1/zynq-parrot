#!/usr/bin/env python3
"""Exact arithmetic for both fixed synthetic D correctness intervals; no replay."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def binding(p):
    p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def require(ok,message):
    if not ok:raise ValueError(message)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);a=parser.parse_args()
    require(not a.out.exists(),'fresh diagnostics output')
    reviewed=HERE/'review.json';require(binding(reviewed)['sha256']=='7a8741e46cfa592448a72a2ee10fdca271821706f136123c2571b3879c508caf','exact independently reviewed paired endpoints')
    proof=json.loads(reviewed.read_text());period=50000
    clock=Path('/home/coyang/zynq-parrot-linux-capacity/cosim/v/bsg_nonsynth_zynq_testbench.sv')
    source=binding(clock);require(source['sha256']=='87b0308f4a5a63e8e2f0dfbeabc964c8878e81e12491712dd407c5c340ef97f7','exact compiled testbench bytes')
    compiled=Path('/home/coyang/fpga-artifacts/context-resume/retained1792-stream-canonical-20261121/stopped-audit01/compiled-sources.json')
    raw=json.loads(compiled.read_text());rows=raw.get('sources',raw)
    expected=rows['/dev/shm/zp-linux-canonical-fulltop-20261121-01/cosim/v/bsg_nonsynth_zynq_testbench.sv']
    require(all(source[k]==expected[k] for k in ('bytes','sha256')),'compiled source identity through local byte-identical copy')
    text=clock.read_text();require('localparam aclk_period_lp = 50000;' in text and 'assign core_clk = aclk;' in text,'native synchronous clock source')
    result={}
    for interval in ('population_and_check','target_check_only'):
        values={}
        for role,row in proof['paired_d_synthetic_intervals'].items():
            ticks=row[interval+'_ps'];require(ticks%period==0,'integral bound native core cycles')
            values[role]=dict(raw_ps=ticks,core_cycles=ticks//period)
        on,off=(values[role]['core_cycles'] for role in ('d-enabled','d-off'))
        ratio=Fraction(on,off);percent=100*(ratio-1)
        result[interval]=dict(values=values,on_divided_by_off_exact=str(ratio),on_divided_by_off=float(ratio),
            on_minus_off_cycles=on-off,on_minus_off_percent_exact=str(percent),on_minus_off_percent=float(percent))
    report=dict(state='Fixed synthetic all1792 D interval diagnostics only; no statistics/performance claim',review=binding(reviewed),
        clock=dict(raw_tick_unit='ps',ticks_per_core_cycle=period,model_aclk_hz=20000000,basis='ROOT-bound native synchronous model; exact compiled clock source; no FPGA calibration',compiled_source=expected,local_identical_source=source,compiled_inventory=binding(compiled)),
        intervals=result,excluded=['prior retained activation/mode setup','subsequent mode reset','subsequent drains','reporting and completion'],
        limits='Single closed native run per D mode, all1792 targets, both fixed intervals; no uncertainty/statistics or application/complete-WHOLE claim.')
    with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(binding(a.out),sort_keys=True))


if __name__=='__main__':main()
