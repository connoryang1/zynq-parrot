#!/usr/bin/env python3
"""Fresh1280 integrity software only; immutable cold08 reuse, no model execution."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import time

import budget,materialize
ROOT=materialize.SOURCE
sys = __import__('sys');sys.dont_write_bytecode=True
sys.path.insert(0,str(materialize.PREVIOUS));import software_owned_v2 as owned
HISTORICAL=Path('/home/coyang/zynq-parrot-retained-dense')
HERE=Path(__file__).resolve().parent
INSTALL=Path('/home/coyang/zynq-parrot-linux-research/install')
BASE=budget.BASE

def bind(p):
 p=Path(p).resolve();h=hashlib.sha256()
 with p.open('rb') as f:
  for raw in iter(lambda:f.read(1048576),b''):h.update(raw)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())

def check():
 budget.check()
 out=BASE/'program01'
 used=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()) if out.exists() else 0
 budget.require(used<=8*1024**2,'software output8MiB inside whole1GiB source/run pool')
 return dict(output_bytes=used,whole=budget.check())

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--admission',type=Path,required=True);ap.add_argument('--admission-sha256',required=True);a=ap.parse_args();authority=budget.configure(a.admission,a.admission_sha256);budget.require('software-preparation' in authority['actions'],'ROOT software action');materialize.verify();out=a.out.resolve();assert out==BASE/'program01'
 assert out.parent==BASE and not out.exists();BASE.mkdir(exist_ok=True);check();out.mkdir();(out/'bp-tests').mkdir();(out/'source').mkdir()
 inputs=[ROOT/'testing/rtl/large_retained_system_test.c',ROOT/'testing/Makefile',ROOT/'testing/mt_seed.h',INSTALL/'riscv64-unknown-elf/include/bp_utils.h',Path(__file__).resolve()]
 before=[bind(p) for p in inputs]
 assert before[0]['sha256']=='8d7d447d2d8d500361b89a4a7ddd356f0dba01dff017129418cf3571bf9dd03c','unchanged accepted integrity C'
 assert before[1]['sha256']=='e76712c343a5bb2486caeda82d27e22726864339db9deabd447035cae29c16ef','same maintained compile rule'
 for p in inputs:shutil.copyfile(p,out/'source'/p.name)
 record=dict(state='running',sources=before,commands=[],topology=dict(resident=2,logical=4),expected=dict(i_lines=1280,d_lines=1280,sets=256),scope='Software preparation only; no target/model execution.')
 def run(label,argv,timeout=60):
  row=dict(label=label,argv=list(map(str,argv)));record['commands'].append(row)
  with (out/(label+'.log')).open('wb') as f:
   try:row['owned']=owned.run(list(map(str,argv)),out,dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(out)),f,timeout,check,lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
   except BaseException as e:row['owned']=getattr(e,'owned_receipt',None);raise
  row.update(returncode=row['owned']['returncode'],log=bind(out/(label+'.log')));assert row['returncode']==0 and not row['owned']['owned_group_remaining'],label;check()
 try:
  cc=INSTALL/'bin/riscv64-unknown-elf-gcc';objcopy=INSTALL/'bin/riscv64-unknown-elf-objcopy';objdump=INSTALL/'bin/riscv64-unknown-elf-objdump';readelf=INSTALL/'bin/riscv64-unknown-elf-readelf'
  elf=out/'bp-tests/mt_large_retained_system_test.riscv'
  opts=['TOP='+str(ROOT),'ZP_INSTALL_DIR='+str(INSTALL),'ZP_RISCV_DIR='+str(out),'NUM_THREADS=2','NUM_CONTEXTS=4','BP_RETAINED_I_LINES=1280','BP_RETAINED_D_LINES=1280','BP_RETAINED_SETS=256']
  make=['make','-f',str(ROOT/'testing/Makefile'),str(elf)]+opts
  run('compile-dry',make[:1]+['-n']+make[1:])
  flags=['-O2','-I'+str(ROOT/'software/include'),'-I'+str(INSTALL/'riscv64-unknown-elf/include'),'--specs='+str(INSTALL/'riscv64-unknown-elf/lib/dramfs.specs'),'--specs='+str(INSTALL/'riscv64-unknown-elf/lib/perch.specs'),'-DNUM_THREADS=2','-DBP_NUM_THREADS=2','-DBP_NUM_CONTEXTS=4','-DBENCH_DIAGNOSTIC=0','-DBENCH_BARRIER=0','-I'+str(ROOT/'testing'),'-DBP_EXPECT_I_LINES=1280','-DBP_EXPECT_D_LINES=1280','-DBP_EXPECT_RETAINED_SETS=256']
  line=next(l for l in (out/'compile-dry.log').read_text().splitlines() if str(cc) in l and ' -o ' in l)
  parsed=shlex.split(line);redirect=parsed.index('>>');actual=parsed[:redirect];expected=[str(cc),'-o',str(elf),str(inputs[0])]+flags;assert actual==expected,'actual maintained rule flags differ'
  run('compile',make)
  run('compiler-version',[cc,'--version']);run('actual-driver-link',[cc,'-###','-o',elf,inputs[0]]+flags)
  link_line=next(l for l in (out/'actual-driver-link.log').read_text().splitlines() if 'collect2' in l and ' -o ' in l);args=shlex.split(link_line)
  files=[Path(x) for x in args if x.startswith('/') and Path(x).is_file()];dirs=[Path(x[2:]) for x in args if x.startswith('-L')]
  for name in ('c','gloss_dramfs','perch','gcc'):
   match=next((d/('lib'+name+'.a') for d in dirs if (d/('lib'+name+'.a')).exists()),None);assert match is not None,'actual linked library '+name;files.append(match)
  files += [INSTALL/'riscv64-unknown-elf/lib/dramfs.specs',INSTALL/'riscv64-unknown-elf/lib/perch.specs']
  record['link_inputs']=[bind(p) for p in sorted(set(p.resolve() for p in files))]
  (out/'link-inputs').mkdir()
  for p in sorted(set(p.resolve() for p in files)):
   if p.suffix in ('.o','.ld','.specs'):shutil.copyfile(p,out/'link-inputs'/p.name)
  record['tools']=[bind(p) for p in (cc,objcopy,objdump,readelf)]
  run('disassembly',[objdump,'-dr',elf]);run('readelf',[readelf,'-a',elf]);run('new-comment',[readelf,'-p','.comment',elf])
  closure=HISTORICAL/'research/retained-system-geometry-20261121/closure'
  old=gzip.decompress((closure/'integrity-prog.riscv.gz').read_bytes());assert hashlib.sha256(old).hexdigest()=='2fab907445c24b77a3181fd870d7ae8370c72bfc80bff13b4b14ecfc4b3edac7'
  reference=out/'accepted1280-reference.riscv';reference.write_bytes(old);run('accepted-compiler-comment',[readelf,'-p','.comment',reference]);assert (out/'new-comment.log').read_bytes()==(out/'accepted-compiler-comment.log').read_bytes(),'accepted compiler identity differs'
  shutil.copyfile(elf,out/'integrity-prog.riscv');run('objcopy',[objcopy,'-O','verilog',elf,out/'integrity-prog.mem'])
  mem=out/'integrity-prog.mem';mem.write_text(mem.read_text().replace('@8','@0'))
  nbf_script=ROOT/'import/black-parrot/bp_common/software/py/nbf.py';run('nbf',['python3',nbf_script,'--skip_zeros','--config','--debug','--mem',mem,'--ncpus','1'])
  shutil.copyfile(out/'nbf.log',out/'integrity-prog.nbf')
  fixture=Path('/home/coyang/zynq-parrot-linux-fit1280/research/retained-control-abi-20261121/advisory-fixture-cold08/manifest.json');f=json.loads(fixture.read_text());source=Path(f['source']['path']);assert bind(source)==f['source']
  assert '!((raw >> 16) & 0xffff) || !((raw >> 32) & 0xffff)' in source.read_text()
  programs={'integrity':{k:bind(out/('integrity-prog.'+ext)) for k,ext in [('elf','riscv'),('nbf','nbf')]}}
  for ext,wanted in [('riscv','3fe096173e3a63b2656c1fadf0a058a328fb5f1ee375be652176408856f897b8'),('nbf','627662f775f9c2645e5b5687a9df3bfaed25d42265e125a0386047ebe1daad4b')]:
   raw=gzip.decompress((closure/('advisory-prog.'+ext+'.gz')).read_bytes());assert hashlib.sha256(raw).hexdigest()==wanted;(out/('advisory-prog.'+ext)).write_bytes(raw)
  programs['advisory']={k:bind(out/('advisory-prog.'+ext)) for k,ext in [('elf','riscv'),('nbf','nbf')]}
  for kind in programs:
   for ext in ('riscv','nbf'):(out/(kind+'-prog.'+ext+'.gz')).write_bytes(gzip.compress((out/(kind+'-prog.'+ext)).read_bytes(),mtime=0))
  assert before==[bind(p) for p in inputs]
  record.update(state='PASS-fresh1280-integrity-accepted-flags-CRT-and-byteidentical-cold08-preparation-only',programs=programs,actual_gcc_argv=actual,nbf_script=bind(nbf_script),cold08_fixture=bind(fixture),cold08_source=f['source'],cold08_capacity_guard='nonzero I/D capacities only',accepted_compiler_comment_match=True,resources=check())
 except BaseException as e:record.update(state='FAIL-preserved-no-retry',error=repr(e));raise
 finally:(out/'program-proof.json').write_text(json.dumps(record,indent=2)+'\n');print(record['state'],flush=True)

if __name__=='__main__':main()
