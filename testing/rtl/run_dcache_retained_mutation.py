#!/usr/bin/env python3
"""Real Dcache accepted-mutation pipeline gate; no core, SDK or board writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root=Path(__file__).resolve().parents[2];bp=root/'import/black-parrot';bsg=bp/'external/basejump_stl';here=Path(__file__).resolve().parent
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--verilator',type=Path,default=Path('/home/coyang/zynq-parrot-linux-research/install/bin/verilator'))
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[bp/'bp_common/src/include/bp_common_pkg.sv',bp/'bp_be/src/include/bp_be_pkg.sv',
             bp/'bp_be/src/v/bp_be_dcache/bp_be_dcache.sv',here/'dcache_retained_mutation_tb.sv']
    driver=here/'dcache_retained_mutation_driver.cpp'
    tracked=sources+[driver,Path(__file__)]+list((bp/'bp_common/src/include').glob('*.svh'))+list((bp/'bp_be/src/include').glob('*.svh'))
    before={str(f):sha(f) for f in tracked}
    command=[str(args.verilator.resolve()),'--cc','--exe','--build','--assert','--top-module','dcache_retained_mutation_tb',
        '--prefix','Vdcache_mutation','--Mdir',str(out/'obj'),'-j','2','-Wno-fatal',
        '-DBP_CUSTOM_BASE_CFG=bp_default_cfg_p','-DBP_DCACHE_FILL_WIDTH=64','-DBP_DCACHE_SETS=4']
    for d in [bsg/v for v in ('bsg_misc','bsg_cache','bsg_mem','bsg_dataflow','bsg_noc')]+[bp/v/'src/include' for v in ('bp_common','bp_be')]+[bp/'external/HardFloat/source',bp/'external/HardFloat/source/RISCV']:command+=['+incdir+'+str(d)]
    for d in [bsg/v for v in ('bsg_misc','bsg_cache','bsg_mem','bsg_dataflow')]+[bp/'bp_be/src/v/bp_be_dcache']:command+=['-y',str(d)]
    command+=list(map(str,sources))+[str(driver)]
    (out/'build-command.json').write_text(json.dumps(command,indent=2)+'\n')
    with (out/'build.log').open('w') as f:subprocess.run(command,cwd=root,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=240)
    if any(sha(Path(p))!=v for p,v in before.items()):raise RuntimeError('Source changed during build')
    with (out/'run.log').open('w') as f:subprocess.run([str(out/'obj/Vdcache_mutation')],cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=30)
    if '[DCACHE-MUTATION] PASS:' not in (out/'run.log').read_text():raise RuntimeError('Missing acceptance marker')
    if any(sha(Path(p))!=v for p,v in before.items()):raise RuntimeError('Source changed during run')
    (out/'verification.json').write_text(json.dumps(dict(passed=True,scope='Real Dcache pipeline with initialized L1/fake engine fixture; no core/FPGA claim',
        source_sha256=before,artifacts={n:sha(out/n) for n in ('build-command.json','run.log','obj/Vdcache_mutation')}),indent=2)+'\n')
    print((out/'run.log').read_text(),end='')


if __name__=='__main__':main()
