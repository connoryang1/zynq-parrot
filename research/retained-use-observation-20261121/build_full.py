#!/usr/bin/env python3
"""Clean scoped actual-fulltop build in fresh caller-owned HOME output only."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def binding(path):
    path=Path(path).resolve();data=path.read_bytes();stat=path.stat()
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                inode=stat.st_ino,mtime_ns=stat.st_mtime_ns,ctime_ns=stat.st_ctime_ns)


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();output=args.out.resolve();output.mkdir(parents=True,exist_ok=False)
    runtime=output/'verilator';runtime.mkdir();(output/'Makefile.design').symlink_to(ROOT/'cosim/black-parrot-example/Makefile.design')
    recipe=ROOT/'research/hp0-response-path-20261121/full-system-delay200-10/source-before.json.gz'
    command=json.loads(gzip.decompress(recipe.read_bytes()))['command_prefix']
    command=[arg.replace('/home/coyang/zynq-parrot-linux-capacity',str(ROOT)) for arg in command]
    command=[('BP_AXI_RESPONSE_DELAY=0' if arg.startswith('BP_AXI_RESPONSE_DELAY=') else arg) for arg in command]
    command+=['BP_RETAINED_OBSERVE=1']
    critical=[ROOT/path for path in ('cosim/black-parrot-example/v/top_zynq.sv','cosim/v/bp_retained_use_counters.sv',
        'cosim/black-parrot-example/Makefile.design','cosim/black-parrot-example/Makefile.hardware',
        'cosim/black-parrot-example/ps.cpp','cosim/black-parrot-example/ps.hpp','cosim/mk/Makefile.verilator',
        'testing/rtl/scoped-assertions/bsg_clkgate_optional.sv',
        'import/black-parrot/bp_top/src/v/bp_unicore_lite.sv','import/black-parrot/bp_me/src/v/cce/bp_uce.sv',
        'import/black-parrot/bp_common/src/v/bp_retained_line_store.sv')]
    before={str(path):binding(path) for path in critical}
    write(output/'source-before.json',dict(command_prefix=command,source=before,recipe=binding(recipe),
        scope='Actual fulltop observe1 native0 64/64 sets64; maintained scoped assertion guard, not global assertion acceptance'))
    env=os.environ.copy();env['LD_LIBRARY_PATH']='/home/coyang/zynq-parrot-linux-research/install/lib'+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    status=dict(state='clean pending',runtime=str(runtime),command=command)
    try:
        with (output/'clean.log').open('w') as log:subprocess.run(command+['clean'],cwd=runtime,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        status['state']='clean complete; build active';write(output/'status.json',status)
        with (output/'build.log').open('w') as log:subprocess.run(command+['build'],cwd=runtime,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=3600)
        if before!={str(path):binding(path) for path in critical}:raise ValueError('critical source changed during build')
        metadata=runtime/'obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat'
        sources={}
        for line in metadata.read_text().splitlines():
            match=re.fullmatch(r'S\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"([^"]+)"',line)
            if not match:continue
            size,inode,ctime,ctime_ns,mtime,mtime_ns=map(int,match.groups()[:6]);path=Path(match[7])
            record=binding(path)
            if (record['bytes'],record['inode'],record['mtime_ns'],record['ctime_ns'])!=(size,inode,mtime*10**9+mtime_ns,ctime*10**9+ctime_ns):
                raise ValueError('source ingestion metadata differs: '+str(path))
            sources[str(path)]=record
        for key in ('cosim/black-parrot-example/v/top_zynq.sv','cosim/v/bp_retained_use_counters.sv',
                    'import/black-parrot/bp_me/src/v/cce/bp_uce.sv'):
            if str(ROOT/key) not in sources:raise ValueError('owned source not consumed: '+key)
        write(output/'actual-source-list.json',dict(sources=sources,metadata=binding(metadata)))
        model=runtime/'obj_dir/Vbsg_nonsynth_zynq_testbench'
        status.update(state='PASS clean actual-fulltop build; runtime pending',model=binding(model),actual_sources=binding(output/'actual-source-list.json'))
    except BaseException as error:
        status.update(state='FAIL no runtime eligible',error=repr(error));raise
    finally:write(output/'status.json',status)
    print(output/'status.json')


if __name__=='__main__':main()
