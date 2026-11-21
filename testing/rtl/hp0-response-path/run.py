#!/usr/bin/env python3
"""Compile the exact common-top HP0 block, not a duplicate wrapper implementation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DESIGN = ROOT / 'cosim/black-parrot-example'
TOP = DESIGN / 'v/top_zynq.sv'

HEADER = '''module hp0_response_path #(parameter bit RETAINED=1, BYPASS=0)
 (input logic aclk,aresetn,hp0_axi_rvalid,hp0_axi_bvalid,consume_rready,consume_bready,
  input logic [63:0] hp0_axi_rdata, input logic [5:0] hp0_axi_rid,hp0_axi_bid,
  input logic [1:0] hp0_axi_rresp,hp0_axi_bresp, input logic hp0_axi_rlast,
  output logic hp0_axi_rready,hp0_axi_bready,rvalid_o,bvalid_o,
  output logic [63:0] rdata_o, output logic [5:0] rid_o,bid_o,
  output logic [1:0] rresp_o,bresp_o, output logic rlast_o);
 localparam C_HP0_AXI_DATA_WIDTH=64;
 localparam retained_buffer_p=RETAINED, prefetch_axi_bypass_lp=BYPASS;
 wire unused_native_inputs = &{1'b0,aclk,aresetn};
'''
FOOTER = '''assign bp_hp0_rready=consume_rready,bp_hp0_bready=consume_bready;
assign rvalid_o=bp_hp0_rvalid,bvalid_o=bp_hp0_bvalid;
assign rdata_o=bp_hp0_rdata,rid_o=bp_hp0_rid,rresp_o=bp_hp0_rresp,rlast_o=bp_hp0_rlast;
assign bid_o=bp_hp0_bid,bresp_o=bp_hp0_bresp;
endmodule
'''


def record(path):
    path = Path(path).resolve()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def limit():
    resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024*1024,32*1024*1024))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    inputs = [TOP,DESIGN/'Makefile.design',DESIGN/'Makefile.hardware',
              DESIGN/'v/bp_axi_response_delay.sv',DESIGN/'v/bp_axi_response_delay_fifo.sv',
              HERE/'driver.cpp',Path(__file__).resolve()]
    before = [record(p) for p in inputs]
    top = TOP.read_text()
    block = top.split('// BEGIN COMMON_HP0_RESPONSE_PATH\n',1)[1].split('// END COMMON_HP0_RESPONSE_PATH',1)[0]
    default = re.search(r'`ifndef BP_AXI_RESPONSE_DELAY.*?`endif',top,re.S)[0]
    setting = re.search(r'   localparam integer axi_response_delay_lp = .*?;',top)[0]
    for channel, fields in (('r',('data','valid','ready','id','last','resp')),('b',('valid','ready','id','resp'))):
        for field in fields:
            direction = 'o' if field=='ready' else 'i'
            assert f'.m_axi_{channel}{field}_{direction}(bp_hp0_{channel}{field})' in top
    generated = out/'hp0_response_path.sv'
    generated.write_text(default+'\n'+HEADER+setting+'\n'+block+FOOTER)
    results = dict(state='running',sources=before,generated=record(generated),cases=[])
    verilator = Path('/home/coyang/zynq-parrot/install/bin/verilator')
    try:
        for label,n,bypass in (('default0',0,False),('high384',384,False),('unsafe_bypass',0,True)):
            case = out/label; case.mkdir()
            command = [verilator,'--cc','--exe','--build','--trace-fst','-Wall','--top-module','hp0_response_path',
                       '-j','2','--Mdir',case/'obj','-CFLAGS',f'-std=c++14 -DDELAY={n}',
                       generated,inputs[3],inputs[4],HERE/'driver.cpp']
            if n: command += ['+define+BP_AXI_RESPONSE_DELAY='+str(n)]
            if bypass: command += ["-GBYPASS=1'b1"]
            else: command += ['--assert']
            with (case/'build.log').open('wb') as log:
                built = subprocess.run(list(map(str,command)),stdout=log,stderr=subprocess.STDOUT,timeout=180,preexec_fn=limit)
            assert built.returncode==0, str(case/'build.log')
            binary = case/'obj/Vhp0_response_path'
            with (case/'run.log').open('wb') as log:
                ran = subprocess.run([str(binary)],cwd=case,stdout=log,stderr=subprocess.STDOUT,timeout=30,preexec_fn=limit)
            text = (case/'run.log').read_text()
            if bypass:
                assert ran.returncode!=0 and 'require allocating L2' in text and 'HP0_RESPONSE_PATH_PASS' not in text
            else:
                assert ran.returncode==0 and text.count(f'HP0_RESPONSE_PATH_PASS N={n} ')==1
                assert 'HP0_RESPONSE_PATH_EXIT_CLEAN' in text
                generated_cpp = '\n'.join(p.read_text() for p in (case/'obj').glob('*.h'))
                assert ('return_delay' in generated_cpp)==bool(n),'native branch still elaborated a delay instance'
            results['cases'].append(dict(label=label,delay=n,bypass=bypass,
                assertions_enabled=not bypass,build_argv=list(map(str,command)),build_exit=built.returncode,
                run_exit=ran.returncode,build_log=record(case/'build.log'),run_log=record(case/'run.log'),
                binary=record(binary),fst=record(case/'hp0-response-path.fst')))
        assert before==[record(p) for p in inputs],'source changed during gate'
        results['state']='PASS exact extracted HP0 block N0/N384 and unsafe bypass rejection; no full core/FPGA fit'
    except BaseException as error:
        results.update(state='FAIL preserved',error=repr(error)); raise
    finally:
        (out/'manifest.json').write_text(json.dumps(results,indent=2)+'\n')
        print(results['state'],out)


if __name__=='__main__': main()
