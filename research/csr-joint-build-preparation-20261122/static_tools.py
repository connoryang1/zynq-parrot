"""Source-only linked proof helpers; no target execution or import-time tools."""
from pathlib import Path
import struct
BASE=0x80000000


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


def symbols(text):
    result={}
    for line in text.splitlines():
        fields=line.split()
        if len(fields)==4:
            address,size,kind,name=fields
        elif len(fields)==3:
            address,kind,name=fields;size='0'
        else:continue
        if name.startswith('retained_'):
            require(name not in result,'unique fixture symbol '+name)
        result[name]=dict(address=int(address,16),size=int(size,16),kind=kind)
    return result


def sign(value,width):
    return value-(1<<width) if value&(1<<(width-1)) else value


def branch_offset(word):
    return sign(((word>>31)&1)<<12|((word>>7)&1)<<11|((word>>25)&63)<<5|((word>>8)&15)<<1,13)


def jump_offset(word):
    return sign(((word>>31)&1)<<20|((word>>12)&255)<<12|((word>>20)&1)<<11|((word>>21)&1023)<<1,21)


def writes_register(word):
    return (word&127) in (0x03,0x07,0x13,0x17,0x1b,0x33,0x37,0x3b,0x53,0x67,0x6f,0x73)


def verify_joint_cfg(image,syms,guard=lambda:None):
    """Separate extension: old no-call rule remains old. Inspect linked RV64 words."""
    def address(name):
        require(name in syms,'required linked symbol '+name)
        return syms[name]['address']
    start=address('retained_joint_capacity_region')
    end=start+syms['retained_joint_capacity_region']['size']
    begin=address('retained_capacity_i_populate_begin')
    populated=address('retained_capacity_joint_populated')
    verified=address('retained_capacity_joint_verified')
    call=address('retained_capacity_joint_call')
    dverify=address('retained_capacity_d_verify_begin')
    dend=address('retained_capacity_d_verified')
    require(start<begin<populated<call<dverify<dend<verified<end and end-start<=65536,'fixed region ordering/bound')
    require((end-start)%4==0,'full32-bit noRVC assembly function')
    words={pc:int.from_bytes(bytes(image[pc+n]for n in range(4)),'little')for pc in range(start,end,4)}
    require(all(word&3==3 for word in words.values()),'no compressed/zero instruction in region')
    require(all((word&127)in(0x03,0x0f,0x13,0x17,0x1b,0x23,0x33,0x37,0x3b,0x63,0x67,0x6f,0x73)
                for word in words.values()),'only declared integer assembly opcodes')
    graph={};calls=[];loads=[];hints=[];returns=[];checked_errors=[];timeout_results=[]
    for pc,word in words.items():
        guard();opcode=word&127;rd=(word>>7)&31;rs1=(word>>15)&31;funct3=(word>>12)&7
        if opcode==0x63:
            require(funct3 in (0,1,4,5,6,7),'legal conditional branch')
            successors=[pc+4,pc+branch_offset(word)]
        elif opcode==0x6f:
            require(rd==0,'no direct linked calls in joint region')
            successors=[pc+jump_offset(word)]
        elif opcode==0x67:
            require(funct3==0,'legal JALR')
            if pc==call:
                require(rd==1 and rs1==23 and word>>20==0,'only jalr ra,0(s7)')
                calls.append(pc);successors=[pc+4]
            else:
                require(rd==0 and rs1==1 and word>>20==0,'only ABI return outside target call')
                returns.append(pc);successors=[]
        else:successors=[pc+4]
        require(all(target in words for target in successors),'no unresolved/external direct CFG edge')
        graph[pc]=successors
        if not begin<=pc<verified:continue
        # Identify declared compare failures by their actual linked operands,
        # not by guessing which edges look like errors after linking.
        if opcode==0x63:
            rs2=(word>>20)&31;error_value=None
            if funct3==1 and (rs1,rs2)==(28,21):error_value=5
            if funct3==1 and (rs1,rs2)==(10,24):error_value=6
            if funct3==1 and (rs1,rs2)==(7,28):error_value=7
            previous=words.get(pc-4,0)
            cap_shift=(previous&127)==0x13 and ((previous>>12)&7)==5 and ((previous>>7)&31)==28 and ((previous>>15)&31)==7 and previous>>20==63
            if funct3==0 and (rs1,rs2)==(28,0) and cap_shift:error_value=5
            if error_value is not None:
                target=pc+branch_offset(word);first=words[target]
                require(target>verified and (first&0xfffff)==0x513 and sign(first>>20,12)==error_value,
                        'declared compare failure goes only to nonzero error result')
                checked_errors.append((pc,error_value))
        if (word&0xfffff)==0x513 and sign(word>>20,12)>0:
            nxt=words[pc+4]
            require((nxt&127)==0x6f and ((nxt>>7)&31)==0 and pc+4+jump_offset(nxt)>verified,
                    'timeout result exits, never enters verified')
            timeout_results.append(sign(word>>20,12))
        require(opcode not in (0x23,0x27,0x2f,0x0f),'no store/FPstore/AMO/fence in protected lexical body')
        require(not(writes_register(word) and rd==2),'no protected stack-pointer write')
        if opcode in (0x03,0x07):
            require(opcode==0x03 and funct3==3 and rs1==6 and rd==7 and word>>20==0
                    and dverify<pc<dend,'one target LD t2,0(t1) after D verify marker')
            loads.append(pc)
        if opcode==0x73:
            csr=word>>20
            if funct3==2 and rs1==0:
                require(csr in (0x5c2,0x7c0,0x9c0),'declared status reads only')
            else:
                require(funct3==1 and csr in (0x7c0,0x9c0) and pc<populated,'only population hints; no control write')
                hints.append((pc,csr))
    require(calls==[call] and len(loads)==1 and len(returns)==1,'exact one target-call/target-load/ABI-return site')
    require(sorted(csr for _,csr in hints)==[0x7c0,0x9c0],'exact one I and one D hint site')
    require(sorted(value for _,value in checked_errors)==[5,5,5,5,5,5,6,7]
            and sorted(timeout_results)==[1,2,3,4],'all declared control/cap/code/data/timeout failures checked')

    def reaches(seed,target):
        todo=[seed];seen=set()
        while todo:
            pc=todo.pop()
            if pc==target:return True
            if pc in seen:continue
            seen.add(pc);todo.extend(graph[pc])
        return False
    require(reaches(begin,verified),'structural success path reaches verified marker')
    # Successors leaving the protected region before its verified marker are
    # failure paths. A nonzero constant a0 must survive each to ABI return.
    escapes=[]
    for pc in range(begin,verified,4):
        for target in graph[pc]:
            if begin<=target<verified or target==verified:continue
            require(not reaches(target,verified),'failure path cannot reach verified marker')
            prior=words.get(pc-4,0)
            initial=sign(prior>>20,12) if (prior&0xfffff)==0x513 else None
            todo=[(target,initial)];seen=set();terminals=0
            while todo:
                at,value=todo.pop()
                if (at,value)in seen:continue
                seen.add((at,value));w=words[at]
                if writes_register(w) and (w>>7)&31==10:
                    value=sign(w>>20,12) if (w&0xfffff)==0x513 else None
                if not graph[at]:
                    require(value is not None and value>0,'failure exits retain explicit nonzero result')
                    terminals+=1
                else:
                    require(all(n>at for n in graph[at]),'error cleanup CFG strictly forward, no hidden loop')
                    todo.extend((n,value)for n in graph[at])
            require(terminals>0,'every error CFG reaches an ABI return')
            escapes.append(dict(from_pc=pc,to_pc=target))
    require(escapes,'explicit checked failure paths')
    return dict(state='PASS linked protected CFG static extension; no target execution',
                function_start=start,function_end=end,protected_begin=begin,verified=verified,
                protected_instructions=(verified-begin)//4,call_site=call,target_load_site=loads[0],
                hint_sites=hints,store_atomic_fence_control_writes=0,error_escapes=escapes,
                checked_compare_failures=checked_errors,timeout_results=timeout_results,
                limits='Target-call dynamic address and checked returns still require full execution/trace; generated callees separately checked exact16 instructions.')


