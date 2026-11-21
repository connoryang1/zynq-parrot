#!/usr/bin/env python3
"""Prepare one immutable natural-retention ELF and exact mode-word NBF patches.
No simulator, FPGA, synthesis or target execution is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
INSTALL=Path('/home/coyang/zynq-parrot/install')
OLD=Path('/home/coyang/zynq-parrot-linux-research/research/resume-data-reuse-20261120/compact-thirtytwo-kib')
sys.path.insert(0,str(ROOT/'linux-tests'))
from patch_nbf_memory_records import patch


def bind(path):
 p=Path(path).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def elf_bytes(data,address,size):
 # Program headers establish file-backed bytes independently of symbol type.
 if data[:6]!=b'\x7fELF\x02\x01':raise ValueError('RV64 little-endian ELF required')
 phoff=struct.unpack_from('<Q',data,32)[0];entsize,count=struct.unpack_from('<HH',data,54)
 for n in range(count):
  typ,flags,offset,va,pa,filesz,memsz,align=struct.unpack_from('<II6Q',data,phoff+n*entsize)
  if typ==1 and va<=address and address+size<=va+filesz:return data[offset+address-va:offset+address-va+size]
 raise ValueError('config not file-backed')


def patch_mode(text,address,mode):
 if mode not in (0,9,6,15) or address<0x80000000 or address&7:raise ValueError('invalid mode/address')
 lines=text.splitlines()
 if '\n'.join(lines)+'\n'!=text:raise ValueError('noncanonical NBF')
 changed=patch(lines,[(address,(1<<64)-1,mode)])
 if len(changed)!=len(lines) or sum(a!=b for a,b in zip(lines,changed))!=1:raise ValueError('not exactly one mode record')
 if patch(changed,[(address,mode,(1<<64)-1)])!=lines:raise ValueError('patch not reversible')
 return '\n'.join(changed)+'\n'


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 files=('testing/mt_retained_resume_data_benchmark.c','testing/mt_seed.h','linux-tests/resume_workload.h')
 record=dict(state='preparing-no-target-execution',sources={},commands=[],old_f35=dict(session=bind(OLD/'session.json'),source=bind(OLD/'source/testing/mt_resume_data_reuse_benchmark.c'),elf_sha256='f35e5da8dcb527cfa04c16edab0616f1f80a7715c9b05278500799c9b66393dd'),purpose='New whole-lifecycle dataset with unchanged lookup generator, fixed32KiB private inputs and mode-only NBF control. Not a result.')
 for rel in files:
  src=ROOT/rel;dest=out/'source'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);record['sources'][rel]=bind(src)
 old_header=OLD/'source/linux-tests/resume_workload.h'
 if bind(old_header)['sha256']!=record['sources']['linux-tests/resume_workload.h']['sha256']:raise ValueError('generator differs from closed F35')
 record['generator_byte_identical_to_f35']=True
 program=out/'program';program.mkdir();elf=program/'benchmark.riscv'
 def run(label,cmd):
  r=subprocess.run(list(map(str,cmd)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60);(program/(label+'.log')).write_text(r.stdout);record['commands'].append(dict(label=label,argv=list(map(str,cmd)),returncode=r.returncode,log=bind(program/(label+'.log'))))
  if r.returncode:raise ValueError(label+' failed')
  return r.stdout
 try:
  flags=['-O2','-Wall','-Wextra','-Werror','-I'+str(INSTALL/'riscv64-unknown-elf/include'),'--specs='+str(INSTALL/'riscv64-unknown-elf/lib/dramfs.specs'),'--specs='+str(INSTALL/'riscv64-unknown-elf/lib/perch.specs'),'-DNUM_THREADS=2','-DBP_NUM_THREADS=2','-DBP_NUM_CONTEXTS=4','-DBP_RESUME_ZLIB=0','-Wl,--defsym=__heap_size=0x40000']
  run('compile',[INSTALL/'bin/riscv64-unknown-elf-gcc']+flags+['-o',elf,out/'source/testing/mt_retained_resume_data_benchmark.c'])
  text=run('symbols',[INSTALL/'bin/riscv64-unknown-elf-nm','-n','-S',elf]);symbols={}
  for line in text.splitlines():
   f=line.split()
   if len(f)==4:symbols[f[3]]=dict(address=int(f[0],16),size=int(f[1],16),type=f[2])
   elif len(f)==3:symbols[f[2]]=dict(address=int(f[0],16),size=0,type=f[1])
  config=symbols['resume_retained_control'];address=config['address']
  if config['size']!=8 or config['type'] not in ('D','d') or elf_bytes(elf.read_bytes(),address,8)!=b'\xff'*8:raise ValueError('configuration is not the exact initialized8B word')
  if symbols['__heap_size']['address']!=0x40000 or symbols['__heap_end']['address']-symbols['_end']['address']<0x40000:raise ValueError('fixed heap bound')
  run('disassembly',[INSTALL/'bin/riscv64-unknown-elf-objdump','-dr',elf]);mem=program/'prog.mem';run('objcopy',[INSTALL/'bin/riscv64-unknown-elf-objcopy','-O','verilog',elf,mem]);mem.write_text(mem.read_text().replace('@8','@0'))
  nbf=program/'prog.nbf';cmd=['python3',ROOT/'import/black-parrot/bp_common/software/py/nbf.py','--skip_zeros','--config','--debug','--mem',mem,'--ncpus','1'];r=subprocess.run(list(map(str,cmd)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60);nbf.write_text(r.stdout);(program/'nbf.stderr').write_text(r.stderr)
  if r.returncode:raise ValueError('NBF generation failed')
  patches={}
  for mode in (0,9,6,15):
   dest=program/f'mode{mode}.nbf';dest.write_text(patch_mode(nbf.read_text(),address,mode));patches[str(mode)]=bind(dest)
  for rel,b in record['sources'].items():
   if bind(ROOT/rel)!=b:raise ValueError('source changed while preparing')
  record.update(state='PREPARED-crosslink-layout-modepatch-checks-PASS-no-execution',elf=bind(elf),nbf=bind(nbf),mem=bind(mem),mode_patches=patches,symbols=symbols,
                compiler=bind(INSTALL/'bin/riscv64-unknown-elf-gcc'),nbf_tool=bind(ROOT/'import/black-parrot/bp_common/software/py/nbf.py'),heap=dict(bytes=0x40000,end=symbols['_end']['address'],heap_end=symbols['__heap_end']['address']))
 except BaseException as e:record.update(state='FAIL-preparation-preserved',error=repr(e));raise
 finally:(out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n');print(out/'manifest.json',record['state'])

if __name__=='__main__':main()
