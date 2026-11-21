#!/usr/bin/env python3
"""Build real UCE+retained backend in fresh isolated storage; no board/core run."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root=Path(__file__).resolve().parents[2]
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--lines',type=int,default=64,choices=(64,128,256,512,1024,2048))
    p.add_argument('--icache',action='store_true',help='I request/writeback0 configuration; all8 payload words checked')
    p.add_argument('--icache-fill-width',type=int,choices=(64,128),default=64,
                   help='accepted I64/BedRock64 primary, matching128 supplemental functional coverage')
    p.add_argument('--verilator',type=Path,default=Path('/home/coyang/zynq-parrot-linux-research/install/bin/verilator'))
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    bp=root/'import/black-parrot';bsg=bp/'external/basejump_stl';here=Path(__file__).resolve().parent
    sources=[bp/'bp_common/src/include/bp_common_pkg.sv',bp/'bp_me/src/include/bp_me_pkg.sv',
             bp/'bp_common/src/v/bp_retained_line_store.sv',bp/'bp_me/src/v/cce/bp_uce.sv',here/'uce_retained_tb.sv']
    driver=here/'uce_retained_driver.cpp'
    tracked=sources+[driver,Path(__file__)]+list((bp/'bp_common/src/include').glob('*.svh'))+list((bp/'bp_me/src/include').glob('*.svh'))
    before={str(f):digest(f) for f in tracked}
    includes=[bsg/v for v in ('bsg_misc','bsg_cache','bsg_mem','bsg_dataflow','bsg_noc')]
    includes += [bp/v/'src/include' for v in ('bp_common','bp_me')]
    libraries=[bsg/v for v in ('bsg_misc','bsg_dataflow','bsg_mem')]+[bp/'bp_me/src/v/network',bp/'bp_me/src/v/cce',bp/'bp_common/src/v']
    command=[str(args.verilator.resolve()),'--cc','--exe','--build','--assert','--trace-fst',
             '--top-module','uce_retained_tb','--prefix','Vuce_retained','--Mdir',str(out/'obj'),'-j','2','-Wno-fatal',
             '-DBP_CUSTOM_BASE_CFG=bp_default_cfg_p','-DBP_DCACHE_FILL_WIDTH=64',
             '-DBP_BEDROCK_FILL_WIDTH='+str(args.icache_fill_width if args.icache else 64),
             '-Gretained_lines_p='+str(args.lines)]
    if args.icache:command+=['-Ginstruction_p=1','-DBP_ICACHE_FILL_WIDTH='+str(args.icache_fill_width)]
    command += ['+incdir+'+str(v) for v in includes]
    for v in libraries:command+=['-y',str(v)]
    command += list(map(str,sources))+[str(driver)]
    (out/'build-command.json').write_text(json.dumps(command,indent=2)+'\n')
    with (out/'build.log').open('w') as log:subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    if any(digest(Path(f))!=d for f,d in before.items()):raise RuntimeError('Source changed during build; output unaccepted')
    with (out/'run.log').open('w') as log:subprocess.run([str(out/'obj/Vuce_retained')],cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
    marker='[UCE-RETAINED-I] PASS:' if args.icache else '[UCE-RETAINED] PASS:'
    if marker not in (out/'run.log').read_text():raise RuntimeError('Missing functional acceptance marker')
    negative=out/'short-response';negative.mkdir()
    with (negative/'run.log').open('w') as log:
        result=subprocess.run([str(out/'obj/Vuce_retained'),'--short-response'],cwd=negative,stdout=log,
            stderr=subprocess.STDOUT,timeout=30,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
    if result.returncode==0 or 'UCE prefetch response has no live slot' not in (negative/'run.log').read_text():
        raise RuntimeError('16B reply to full64B request did not fail its specific RTL ownership assertion')
    drained=out/'short-response-drain';drained.mkdir()
    with (drained/'run.log').open('w') as log:
        subprocess.run([str(out/'obj/Vuce_retained'),'--short-response-drain'],cwd=drained,stdout=log,
            stderr=subprocess.STDOUT,check=True,timeout=30)
    if '[UCE-SHORT-DRAIN] PASS:' not in (drained/'run.log').read_text():raise RuntimeError('Missing assertion-disabled partial-packet guard proof')
    if any(digest(Path(f))!=d for f,d in before.items()):raise RuntimeError('Source changed during test; output unaccepted')
    (out/'verification.json').write_text(json.dumps(dict(passed=True,scope='Real standalone UCE+BRAM backend; L1 miss/array endpoints supplied, not full core/FPGA evidence',
        lines=args.lines,instruction=args.icache,icache_fill_width=args.icache_fill_width if args.icache else None,
        payload_bytes_per_line=64,short_response_rejected=True,assertion_disabled_short_response_drained=True,source_sha256=before,
        artifacts={n:digest(out/n) for n in ('build-command.json','run.log','short-response/run.log','short-response-drain/run.log','uce-retained.fst','obj/Vuce_retained')}),indent=2)+'\n')
    print((out/'run.log').read_text(),end='')


if __name__=='__main__':main()
