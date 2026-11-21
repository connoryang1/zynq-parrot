#!/usr/bin/env python3
"""Read closed FST geometry and clean selected-block EOF without target execution."""
import argparse
import json
from pathlib import Path
import subprocess
from run_fullcore import bind as artifact

BASE='TOP.bsg_nonsynth_zynq_testbench.dut.top_fpga_inst'
CORE=BASE+'.blackparrot.processor.u.unicore.unicore_lite'
STORE=CORE+'.retained_store.storage'
EXPECTED={
 'tag_rows':(STORE+'.tag_rows_lp',1),
 'tag_row_bits':(STORE+'.tag_word_bits_lp',145),
 'tag_depth':(STORE+'.tag_depth_lp',512),
 'epoch_width':(STORE+'.epoch_width_p',8),
 'physical_address_width':(STORE+'.paddr_width_p',34),
 'payload_slots':(STORE+'.total_lines_lp',2560),
 'retained_i_lines':(STORE+'.i_lines_p',1280),
 'retained_d_lines':(STORE+'.d_lines_p',1280),
 'retained_sets':(STORE+'.sets_p',256),
 'hp0_delay':(BASE+'.axi_response_delay_lp',0),
 'resident_slots':(CORE+'.core_minimal.be.num_threads_p',2),
 'logical_contexts':(CORE+'.core_minimal.be.num_contexts_p',4)}
for lane,path in [('i',CORE+'.core_minimal.fe.icache'),('d',CORE+'.core_minimal.be.calculator.pipe_mem.dcache')]:
    for key,want in [('sets_p',64),('assoc_p',8),('block_width_p',512)]:EXPECTED[lane+'_'+key]=(path+'.'+key,want)
READER='a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',type=Path,required=True);p.add_argument('--reader',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=json.loads(a.session.read_text())
    if not m['state'].startswith('PASS-') or artifact(m['trace']['path'])!=m['trace']:raise ValueError('closed passed trace required')
    reader=artifact(a.reader)
    if reader['sha256']!=READER:raise ValueError('reader differs from source-reviewed artifact')
    a.output.mkdir(parents=True,exist_ok=False);selection=a.output/'selection.tsv'
    selection.write_text(''.join(k+'\t'+path+'\n' for k,(path,_) in EXPECTED.items())+'store_clock\t'+STORE+'.clk_i\nstore_reset\t'+STORE+'.reset_i\n')
    cmd=[reader['path'],m['trace']['path'],str(selection.resolve())]
    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)
    (a.output/'reader.stderr').write_text(result.stderr)
    lines=result.stdout.splitlines()
    if result.returncode or not lines or lines[-1]!='#END':raise ValueError('selected reader did not finish clean EOF')
    ids={};headers={};observed={};events=0
    for line in lines:
        f=line.split('\t')
        if f[0]=='#FST':headers=dict(start_tick=int(f[1]),end_tick=int(f[2]),timescale_exponent=int(f[3]))
        elif f[0]=='#SIGNAL':
            key,width,handle,path=f[1],int(f[2]),int(f[3]),f[4]
            if key in EXPECTED:
                if width!=(1 if key=='tag_rows' else 32) or path!=EXPECTED[key][0]:raise ValueError('wrong parameter declaration')
            ids.setdefault(handle,[]).append(key)
        elif f[0].isdigit():
            events+=1
            for key in ids[int(f[1])]:
                if key not in EXPECTED:continue
                if any(c in f[2].lower() for c in 'xz'):raise ValueError('unknown parameter')
                value=int(f[2],2)
                if value!=EXPECTED[key][1]:raise ValueError('wrong actual geometry: '+key)
                observed[key]=value
    if set(observed)!=set(EXPECTED) or headers['end_tick']<=headers['start_tick']:raise ValueError('incomplete observed geometry/time')
    if artifact(m['trace']['path'])!=m['trace']:raise ValueError('FST changed during audit')
    (a.output/'selected-events.tsv').write_text(result.stdout)
    report=dict(state='PASS-closed-geometry-and-selected-reader-EOF',session=artifact(a.session),trace=m['trace'],reader=reader,analyzer=artifact(__file__),selection=artifact(selection),events=artifact(a.output/'selected-events.tsv'),observed=observed,trace_time=headers,selected_events=events,command=cmd,
                limits='Static elaborated geometry and closed selected-FST block iteration only; no architectural access counts, unique capacity, workload benefit, synthesis, routed timing or FPGA claim.')
    (a.output/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(observed,sort_keys=True))

if __name__=='__main__':main()
