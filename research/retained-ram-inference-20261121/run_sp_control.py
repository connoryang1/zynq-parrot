#!/usr/bin/env python3
"""Source-bound private single-clock RAM prototype under production synthesis options."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
BP=Path('/home/coyang/zynq-parrot-retained-maintenance/import/black-parrot')
HOST='coyang@haight.chillysky.com'
WRAPPER='/home/coyang/zynq-parrot/codex-skills/bp-fpga-synthesis/scripts/run_vivado_2024_2.sh'
CASES={'store-private-sp-prod':('d766d42cdf04ee43ca1e915fb9da06f5cc117dde',8)}


def bind(p):
    p=Path(p);raw=p.read_bytes()
    return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('case',choices=CASES);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    commit,threads=CASES[a.case]
    source=subprocess.check_output(['git','-C',str(BP),'show',commit+':bp_common/src/v/bp_retained_line_store.sv'])
    state=dict(state='PREPARED source-bound compiler isolation only',case=a.case,bp=commit,threads=threads,
               source_sha256=hashlib.sha256(source).hexdigest(),physical_operations=0)
    if not a.execute:print(json.dumps(state,indent=2));return
    out=HERE/(a.case+'01');out.mkdir();remote='/tmp/linux-retained-'+a.case+'-20261121-01'
    (out/'source.sv').write_bytes(source)
    tcl='''set_param general.maxThreads THREADS
create_project -in_memory -part xc7z020clg400-1
read_verilog -sv source.sv
synth_design -top bp_retained_line_store -part xc7z020clg400-1 -directive AreaOptimized_high -global_retiming on -control_set_opt_threshold 1 -generic i_lines_p=1280 -generic d_lines_p=1280 -generic sets_p=256
report_utilization -hierarchical -file utilization.rpt
set f [open primitives.tsv w]
foreach c [lsort [get_cells -hier -filter {REF_NAME =~ RAMB*}]] {
  puts $f [join [list $c [get_property REF_NAME $c] [get_property RAM_MODE $c] [get_property READ_WIDTH_A $c] [get_property WRITE_WIDTH_A $c] [get_property READ_WIDTH_B $c] [get_property WRITE_WIDTH_B $c]] "\\t"]
}
close $f
write_checkpoint -force synthesized.dcp
'''.replace('THREADS',str(threads))
    (out/'probe.tcl').write_text(tcl)
    state.update(started_utc=datetime.now(timezone.utc).isoformat(),inputs=[bind(out/'source.sv'),bind(out/'probe.tcl'),bind(__file__)],commands=[])
    def save():(out/'session.json').write_text(json.dumps(state,indent=2)+'\n')
    def run(label,argv,seconds,required=True):
        row=dict(label=label,argv=argv,timeout=seconds);state['commands'].append(row);save()
        try:
            with (out/(label+'.log')).open('wb') as log:r=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=seconds)
            row['returncode']=r.returncode
            if required and r.returncode:raise RuntimeError(label+' failed; source/partial evidence retained')
            return r.returncode
        finally:
            if (out/(label+'.log')).exists():row['log']=bind(out/(label+'.log'))
            save()
    ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-p','30041',HOST]
    try:
        run('admission',ssh+['test -x '+shlex.quote(WRAPPER)+' && ! pgrep -x vivado && test ! -e '+shlex.quote(remote)+' && mkdir '+shlex.quote(remote)],30)
        run('upload',['scp','-q','-P','30041',str(out/'source.sv'),str(out/'probe.tcl'),HOST+':'+remote+'/'],30)
        rc=run('synthesis',ssh+['cd '+shlex.quote(remote)+' && timeout --kill-after=15s 580s '+shlex.quote(WRAPPER)+' -mode batch -source probe.tcl -log vivado.log -journal vivado.jou'],620,False)
        collected=run('collect',['scp','-q','-r','-P','30041',HOST+':'+remote,str(out/'remote')],40,False)
        run('no-orphans',ssh+['! pgrep -x vivado'],20)
        if collected:raise RuntimeError('partial source/log collection failed')
        if rc:raise RuntimeError('compiler isolation arm failed; inspect preserved crash evidence')
        for n in ('utilization.rpt','primitives.tsv','synthesized.dcp'):
            if not (out/'remote'/n).is_file():raise RuntimeError('missing actual synthesis output')
        state.update(state='PASS standalone actual-store production-option synthesis only; no routed-fit claim',
                     outputs={n:bind(out/'remote'/n) for n in ('utilization.rpt','primitives.tsv','synthesized.dcp')})
    except BaseException as e:
        state.update(state='FAIL preserved compiler isolation only; no fit conclusion',error=repr(e));raise
    finally:state['closed_utc']=datetime.now(timezone.utc).isoformat();save()
    print(state['state'],a.case)

if __name__=='__main__':main()
