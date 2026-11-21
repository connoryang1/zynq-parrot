#!/usr/bin/env python3
"""Isolated clean traced response-delay gate; GCC9, no SV timing coroutines."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCES=[ROOT/'cosim/black-parrot-example/v/bp_axi_response_delay.sv',
         ROOT/'cosim/black-parrot-example/v/bp_axi_response_delay_fifo.sv',
         HERE/'axi_response_delay_wrapper.sv',HERE/'driver.cpp',Path(__file__).resolve()]


def artifact(path):
    path=Path(path).resolve()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def file_limit():resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024*1024,32*1024*1024))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--counter-width',choices=(12,32),type=int,default=32)
    parser.add_argument('--fifo-els',type=int,default=512)
    parser.add_argument('--verilator',type=Path,default=Path('/home/coyang/zynq-parrot/install/bin/verilator'))
    args=parser.parse_args()
    if not 2<=args.fifo_els<=512:parser.error('unit gate supports2through512 entries')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    record=dict(state='running',scope='Response-stream protocol/added-clock unit gate only; not DRAM/load-use or FPGA calibration.',
                counter_width=args.counter_width,fifo_els=args.fifo_els,commands=[],sources={p.name:artifact(p)for p in SOURCES})
    try:
        if shutil.disk_usage(out).free<80*1024*1024:raise RuntimeError('insufficient local headroom; use isolated root RAM output')
        (out/'source').mkdir()
        for source in SOURCES:shutil.copyfile(source,out/'source'/source.name)
        def run(label,argv,timeout):
            command=dict(label=label,argv=list(map(str,argv)),timeout_seconds=timeout);record['commands'].append(command)
            start=time.monotonic()
            with (out/(label+'.log')).open('wb')as log:
                result=subprocess.run(command['argv'],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,preexec_fn=file_limit)
            command.update(returncode=result.returncode,elapsed_seconds=time.monotonic()-start,log=artifact(out/(label+'.log')))
            if result.returncode:raise RuntimeError(label+' failed:'+str(result.returncode))
        run('version',[args.verilator,'--version'],10)
        run('build',[args.verilator,'--cc','--exe','--build','--trace-fst','--assert','-Wall','--top-module','axi_response_delay_wrapper',
            '-GCOUNTER_WIDTH='+str(args.counter_width),'-GFIFO_ELS='+str(args.fifo_els),'-CFLAGS','-std=c++14','-j','2','--Mdir',out/'obj']+SOURCES[:4],300)
        binary=out/'obj/Vaxi_response_delay_wrapper'
        run('run',[binary],60)
        text=(out/'run.log').read_text()
        expected=f'AXI_RESPONSE_DELAY_PASS FIFO={args.fifo_els} COUNTER={args.counter_width}'
        assert text.count(expected)==1and text.count('AXI_DELAY_EXIT_CLEAN')==1,'missing exact clean completion'
        assert 'AXI_DELAY_NATIVE_COMBINATIONAL_IDENTITY_PASS'in text and'AXI_DELAY_CONFIG_DRAIN_RESET_PASS'in text
        for source in SOURCES:assert artifact(source)==record['sources'][source.name],'source changed during gate'
        record.update(state='PASS-clean-response-delay-unit',executable=artifact(binary),fst=artifact(out/'axi-response-delay.fst'))
    except BaseException as error:
        record.update(state='FAIL-preserved-not-calibration-evidence',error=repr(error));raise
    finally:
        (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n');print(out,record['state'])


if __name__=='__main__':main()
