#!/usr/bin/env python3
"""Read-only source/closed-report audit; no compiler, FST reader or hardware."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

MAIN=Path('/home/coyang/zynq-parrot-linux-capacity')
SOURCE=Path('/home/coyang/zp-retained256-source-20261122')
TOP='eb7d390134a0025331a2366a979a774263b146d5'
BP='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c'
SUB='f6ce99ea7ebdcb97a46f73c296505071e9fb22ab'
HERE=Path(__file__).resolve().parent


def bind(path):
    path=Path(path);data=path.read_bytes()
    return dict(path=str(path.resolve()),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def git_file(repo,commit,name,ranges):
    marker=repo/'.git';assert marker.is_file()
    admin=Path(marker.read_text().strip().split(': ',1)[1])
    if not admin.is_absolute():admin=(repo/admin).resolve()
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_DIR=str(admin),GIT_WORK_TREE=str(repo))
    data=subprocess.check_output(['git','show',commit+':'+name],cwd=repo,env=env,timeout=30)
    text=data.decode().splitlines()
    return dict(repo=str(repo),commit=commit,path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                excerpts=[dict(first_line=a,last_line=b,text='\n'.join(text[a-1:b])) for a,b in ranges])


def executable_csr_scan(record):
    assert bind(record['path'])==record
    data=Path(record['path']).read_bytes();assert data[:6]==b'\x7fELF\x02\x01'
    off=struct.unpack_from('<Q',data,40)[0];entry,count,strings=struct.unpack_from('<HHH',data,58)
    sections=[];candidates=[]
    for i in range(count):
        sh=struct.unpack_from('<IIQQQQIIQQ',data,off+i*entry)
        kind,flags,address,fileoff,size=sh[1:6]
        if kind!=1 or not flags&4:continue
        assert fileoff+size<=len(data)
        sections.append(dict(index=i,address=address,file_offset=fileoff,bytes=size))
        for j in range(0,size-3,2):
            word=struct.unpack_from('<I',data,fileoff+j)[0]
            if word&127==0x73 and (word>>12)&7 in (1,2,3,5,6,7) and (word>>20)&4095 in (0x805,0x806,0x807):
                candidates.append(dict(address=address+j,word=word,csr=(word>>20)&4095))
    assert sections
    return dict(elf=record,executable_sections=sections,scanned_bytes=sum(x['bytes'] for x in sections),
                csr_805_806_807_candidates=candidates,
                method='Every2-byte boundary of every SHF_EXECINSTR PROGBITS section; valid CSR funct3=1,2,3,5,6,7. No disassembly/reachability assumption. No other firmware/DSO claim.')


def main():
    sources=[
        git_file(SOURCE,TOP,'cosim/black-parrot-example/v/top_zynq.sv',[(773,793)]),
        git_file(SOURCE/'import/black-parrot-subsystems',SUB,'blackparrot/v/bp_axi_top.sv',[(10,22),(184,196)]),
        git_file(SOURCE/'import/black-parrot',BP,'bp_top/src/v/bp_processor.sv',[(12,23),(311,325)]),
        git_file(SOURCE/'import/black-parrot',BP,'bp_top/src/v/bp_unicore.sv',[(25,36),(129,144)]),
        git_file(SOURCE/'import/black-parrot',BP,'bp_top/src/v/bp_unicore_lite.sv',[(8,18),(274,285)]),
        git_file(SOURCE/'import/black-parrot',BP,'bp_top/src/v/bp_core_minimal.sv',[(17,26),(191,272)]),
        git_file(SOURCE/'import/black-parrot',BP,'bp_be/src/v/bp_be_calculator/bp_be_csr.sv',[(210,218),(578,584),(1075,1086)]),
        git_file(SOURCE,TOP,'cosim/mk/Makefile.verilator',[(79,89)]),
        git_file(SOURCE,TOP,'cosim/tcl/vivado-utils.tcl',[(139,174)])]
    manifests={
        'COST':MAIN/'research/retained-trigger-accounting-20261121/prepared-cost01/manifest.json',
        'kernel29':MAIN/'research/retained-control-kernel29-20261121/package-manifest.json',
        'integrity-cold08':Path('/home/coyang/fpga-artifacts/context-resume/retained-dense-fullcore-20261121/program02/program-proof.json'),
        'capacity':Path('/home/coyang/fpga-artifacts/context-resume/retained-capacity1792-fixtures-20261121/preparation01/build01/manifest.json')}
    docs={k:json.loads(p.read_text()) for k,p in manifests.items()}
    scans={}
    for name,value in docs['COST']['programs'].items():scans['COST-'+name]=executable_csr_scan(value['elf'])
    scans['kernel29']=executable_csr_scan(docs['kernel29']['stripped_elf'])
    for name,value in docs['integrity-cold08']['programs'].items():scans[name]=executable_csr_scan(value['elf'])
    scans['capacity']=executable_csr_scan(docs['capacity']['elf'])
    assert all(not s['csr_805_806_807_candidates'] for s in scans.values())
    report=Path('/home/coyang/fpga-artifacts/context-resume/native1792-canonical-r7-preparation-20261121/read-optimized-hierarchy01')
    counts={}
    for line in (report/'primitive-counts.tsv').read_text().splitlines():
        fields=line.split('\t')
        if fields[0]=='trace_named':counts[fields[2]]=int(fields[3])
    luts=sum(v for k,v in counts.items() if k.startswith('LUT'))
    assert counts['RAMB36E1']==2 and counts['FDRE']==54 and luts==53
    memories=[line for line in (report/'primitive-name-samples.tsv').read_text().splitlines() if line.startswith('trace_named\tall\tRAMB36E1\t')]
    assert len(memories)==2 and all('gen_cache_miss_trace.' in row for row in memories)
    software=[]
    for row in docs['COST']['sources']:
        if row['snapshot']['path'].endswith(('.c','.h')) and 'test_' not in Path(row['snapshot']['path']).name:
            assert bind(row['snapshot']['path'])==row['snapshot'];software.append(row['snapshot'])
    for row in docs['integrity-cold08']['sources']:
        if row['path'].endswith(('.c','.h')):assert bind(row['path'])==row;software.append(row)
    for row in docs['capacity']['sources']:
        if row['path'].endswith(('.c','.S')):assert bind(row['path'])==row;software.append(row)
    software += [bind(MAIN/'research/retained-control-kernel29-20261121/source/kernel/sys.c'),bind(MAIN/'linux-tests/kernel-patches/0029-blackparrot-retained-control.patch')]
    q=dict(state='CLOSED read-only cache-miss-recorder opportunity audit; no implementation or fit claim',
        source_bindings=sources,software_source_bindings=software,software_manifests={k:bind(p) for k,p in manifests.items()},executable_scans=scans,
        actual_closed_primitive_evidence=dict(files=[bind(report/n) for n in ('primitive-counts.tsv','primitive-name-samples.tsv','query.tcl','session.json')],trace_named_primitives=counts,raw_LUTs=luts,raw_FFs=54,RAMB36E1=2,exact_memory_samples=memories),
        limits='Mapped existing diagnostic trace cost only; removing it is untested. No additive fit/placement/timing savings, larger capacity acceptance, application result, all-firmware/DSO reachability claim or trace-profile equivalence.')
    out=HERE/'audit.json'
    with out.open('x') as f:json.dump(q,f,indent=2);f.write('\n')
    print(out)


if __name__=='__main__':main()
