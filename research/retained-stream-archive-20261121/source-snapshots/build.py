#!/usr/bin/env python3
"""Crosscompile one physical ELF and independently verify every NBF file byte."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

import generate

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
INSTALL=Path('/home/coyang/zynq-parrot/install')
MAGIC=0xc640000000000000
BASE=0x80000000


def bind(path):
    path=Path(path).resolve();data=path.read_bytes();return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def require(value,message):
    if not value:raise ValueError(message)


def segments(path):
    raw=Path(path).read_bytes();require(raw[:6]==b'\x7fELF\x02\x01','ELF64LE')
    off=struct.unpack_from('<Q',raw,32)[0];size,count=struct.unpack_from('<HH',raw,54)
    result=[]
    for n in range(count):
        kind,flags,offset,va,pa,filesz,memsz,alignment=struct.unpack_from('<IIQQQQQQ',raw,off+n*size)
        if kind==1:
            require(va==pa and BASE<=pa and pa+memsz<=BASE+46*1024*1024,'physical ELF46MiB bounds')
            result.append(dict(address=pa,data=raw[offset:offset+filesz],memsz=memsz,flags=flags))
    require(result,'PT_LOAD segments');return result


def image_from_elf(path):
    image={}
    for segment in segments(path):
        for n,byte in enumerate(segment['data']):
            addr=segment['address']+n
            require(addr not in image or image[addr]==byte,'overlapping ELF input differs');image[addr]=byte
    return image


def decode_nbf(path):
    image={};maximum=BASE;count=0
    for line in Path(path).read_text().splitlines():
        fields=line.split('_');require(len(fields)==3,'NBF record fields')
        op,address,value=(int(part,16) for part in fields)
        if op<=3 and address>=BASE:
            length=1<<op;require(address+length<=BASE+46*1024*1024,'actual NBF write tail bound')
            maximum=max(maximum,address+length);count+=1
            for n in range(length):image[address+n]=(value>>(8*n))&255
    return image,dict(write_records=count,maximum_write_end_exclusive=hex(maximum),allocation_bytes=46*1024*1024)


def verify_coverage(elf,nbf,config_address,config_value):
    # Independent converter readback: no use of its parsed mem dictionary.
    actual,bound=decode_nbf(nbf);missing=[];wrong=[];zero=0;total=0
    for segment in segments(elf):
        for n,byte in enumerate(segment['data']):
            address=segment['address']+n
            if config_address<=address<config_address+8:byte=(config_value>>(8*(address-config_address)))&255
            total+=1;zero+=byte==0
            if address not in actual:missing.append(address)
            elif actual[address]!=byte:wrong.append(address)
    require(not missing and not wrong,'file-backed NBF coverage missing=%d wrong=%d'%(len(missing),len(wrong)))
    return dict(file_bytes=total,file_zero_bytes=zero,missing_bytes=0,wrong_bytes=0,load_bound=bound,
                declared_input=dict(address=hex(config_address),bytes=8,value=hex(config_value)))


def verify_no_store(raw):
    require(len(raw)%4==0,'D phase32-bit instruction alignment')
    loads=0;hints=0
    for offset in range(0,len(raw),4):
        instruction=struct.unpack_from('<I',raw,offset)[0];opcode=instruction&127;rd=(instruction>>7)&31
        require(instruction&3==3,'compressed instruction in no-store D phase')
        require(opcode not in (0x23,0x2f),'store/atomic in protected D phase')
        require(opcode not in (0x6f,0x67) or rd==0,'call in protected D phase')
        require(not(opcode==15 and ((instruction>>12)&7)==1),'fenceI in protected phase')
        if opcode==3:
            require(((instruction>>12)&7)==3 and ((instruction>>15)&31)==6,'only target LD via t1 allowed')
            loads+=1
        if opcode==0x73:
            csr=instruction>>20;funct3=(instruction>>12)&7;rs1=(instruction>>15)&31
            require(csr in (0x5c2,0x9c0),'unexpected CSR in protected phase')
            if csr==0x5c2:require(funct3==2 and rs1==0,'no control write during captured-state interval')
            if csr==0x9c0 and funct3==1:hints+=1
    require(loads==1 and hints==1,'one looped target load/hint instruction required')
    return dict(instructions=len(raw)//4,store_instructions=0,atomic_instructions=0,call_instructions=0,
                target_load_instructions=loads,direct_hint_instructions=hints,scope='all lexical instructions and reachable success CFG between populate_begin and verified')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--max-lines',default=64,type=int);parser.add_argument('--max-sets',default=64,type=int)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    generated,functions=generate.text(args.max_lines,args.max_sets);inc=out/'capacity_targets.inc';inc.write_text(generated)
    tools={name:INSTALL/'bin'/('riscv64-unknown-elf-'+name) for name in ('gcc','nm','objdump')}
    elf=out/'retained_capacity_test.elf'
    sources=[HERE/'retained_capacity_test.c',HERE/'retained_capacity.S',HERE/'generate.py',Path(__file__).resolve(),inc]
    before=[bind(path) for path in sources]
    command=[str(tools['gcc']),'-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'software/include'),'-I'+str(out),
        '-I'+str(INSTALL/'riscv64-unknown-elf/include'),'--specs='+str(INSTALL/'riscv64-unknown-elf/lib/dramfs.specs'),
        '--specs='+str(INSTALL/'riscv64-unknown-elf/lib/perch.specs'),'-DBP_FPGA_PROGRAM=1','-DNUM_THREADS=2','-DBP_NUM_THREADS=2','-DBP_NUM_CONTEXTS=4',
        '-DCAP_MAX_LINES='+str(args.max_lines),'-DCAP_MAX_SETS='+str(args.max_sets),'-DCAP_CODE_FUNCTIONS='+str(functions),
        '-o',str(elf),str(sources[0]),str(sources[1])]
    with (out/'compile.log').open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
    nm=subprocess.check_output([str(tools['nm']),'-n','-S',str(elf)],text=True);(out/'symbols.txt').write_text(nm)
    symbols={}
    for row in nm.splitlines():
        fields=row.split()
        if len(fields)==4:symbols[fields[3]]=dict(address=int(fields[0],16),size=int(fields[1],16))
        elif len(fields)==3:symbols[fields[2]]=dict(address=int(fields[0],16),size=0)
    image=image_from_elf(elf)
    def memory(address,size):return bytes(image[address+n] for n in range(size))
    data=symbols['retained_capacity_data_base']['address'];code=symbols['retained_capacity_code_base']['address'];config=symbols['retained_capacity_config']['address']
    require(data%(64*args.max_sets)==code%(64*args.max_sets)==0,'set0 bases aligned')
    require(symbols['retained_capacity_data_end']['address']-data==64*args.max_lines,'full data size')
    for n in range(args.max_lines):require(memory(data+64*n,64)==struct.pack('<8Q',*generate.data_words(n)),'independent analytic D payload')
    for n in range(functions):
        symbol=symbols['retained_capacity_code_'+str(n)]
        require(symbol['address']==code+192*n and symbol['size']==64,'full code64/guarded stride')
        require(memory(code+192*n,64)==struct.pack('<8Q',*generate.code_words(n)),'all16 linked code instructions')
        require(memory(code+192*n+64,128)==bytes(128),'zero guard bytes')
    d_begin=symbols['retained_capacity_d_populate_begin']['address'];d_end=symbols['retained_capacity_d_verified']['address']
    no_store=verify_no_store(memory(d_begin,d_end-d_begin))
    disasm=subprocess.check_output([str(tools['objdump']),'-d',str(elf)],text=True);(out/'disassembly.txt').write_text(disasm)
    converter=ROOT/'import/black-parrot/bp_common/software/py/nbf.py';cases={}
    for role,value in (('d-enabled',MAGIC|2),('d-off',MAGIC),('i-enabled',MAGIC|3),('i-off',MAGIC|1)):
        case=out/role;case.mkdir();expected=dict(image)
        for n in range(8):expected[config+n]=(value>>(8*n))&255
        mem=case/'prog.mem'
        with mem.open('w') as stream:
            previous=None
            for addr,byte in sorted(expected.items()):
                if previous is None or addr!=previous+1:stream.write('@%08x\n'%(addr-BASE))
                stream.write('%02x\n'%byte);previous=addr
        nbf=case/'prog.nbf';nbf_command=[sys.executable,str(converter),'--skip_zeros','--keep_mem_zeros','--config','--mem',str(mem),'--ncpus','1']
        with nbf.open('w') as stream:subprocess.run(nbf_command,stdout=stream,check=True,timeout=60)
        coverage=verify_coverage(elf,nbf,config,value)
        cases[role]=dict(input_word=hex(value),mem=bind(mem),nbf=bind(nbf),command=nbf_command,coverage=coverage)
    require(before==[bind(path) for path in sources],'source changed during compile')
    report=dict(state='PASS crosscompile/static no-store/all-linked-word/NBF-zero-coverage; model runtime pending',
        sources=before,compiler=bind(tools['gcc']),compile_command=command,elf=bind(elf),symbols=symbols,
        max_lines=args.max_lines,max_sets=args.max_sets,code_functions=functions,data_base=data,code_base=code,code_stride=192,
        no_store=no_store,cases=cases,converter=bind(converter),same_physical_and_simulation_ELF=True,debug_start=False,
        limits='No board/synth; no capacity beyond actual configured-model gate; role input changes only one declared data word.')
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'manifest.json')


if __name__=='__main__':main()
