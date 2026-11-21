#!/usr/bin/env python3
"""Compare actual before/after UCE combinational endpoints without board traffic."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
BASE='e10992a3eea3ba2ef6ae3ccb42ff5e8c658286a8'


def bind(path):
    path=Path(path).resolve();data=path.read_bytes()
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('adapter source contract: '+old)
    return text.replace(old,new)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    bp=ROOT/'import/black-parrot';bsg=bp/'external/basejump_stl';uce=bp/'bp_me/src/v/cce/bp_uce.sv'
    old=subprocess.check_output(['git','-C',str(bp),'show',BASE+':bp_me/src/v/cce/bp_uce.sv'],text=True)
    before=out/'bp_uce_before.sv';before.write_text(replace_once(old,'module bp_uce\n','module bp_uce_before\n'))
    base=ROOT/'testing/rtl/uce_retained_tb.sv';adapter=base.read_text();generated=[]
    for name,module in [('before','bp_uce_before'),('after','bp_uce')]:
        text=replace_once(adapter,'module uce_retained_tb\n','module uce_maintenance_'+name+'\n')
        text=replace_once(text,'#(parameter int retained_lines_p=64',
            '#(parameter bit test_retained_p=1, test_priority_p=0, test_sidebuffer_p=0\n   , parameter int retained_lines_p=64')
        text=replace_once(text,'(input clk_i,reset_i,enable_i', '(input test_hit_i\n  ,input clk_i,reset_i,enable_i')
        text=replace_once(text,"req='0;req.msg_type", "req='0;req.hit=test_hit_i;req.msg_type")
        text=replace_once(text,'bp_uce #(',module+' #(')
        text=replace_once(text,'.retained_buffer_p(1)',
            '.retained_buffer_p(test_retained_p),.prefetch_demand_priority_p(test_priority_p),.prefetch_side_buffer_p(test_sidebuffer_p)')
        target=out/('adapter_'+name+'.sv');target.write_text(text);generated.append(target)
    sources=[bp/'bp_common/src/include/bp_common_pkg.sv',bp/'bp_me/src/include/bp_me_pkg.sv',
             bp/'bp_common/src/v/bp_retained_line_store.sv',before,uce,*generated,HERE/'endpoint.sv']
    tracked=sources+[base,HERE/'driver.cpp',Path(__file__)]+list((bp/'bp_common/src/include').glob('*.svh'))+list((bp/'bp_me/src/include').glob('*.svh'))
    bindings=[bind(path) for path in tracked]
    includes=[bsg/v for v in ('bsg_misc','bsg_cache','bsg_mem','bsg_dataflow','bsg_noc')]+[bp/v/'src/include' for v in ('bp_common','bp_me')]
    libraries=[bsg/v for v in ('bsg_misc','bsg_dataflow','bsg_mem')]+[bp/'bp_me/src/v/network',bp/'bp_me/src/v/cce',bp/'bp_common/src/v']
    cmd=['/home/coyang/zynq-parrot-linux-research/install/bin/verilator','--cc','--exe','--build','--assert',
         '--top-module','uce_maintenance_endpoint','--prefix','Vmaintenance','--Mdir',str(out/'obj'),'-j','2','-Wno-fatal',
         '-DBP_CUSTOM_BASE_CFG=bp_default_cfg_p','-DBP_DCACHE_FILL_WIDTH=64','-DBP_ICACHE_FILL_WIDTH=64','-DBP_BEDROCK_FILL_WIDTH=64']
    cmd+=['+incdir+'+str(path) for path in includes]
    for path in libraries:cmd+=['-y',str(path)]
    cmd+=list(map(str,sources))+[str(HERE/'driver.cpp')]
    (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
    with (out/'build.log').open('w') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=360)
    with (out/'run.log').open('w') as log:subprocess.run([str(out/'obj/Vmaintenance')],cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    if '[UCE-MAINTENANCE] PASS endpoints=18370560' not in (out/'run.log').read_text():raise ValueError('missing exhaustive gate')
    if [bind(path) for path in tracked]!=bindings:raise ValueError('source changed during endpoint gate')
    result=dict(state='PASS exhaustive actual before/after UCE combinational endpoint equivalence',endpoints=18370560,
                states=23,legal_opcodes=[0,1,2,3,4,5,6,7,8,9,11,12,13],installer_states=10,boolean_endpoints=512,
                parameter_variants='12 legal retained0/1 x demandpriority0/1 x sidebuffer0/1 x I64-writeback0/D64-writeback1 combinations; production-forbidden retained+sidebuffer excluded',
                source_bindings=bindings,command=bind(out/'command.json'),run=bind(out/'run.log'),model=bind(out/'obj/Vmaintenance'),
                limits='Actual UCE common-yumi datapaths compared. Forced combinational endpoint/state coverage includes unreachable combinations, not clocked ownership/traffic proof. Baseline UNOPTFLAT is intentional; fixed fulltop requires separate acyclic structural gate.')
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'verification.json')


if __name__=='__main__':main()
