#!/usr/bin/env python3
"""Packaging-only correction: preserve exact ELF and materialize its zero bytes.
No compile, model, target, synthesis or board execution.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
from prepare import bind,patch_mode,ROOT,HERE

EXPECTED='8c83ca26bb44b3d1eb294e568a65323fa75820c6aefa049baa4e6da4002525f4'


def segments(data):
 if data[:6]!=b'\x7fELF\x02\x01':raise ValueError('RV64 little-endian ELF required')
 offset=struct.unpack_from('<Q',data,32)[0];size,count=struct.unpack_from('<HH',data,54);result=[]
 for n in range(count):
  typ,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<II6Q',data,offset+n*size)
  if typ==1 and filesz:
   if va!=pa or not 0x80000000<=va<=va+filesz<=0x88000000:raise ValueError('unexpected load mapping')
   result.append((va,data[off:off+filesz]))
 return result


def writes(text):
 memory={};other=[]
 for line in text.splitlines():
  op,addr,value=line.split('_');op=int(op,16);addr=int(addr,16);value=int(value,16)
  if op in (2,3) and 0x80000000<=addr<0x88000000:
   size=4 if op==2 else 8
   if addr%size or value>=1<<(8*size):raise ValueError('invalid memory record')
   for n,byte in enumerate(value.to_bytes(size,'little')):
    if addr+n in memory:raise ValueError('duplicate memory byte')
    memory[addr+n]=byte
  else:other.append(line)
 return memory,other


def coverage(elf,text,override=None):
 memory,_=writes(text);expected={}
 for va,raw in segments(elf):
  for n,byte in enumerate(raw):
   if va+n in expected and expected[va+n]!=byte:raise ValueError('overlapping ELF segment conflict')
   expected[va+n]=byte
 if override:
  address,value=override
  for n,byte in enumerate(value.to_bytes(8,'little')):expected[address+n]=byte
 missing=[a for a in expected if a not in memory];wrong=[a for a in expected if a in memory and expected[a]!=memory[a]]
 return dict(file_backed_bytes=len(expected),zero_bytes=sum(v==0 for v in expected.values()),materialized_expected_bytes=sum(a in memory for a in expected),missing_bytes=len(missing),wrong_bytes=len(wrong),first_missing=[hex(a) for a in missing[:16]],first_wrong=[hex(a) for a in wrong[:16]],all_file_backed_bytes_exact=not missing and not wrong)


def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 oldpath=HERE/'prepared01/manifest.json';old=json.loads(oldpath.read_text())
 for key in ('elf','mem','nbf','nbf_tool'):
  if bind(old[key]['path'])!=old[key]:raise ValueError('original artifact changed')
 if old['elf']['sha256']!=EXPECTED:raise ValueError('not exact8c83ELF')
 for rel,expected in old['sources'].items():
  if bind(ROOT/rel)!=expected:raise ValueError('target source changed')
 record=dict(state='preparing-packaging-only-no-execution',source=bind(__file__),failed_preparation=bind(oldpath),original_preparer=bind(HERE/'prepare.py'),elf=old['elf'],mem=old['mem'],sources=old['sources'],nbf_tool=old['nbf_tool'],no_compile=True,no_target_execution=True,model_unchanged='ef0c7c4c9e84e97d4b71d6c80e6c118d5670411be3a3b16e5469cb89239b5f5d')
 cmd=[sys.executable,old['nbf_tool']['path'],'--skip_zeros','--keep_mem_zeros','--config','--debug','--mem',old['mem']['path'],'--ncpus','1'];record['command']=cmd
 try:
  r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60);(out/'nbf.stderr').write_text(r.stderr)
  if r.returncode:raise ValueError('NBF generator failed')
  text=r.stdout;(out/'prog.nbf').write_text(text);elf=Path(old['elf']['path']).read_bytes()
  record['base_coverage']=coverage(elf,text)
  if not record['base_coverage']['all_file_backed_bytes_exact']:raise ValueError('new NBF does not fully materialize file-backed ELF')
  oldtext=Path(old['nbf']['path']).read_text();record['failed_image_coverage']=coverage(elf,oldtext)
  memory,other=writes(text);oldmemory,oldother=writes(oldtext)
  if other!=oldother:raise ValueError('nonmemory NBF config/control records changed')
  if any(a not in memory or memory[a]!=byte for a,byte in oldmemory.items()):raise ValueError('previously materialized byte changed')
  record['same_nonmemory_records']=dict(count=len(other),byte_identical=True);record['initial9_config_records_identical']=text.splitlines()[:9]==oldtext.splitlines()[:9]
  address=old['symbols']['resume_retained_control']['address'];patches={}
  for mode in (0,15):
   patched=patch_mode(text,address,mode);path=out/f'mode{mode}.nbf';path.write_text(patched);checked=coverage(elf,patched,(address,mode))
   if not checked['all_file_backed_bytes_exact']:raise ValueError('patched image coverage')
   patches[str(mode)]=dict(nbf=bind(path),coverage=checked)
  m0,_=writes((out/'mode0.nbf').read_text());m15,_=writes((out/'mode15.nbf').read_text());delta=[a for a in m0 if m0[a]!=m15[a]]
  if delta!=[address]:raise ValueError('mode pair differs outside one control word low byte')
  record.update(state='PASS-packaging-coverage-only-no-execution',nbf=bind(out/'prog.nbf'),mode_patches=patches,config_address=hex(address),between_modes_changed_bytes=[hex(a) for a in delta],unchanged_elf=bind(old['elf']['path'])==old['elf'],added_memory_bytes=len(memory)-len(oldmemory))
 except BaseException as e:record.update(state='FAIL-packaging-preflight-preserved',error=repr(e));raise
 finally:(out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n');print(out/'manifest.json',record['state'])

if __name__=='__main__':main()
