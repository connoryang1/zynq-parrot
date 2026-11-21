#!/usr/bin/env python3
"""Prepare a self-contained native ARM build; no board action or execution."""
from pathlib import Path
import hashlib
import io
import json
import tarfile
import gzip

ROOT=Path('/home/coyang/zynq-parrot-linux-fit1280')
OUT=Path('/home/coyang/fpga-artifacts/context-resume/retained-observer-host-build-20261121')
REV='15288321bfb1443c5ce39318014f60cd979890f9'

def binding(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())

def main():
 import subprocess
 if subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()!=REV:raise ValueError('immutable candidate revision changed')
 OUT.mkdir(exist_ok=False)
 sources={}
 for p in sorted((ROOT/'cosim/include/common').glob('*.h')):sources['include/'+p.name]=p
 sources['include/bsg_zynq_pl.h']=ROOT/'cosim/include/zynq/bsg_zynq_pl.h'
 for name in ('ps.cpp','ps.hpp'):sources['src/'+name]=ROOT/'cosim/black-parrot-example'/name
 sources['src/main.cpp']=ROOT/'cosim/src/main.cpp'
 files={name:p.read_bytes() for name,p in sources.items()}
 defines={'HOST_ZYNQ':1,'BP_RETAINED_OBSERVE':1,'DRAM_ALLOCATE_SIZE_MB':46,'BP_NCPUS':1,'GP0_ENABLE':1,'GP0_ADDR_WIDTH':10,'GP0_DATA_WIDTH':32,'GP0_ADDR_BASE':'0x40000000','GP0_ADDR_SIZE_BYTES':4096,'GP1_ENABLE':1,'GP1_ADDR_WIDTH':30,'GP1_DATA_WIDTH':32,'GP1_ADDR_BASE':'0x80000000','GP1_ADDR_SIZE_BYTES':'0x30000000','HP0_ENABLE':1,'HP0_ADDR_WIDTH':32,'HP0_DATA_WIDTH':64,'HP0_ADDR_BASE':'0x00000000','ACLK_MHZ':20,'RTCLK_MHZ':8,'RT_CLK_ENABLE':1,'TAG_ENABLE':1,'BITSTREAM_FILE':'black_parrot_bd_1.bit'}
 command=['g++','-O2','-std=c++14','-mfpu=neon','-D_BSD_SOURCE','-D_DEFAULT_SOURCE','-Iinclude','-Isrc']+['-D'+k+'='+str(v) for k,v in defines.items()]+['src/main.cpp','src/ps.cpp','-o','control-program-observe1']
 manifest=dict(state='PREPARED native compiler inputs only; no target execution',top=REV,definitions=defines,compiler_argv_before_python_includes_and_libs=command,sources={n:dict(original=str(sources[n]),**binding(b)) for n,b in files.items()},native_python_config={'includes':['python3-config','--includes'],'libs':['python3-config','--libs']},scope='New optional diagnostic runner; accepted2dd runner remains fixed for application comparisons. Before privileged execution require exact observed hardware map and newrunner qualification plus rollback under shared reservation.')
 files['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
 data=io.BytesIO()
 with tarfile.open(fileobj=data,mode='w') as t:
  for name,b in files.items():
   info=tarfile.TarInfo(name);info.size=len(b);info.mode=0o644;info.mtime=0;t.addfile(info,io.BytesIO(b))
 archive=gzip.compress(data.getvalue(),mtime=0);(OUT/'source.tar.gz').write_bytes(archive);(OUT/'manifest.json').write_bytes(files['manifest.json'])
 (OUT/'preparation.json').write_text(json.dumps(dict(state='PASS preparation only',archive=binding(archive),unpacked_file_bytes=sum(map(len,files.values())),files=len(files)),indent=2)+'\n')
 print(OUT/'preparation.json')

if __name__=='__main__':main()