def verify_payloads(elf,syms,generator,guard=lambda:None):
    raw=Path(elf).read_bytes()
    require(raw[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',raw,18)[0]==243,'actual ELF64LE RISC-V')
    image=image_from_elf(elf)
    def memory(address,size):return bytes(image[address+n]for n in range(size))
    data=syms['retained_capacity_data_base']['address'];code=syms['retained_capacity_code_base']['address']
    require(data%16384==code%16384==0,'unchanged64*256 set0 alignment')
    require(syms['retained_capacity_data_end']['address']-data==64*1792,'unchanged full D generated size')
    for index in range(1792):
        guard()
        require(memory(data+64*index,64)==struct.pack('<8Q',*generator.data_words(index)),'all independent D words')
        symbol=syms['retained_capacity_code_'+str(index)]
        require(symbol['address']==code+192*index and symbol['size']==64,'unchanged code stride/size')
        require(memory(symbol['address'],64)==struct.pack('<8Q',*generator.code_words(index)),'all linked16 target instructions')
        require(memory(symbol['address']+64,128)==bytes(128),'all128-byte zero guards')
    config=syms['retained_joint_capacity_config']
    require(config['size']==8 and memory(config['address'],8)==struct.pack('<Q',0xc641000000000000),'new single joint config word')
    cfg=verify_joint_cfg(image,syms,guard)
    return image,dict(state='PASS all1792 analytic full64B payloads/guards and protected static CFG; no runtime',
                      data_base=data,code_base=code,code_stride=192,max_lines=1792,max_sets=256,
                      code_functions=1792,i_lines=256,d_lines=256,sets=256,
                      linked_D_words=1792*8,linked_I_instructions=1792*16,zero_guard_bytes=1792*128,
                      ELF_machine=243,ELF_flags=struct.unpack_from('<I',raw,48)[0],
                      config=config['address'],static_CFG=cfg)
