#!/usr/bin/env python3
"""Use the frozen capacity builder unchanged; crosscompile only, never execute a target."""
import gzip
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=Path('/home/coyang/zynq-parrot-retained-observation')
FIXTURE=ROOT/'testing/rtl/retained-capacity-fixture'
OLD=Path('/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121/capacity1280-build01')
OUT=Path('/home/coyang/fpga-artifacts/context-resume/retained-capacity1792-fixtures-20261121/preparation01')
INSTALL=Path('/home/coyang/zynq-parrot/install')
LIMIT=32*1024*1024
def require(ok,message):
 if not ok:raise ValueError(message)
def bind(p):
 p=Path(p).resolve();r=p.read_bytes();return dict(path=str(p),bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def dump(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def total():return sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())
def run(argv,log,timeout=30,cwd=ROOT):
 with log.open('wb') as f:
  p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,cwd=cwd,start_new_session=True)
  start=time.monotonic()
  try:
   while p.poll() is None:
    require(total()<=LIMIT,'32MiB total output cap')
    if time.monotonic()-start>timeout:raise TimeoutError('bounded own compiler process')
    time.sleep(.1)
  except BaseException:
   os.killpg(p.pid,signal.SIGKILL);p.wait();raise
 require(p.returncode==0,'command failed: '+str(argv));return dict(argv=argv,returncode=p.returncode,log=bind(log))

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify-existing',action='store_true');args=parser.parse_args()
 require(shutil.disk_usage('/home/coyang').free>=3*1024**3+LIMIT,'3GiB reserve+32MiB output')
 require(OUT.is_dir() if args.verify_existing else not OUT.exists(),'fresh build or explicit closed-output verification only')
 if not args.verify_existing:OUT.mkdir(parents=True)
 old=json.loads((OLD/'manifest.json').read_text());frozen=[x for x in old['sources'] if not x['path'].endswith('capacity_targets.inc')]+[old['compiler'],old['converter']]
 for r in frozen:require(bind(r['path'])==r,'frozen original input '+r['path'])
 sources=OUT/'source'
 if not args.verify_existing:
  sources.mkdir()
  for r in frozen:
   if Path(r['path']).suffix in ('.c','.S','.py'):shutil.copyfile(r['path'],sources/Path(r['path']).name)
  shutil.copyfile(OLD/'manifest.json',sources/'old1280-manifest.json')
 gcc=str(INSTALL/'bin/riscv64-unknown-elf-gcc');tool_flags=['--specs='+str(INSTALL/'riscv64-unknown-elf/lib/dramfs.specs'),'--specs='+str(INSTALL/'riscv64-unknown-elf/lib/perch.specs')]
 tool_inputs=[]
 for name in ('dramfs.specs','perch.specs','dramfs.ld','dramfs_crt0.o','crtbegin.o','crtend.o','libc.a','libgloss_dramfs.a','libperch.a','libgcc.a'):
  p=Path(subprocess.check_output([gcc,*tool_flags,'-march=rv64gc','-mabi=lp64d','-print-file-name='+name],text=True).strip());require(p.is_file(),'resolved toolchain '+name);tool_inputs.append(bind(p))
 for n in ('gcc','nm','objdump','ld','as'):tool_inputs.append(bind(INSTALL/'bin'/('riscv64-unknown-elf-'+n)))
 preflight=dict(state='PREPARED only, crosscompile pending',original_manifest=bind(OLD/'manifest.json'),frozen_inputs=frozen,toolchain_inputs=tool_inputs,output_limit_bytes=LIMIT,reserve_bytes=3*1024**3)
 if args.verify_existing:require(json.loads((OUT/'preflight.json').read_text())==preflight,'original preflight unchanged')
 else:dump(OUT/'preflight.json',preflight)
 command=['/usr/bin/python3',str(FIXTURE/'build.py'),'--out',str(OUT/'build01'),'--max-lines','1792','--max-sets','256']
 receipt=(dict(argv=command,state='Existing frozen-builder static PASS manifest; original wrapper later failed supplemental startup-byte assertion',log=bind(OUT/'builder.log')) if args.verify_existing else run(command,OUT/'builder.log',timeout=320))
 build=OUT/'build01';new=json.loads((build/'manifest.json').read_text())
 expected=[s.replace(str(OLD),str(build)).replace('-DCAP_MAX_LINES=1280','-DCAP_MAX_LINES=1792').replace('-DCAP_CODE_FUNCTIONS=1280','-DCAP_CODE_FUNCTIONS=1792') for s in old['compile_command']]
 require(new['compile_command']==expected,'only capacity/functions/output changed in compiler command')
 trace=dict(argv=[gcc,'-###',*new['compile_command'][1:]],log=bind(OUT/'compiler-link-trace.log'),scope='existing compiler dry-run only') if args.verify_existing else run([gcc,'-###',*new['compile_command'][1:]],OUT/'compiler-link-trace.log')
 readelf=str(INSTALL/'bin/riscv64-unknown-elf-readelf');elfproof=dict(argv=[readelf,'-h','-l','-S',new['elf']['path']],log=bind(OUT/'readelf.log'),scope='existing read-only ELF inspection') if args.verify_existing else run([readelf,'-h','-l','-S',new['elf']['path']],OUT/'readelf.log')
 require(new['max_lines']==new['code_functions']==1792 and new['max_sets']==256 and new['code_stride']==192,'capacity only')
 require(new['code_base']==old['code_base'],'unchanged code-base placement rule')
 spec=importlib.util.spec_from_file_location('frozen_capacity_build',FIXTURE/'build.py');module=importlib.util.module_from_spec(spec)
 import sys;sys.path.insert(0,str(FIXTURE));spec.loader.exec_module(module)
 old_image=module.image_from_elf(old['elf']['path']);image=module.image_from_elf(new['elf']['path'])
 for index in range(1280):
  for n in range(192):require(old_image[old['code_base']+192*index+n]==image[new['code_base']+192*index+n],'old code/guards unchanged')
  for n in range(64):require(old_image[old['data_base']+64*index+n]==image[new['data_base']+64*index+n],'old analytic data unchanged')
 startup_end=min(old['symbols']['register_fini']['address'],new['symbols']['register_fini']['address'])
 def instructions(path):
  result={}
  for line in path.read_text().splitlines():
   m=re.match(r'\s*([a-f0-9]+):\s+([a-f0-9]+)\s+(.+)',line)
   if m and int(m[1],16)<startup_end:result[int(m[1],16)]=(m[2],m[3])
  return result
 before,after=instructions(OLD/'disassembly.txt'),instructions(build/'disassembly.txt')
 require(before.keys()==after.keys(),'startup instruction locations unchanged')
 differences=[]
 for address in before:
  if before[address][0]!=after[address][0]:
   a,b=before[address],after[address];op=a[1].split()[0]
   require(op==b[1].split()[0] and op in ('auipc','jal','j'),'startup only address-bearing instruction changes')
   require(re.findall(r'<([^>]+)>',a[1])==re.findall(r'<([^>]+)>',b[1]),'startup symbolic relocation target unchanged')
   require((int(a[0],16)&0xfff)==(int(b[0],16)&0xfff),'startup opcode/register unchanged')
   differences.append(dict(address=hex(address),old_encoding=a[0],new_encoding=b[0],old_disassembly=a[1],new_disassembly=b[1]))
 require(len(differences)==10,'exact startup relocation review count')
 pairs={};config=new['symbols']['retained_capacity_config']['address']
 for role in ('d-enabled','d-off','i-enabled'):
  r=new['cases'][role];coverage=r['coverage'];require(coverage['missing_bytes']==coverage['wrong_bytes']==0 and coverage['load_bound']['allocation_bytes']==46*1024*1024,'complete NBF46M verification')
  target_image,_=module.decode_nbf(r['nbf']['path']);pairs[role]=target_image
 require(all({a for a in pairs['d-off'] if pairs[role][a]!=pairs['d-off'][a]}=={config} for role in ('d-enabled','i-enabled')),'only declared config byte changes roles')
 symbol=new['symbols'];stack=dict(base=symbol['__stack_start']['address'],bytes_per_hart=symbol['__stack_size']['address'],conservative_four_context_end=symbol['__stack_start']['address']+4*symbol['__stack_size']['address'])
 require(stack['conservative_four_context_end']<=0x82e00000,'all four conservative stacks within46MiB')
 require(frozen==[bind(r['path']) for r in frozen] and tool_inputs==[bind(r['path']) for r in tool_inputs],'source/toolchain unchanged')
 allfiles=[bind(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='preparation-manifest.json']
 report=dict(state='PASS crosscompile/static preparation only; NO simulation/FPGA/board/runtime result',original_manifest=bind(OLD/'manifest.json'),frozen_inputs=frozen,toolchain_inputs=tool_inputs,commands=[receipt,trace,elfproof],
  max_lines=1792,sets=256,expected_positive_counter=dict(publications=1792,accepted_hits=1792,actual_L1_write_beats=14336),expected_d_off_positive_retained_counter=0,
  requested_roles={k:new['cases'][k] for k in ('d-enabled','d-off','i-enabled')},unrequested_i_off='Frozen builder also creates i-off; prepared only, not delivered/admitted/executed.',
  elf=new['elf'],manifest=bind(build/'manifest.json'),same_ELF_for_three_inputs=True,role_diff='Only config low byte at '+hex(config),source_pattern_prefix_code_data_unchanged=True,
  linked_startup_prefix=dict(begin='0x80000000',end_exclusive=hex(startup_end),byte_identical=False,unchanged_instruction_layout_and_operations=True,relocation_differences=differences),stack_bound=stack,inputs_and_outputs=allfiles,
  limits='Static collateral only. Full1792 payload correctness, observer exact1792/1792/14336 and D-off0 still require future scoped-model/physical gates. No bridge/allowlist/fit approval created.',source=bind(__file__))
 target=OUT/'preparation-manifest.json'
 if target.exists():
  old_report=json.loads(target.read_text())
  require(old_report['elf']==report['elf'] and old_report['requested_roles']==report['requested_roles'],'prepared binaries unchanged')
 dump(target,report);require(total()<=LIMIT,'final32MiB cap');print(str(target));print('bytes',total())

if __name__=='__main__':main()
