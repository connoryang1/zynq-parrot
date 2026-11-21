#!/usr/bin/env python3
"""One fresh-copy metadata mutation; success means the real miter rejects it."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
from run import RTL, HERE, binding


def limit():
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();build=args.build.resolve();output=args.output.resolve()
    assert not build.exists() and not output.exists()
    assert shutil.disk_usage(build.parent).free>=3*1024**3+256*1024**2
    build.mkdir();output.mkdir()
    matrix=json.loads((HERE/'evidence/matrix02/matrix.json').read_text())
    assert matrix['state']=='PASS-20-geometries-two-clocks-cycle-payload-coherence-miter'
    assert all(binding(Path(s['path']))==s for s in matrix['sources'])
    original=RTL.read_text();needle="if (state_r == e_clear) epochs_r[clear_set] <= '0;"
    assert original.count(needle)==1
    mutated=original.replace(needle,"if (state_r == e_clear) begin if (clear_set != '0) epochs_r[clear_set] <= '0; end")
    variant=build/'bp_retained_line_store.sv';variant.write_text(mutated)
    shutil.copyfile(variant,output/variant.name)
    ref=build/'bp_retained_line_store_reference.sv'
    ref.write_text((HERE/'reference-d766.sv').read_text().replace('module bp_retained_line_store\n','module bp_retained_line_store_reference\n'))
    rec=dict(state='running',mutation='Suppress only distributed D-epoch zero writes for set0 during tag-clear sweep; frozen original is unchanged.',original=binding(RTL),variant=binding(variant),reference=binding(HERE/'reference-d766.sv'),wrapper=binding(HERE/'retained_metadata_wrapper.sv'),driver=binding(HERE/'driver.cpp'),commands=[])
    def run(label,argv,cwd,timeout):
        with (output/(label+'.log')).open('wb') as f:
            result=subprocess.run(list(map(str,argv)),cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,preexec_fn=limit)
        rec['commands'].append(dict(label=label,argv=list(map(str,argv)),returncode=result.returncode,log=binding(output/(label+'.log'))))
        return result.returncode
    try:
        v='/home/coyang/zynq-parrot/install/bin/verilator'
        rc=run('build',[v,'--cc','--exe','--build','--trace-fst','--assert','-Wall','-DBP_RETAINED_METADATA_VERIFY','--top-module','retained_metadata_wrapper','-GI_LINES=9','-GD_LINES=13','-GRETAINED_SETS=4','-GEPOCH_WIDTH=2','-CFLAGS','-std=c++14','-j','2','--Mdir',build/'obj',variant,ref,HERE/'retained_metadata_wrapper.sv',HERE/'driver.cpp'],build,300)
        assert rc==0,'negative must first compile cleanly'
        runtime=build/'runtime';runtime.mkdir()
        rc=run('run',[build/'obj/Vretained_metadata_wrapper'],runtime,120)
        text=(output/'run.log').read_text()
        assert rc==1 and 'RETAINED_TEST_FAIL: cycle/payload/RAM-port miter mismatch at tick' in text
        assert 'RETAINED_METADATA_MITER_PASS' not in text and 'RETAINED_TEST_EXIT_CLEAN' not in text
        assert RTL.read_text()==original and all(binding(Path(s['path']))==s for s in matrix['sources'])
        rec.update(state='PASS-negative-metadata-clear-mutation-rejected-by-existing-cycle-miter',fst=binding(runtime/'retained-line-store.fst'),frozen_original_unchanged=True)
    except BaseException as e:
        rec.update(state='FAIL-negative-control-invalid',error=repr(e));raise
    finally:
        (output/'manifest.json').write_text(json.dumps(rec,indent=2)+'\n');print(rec['state'])

if __name__=='__main__':main()
