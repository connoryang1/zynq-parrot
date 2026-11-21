#!/usr/bin/env python3
"""Require the dual-instance gate to reject a one-bit reference payload error."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import run as gate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--verilator',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    source=output/'source';source.mkdir()
    record=dict(state='running',scope='Host component negative control only; deliberately corrupts the reference read data, never production RTL.',
                inputs=[gate.artifact(p) for p in (gate.RTL,gate.GOLDEN/'driver.cpp',gate.GOLDEN/'retained_line_store_wrapper.sv',Path(gate.__file__),Path(__file__))],commands=[])
    def execute(label,argv,cwd,timeout):
        item=dict(argv=list(map(str,argv)),cwd=str(cwd),timeout_seconds=timeout)
        record['commands'].append(item);start=time.monotonic()
        with (output/(label+'.log')).open('wb') as log:
            result=subprocess.run(item['argv'],cwd=cwd,stdout=log,stderr=subprocess.STDOUT,
                                  timeout=timeout,preexec_fn=gate.file_limit)
        item.update(returncode=result.returncode,elapsed_seconds=time.monotonic()-start,
                    log=gate.artifact(output/(label+'.log')))
        return result.returncode
    try:
        gate.generate(source)
        reference=source/'bp_retained_line_store_before.sv'
        text=reference.read_text();old='assign data_rdata[port] = data_q;'
        assert text.count(old)==1
        reference.write_text(text.replace(old,"assign data_rdata[port] = data_q ^ 64'd1;"))
        record['mutation']='Original reference RAM read data XOR 1; production implementation and golden directed checks unchanged.'
        record['generated_sources']=[gate.artifact(p) for p in sorted(source.iterdir())]
        assert execute('build',[args.verilator,'--cc','--exe','--build','--trace-fst','--assert','-Wall',
            '--top-module','retained_line_store_wrapper','-GI_LINES=64','-GD_LINES=64',
            '-CFLAGS','-std=c++14','-j','2','--Mdir',output/'obj',gate.RTL,reference,
            source/'retained_line_store_wrapper.sv',source/'driver.cpp'],output,300)==0
        runtime=output/'runtime';runtime.mkdir()
        assert execute('run',[output/'obj/Vretained_line_store_wrapper'],runtime,120)==1
        text=(output/'run.log').read_text()
        assert text.count('RETAINED_TEST_FAIL: original/private RAM cycle mismatch')==1
        assert 'RETAINED_LINE_STORE_PASS' not in text and 'RETAINED_TEST_EXIT_CLEAN' not in text
        assert record['inputs']==[gate.artifact(p['path']) for p in record['inputs']], 'input drift'
        record['state']='PASS-deliberate-reference-payload-corruption-rejected'
    except BaseException as error:
        record.update(state='FAIL-preserved',error=repr(error));raise
    finally:
        (output/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
        print(output,record['state'])


if __name__=='__main__':main()
