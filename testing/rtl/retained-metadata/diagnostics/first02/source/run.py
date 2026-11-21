#!/usr/bin/env python3
"""Clean source-bound component miter only, no full model or FPGA calls."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RTL = ROOT/'import/black-parrot/bp_common/src/v/bp_retained_line_store.sv'
REFERENCE_SHA = 'aa36581844c5563f77bcc12f531776a4c858b1470a202d8f8394c7a02a7f8ea7'

def binding(p):
    data=p.read_bytes()
    return dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

def limit():
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--sets',type=int,default=256)
    parser.add_argument('--i-lines',type=int,default=1280)
    parser.add_argument('--d-lines',type=int,default=1280)
    parser.add_argument('--epoch-width',type=int,default=8)
    args=parser.parse_args()
    assert args.sets in (1,2,4,64,256) and 0<=args.i_lines<=1536 and 0<=args.d_lines<=1536
    assert args.epoch_width in (2,8)
    output=args.output.resolve()
    assert shutil.disk_usage(output.parent).free >= 3*1024**3+256*1024**2,'3GiB reserve plus256MiB build allocation'
    output.mkdir(exist_ok=False)
    sources=[RTL,HERE/'reference-d766.sv',HERE/'retained_metadata_wrapper.sv',HERE/'driver.cpp',Path(__file__).resolve()]
    rec=dict(state='running',parameters=dict(vars(args),output=str(output)),sources=[binding(p) for p in sources],commands=[],scope='Component cycle/payload/coherence equivalence only; no synthesis, full-core, route, area or application claim.')
    assert binding(HERE/'reference-d766.sv')['sha256']==REFERENCE_SHA,'exact original SP reference'
    (output/'source').mkdir()
    for p in sources: shutil.copyfile(p,output/'source'/p.name)
    reference=output/'source/reference-renamed.sv'
    text=(HERE/'reference-d766.sv').read_text()
    assert text.count('module bp_retained_line_store\n')==1
    reference.write_text(text.replace('module bp_retained_line_store\n','module bp_retained_line_store_reference\n'))
    rec['compiled_reference']=binding(reference)
    def run(label,argv,cwd,timeout):
        command=dict(label=label,argv=list(map(str,argv)),cwd=str(cwd),timeout_seconds=timeout)
        rec['commands'].append(command); started=time.monotonic()
        with (output/(label+'.log')).open('wb') as f:
            result=subprocess.run(command['argv'],cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,preexec_fn=limit)
        command.update(returncode=result.returncode,elapsed_seconds=time.monotonic()-started,log=binding(output/(label+'.log')))
        assert result.returncode==0,label+' failed'
    try:
        verilator='/home/coyang/zynq-parrot/install/bin/verilator'
        run('version',[verilator,'--version'],output,10)
        run('build',[verilator,'--cc','--exe','--build','--trace-fst','--assert','-Wall',
            '-DBP_RETAINED_METADATA_VERIFY','--top-module','retained_metadata_wrapper',
            '-GI_LINES='+str(args.i_lines),'-GD_LINES='+str(args.d_lines),'-GRETAINED_SETS='+str(args.sets),
            '-GEPOCH_WIDTH='+str(args.epoch_width),'-CFLAGS','-std=c++14','-j','2',
            '--Mdir',output/'obj',RTL,reference,HERE/'retained_metadata_wrapper.sv',HERE/'driver.cpp'],output,300)
        exe=output/'obj/Vretained_metadata_wrapper';rec['executable']=binding(exe)
        rec['runs']=[]
        for mode in ('inverted','different-periods'):
            runtime=output/mode;runtime.mkdir()
            run('run-'+mode,[exe]+([] if mode=='inverted' else [mode]),runtime,120)
            log=(output/('run-'+mode+'.log')).read_text()
            assert log.count('RETAINED_METADATA_MITER_PASS ')==1 and log.count('RETAINED_TEST_EXIT_CLEAN')==1
            assert log.count('RETAINED_METADATA_HAZARDS_PASS ')==1
            rec['runs'].append(dict(mode=mode,fst=binding(runtime/'retained-line-store.fst')))
        assert rec['sources']==[binding(p) for p in sources],'source changed during gate'
        assert shutil.disk_usage(output).free>=3*1024**3,'3GiB reserve'
        rec['state']='PASS-metadata-cycle-payload-coherence-miter'
    except BaseException as e:
        rec.update(state='FAIL-preserved',error=repr(e));raise
    finally:
        (output/'manifest.json').write_text(json.dumps(rec,indent=2)+'\n')
        print(output,rec['state'])

if __name__=='__main__':main()
