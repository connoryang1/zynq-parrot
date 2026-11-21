#!/usr/bin/env python3
"""Read CLOSED FST constants plus exact generated packages; never executes models."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
OLD=ROOT/'research/retained-system-geometry-20261121/full-system1280-native0-03'
NEW=Path('/home/coyang/fpga-artifacts/context-resume/retained-maintenance-acyclic-20261121/full01')
READER=ROOT/'research/retained-system-geometry-20261121/reader/fst_events'
TOP='TOP.bsg_nonsynth_zynq_testbench.dut.top_fpga_inst'


def bind(path):
    p=Path(path).resolve();h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def constants(text,expected):
    mapping={};seen={};ended=False
    for line in text.splitlines():
        if ended:raise ValueError('data after EOF')
        fields=line.split('\t')
        if fields[0]=='#FST':continue
        if fields[0]=='#SIGNAL':
            _,key,width,handle,path=fields
            if key not in expected or path!=expected[key] or int(width)!=32:raise ValueError('wrong parameter declaration')
            mapping.setdefault(int(handle),[]).append(key)
        elif fields==['#END']:ended=True
        else:
            tick,handle,bits=fields;handle=int(handle)
            if handle not in mapping or len(bits)!=32 or set(bits)-set('01'):raise ValueError('unknown constant value')
            value=int(bits,2)
            for key in mapping[handle]:
                if key in seen and seen[key]!=value:raise ValueError('parameter changed during trace')
                seen[key]=value
    if not ended or set(seen)!=set(expected):raise ValueError('missing constant/clean EOF')
    return seen


def summary(values,banks):
    if values['l2_slices_p']!=1 or len(banks)!=values['l2_banks_p']:raise ValueError('physical bank hierarchy count mismatch')
    if banks!=list(range(values['l2_banks_p'])):raise ValueError('noncontiguous physical banks')
    total=0
    for bank in banks:
        actual={n:values['bank%d.%s'%(bank,n)] for n in ('sets_p','ways_p','data_width_p','block_size_in_words_p')}
        if (actual['sets_p'],actual['ways_p'],actual['data_width_p']*actual['block_size_in_words_p']) != \
                (values['l2_sets_p'],values['l2_assoc_p'],values['l2_block_width_p']):raise ValueError('actual cache bank/top geometry mismatch')
        total+=actual['sets_p']*actual['ways_p']*actual['data_width_p']*actual['block_size_in_words_p']//8
    normal={side:values[side+'cache_sets_p']*values[side+'cache_assoc_p']*values[side+'cache_block_width_p']//8 for side in ('i','d')}
    return dict(L2_bytes=total,L2_banks=len(banks),L2_sets_per_bank=values['l2_sets_p'],
                L2_ways=values['l2_assoc_p'],line_bytes=values['l2_block_width_p']//8,ordinary_L1_bytes=normal)


def one(name,base,fst,expected_bytes):
    output=HERE/name;output.mkdir()
    listing=subprocess.check_output([str(READER),str(fst),'--list'],text=True,timeout=60)
    if not listing.rstrip().endswith('#END'):raise ValueError('hierarchy not closed')
    rows=[l.split('\t') for l in listing.splitlines() if l.startswith('#VAR\t')]
    expected={n:TOP+'.'+n for n in ('l2_slices_p','l2_banks_p','l2_sets_p','l2_assoc_p','l2_block_width_p',
               'icache_sets_p','icache_assoc_p','icache_block_width_p','dcache_sets_p','dcache_assoc_p','dcache_block_width_p')}
    bank_prefix=TOP+'.blackparrot.processor.u.unicore.slices[0].l2s.bank['
    pattern=re.compile(re.escape(bank_prefix)+r'(\d+)\]\.cache\.(sets_p|ways_p|data_width_p|block_size_in_words_p)$')
    banks=set()
    for row in rows:
        m=pattern.fullmatch(row[3])
        if m:
            bank=int(m[1]);banks.add(bank);expected['bank%d.%s'%(bank,m[2])]=row[3]
    for key,path in expected.items():
        matches=[r for r in rows if r[3]==path]
        if len(matches)!=1 or int(matches[0][1])!=32:raise ValueError('missing actual geometry '+key)
    (output/'selection.tsv').write_text(''.join(k+'\t'+v+'\n' for k,v in expected.items()))
    command=[str(READER),str(fst),str(output/'selection.tsv')]
    text=subprocess.check_output(command,text=True,timeout=120)
    (output/'constant-events.tsv').write_text(text)
    values=constants(text,expected);geometry=summary(values,sorted(banks))
    if geometry['L2_bytes']!=expected_bytes or geometry['ordinary_L1_bytes']!={'i':32768,'d':32768}:raise ValueError('unexpected observed geometry')
    ver=base/('design/verilator' if name=='old-native' else 'verilator')
    sources={}
    for source in (ver/'bsg_blackparrot_pkg.sv',ver/'obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat',base/'actual-source-list.json'):
        sources[source.name]=bind(source)
        shutil.copy2(source,output/source.name)
    pkg=(ver/'bsg_blackparrot_pkg.sv').read_text();command_text=(ver/'obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat').read_text()
    if name=='old-native':
        if 'bp_cfg_gp = e_bp_custom_cfg;' not in pkg or '-DBP_CUSTOM_BASE_CFG=bp_unicore_zynqparrot_cfg_p' not in command_text or 'BP_ZYNQ_PREFETCH_TWO_BANKS' in command_text:raise ValueError('old custom-source provenance mismatch')
    elif 'bp_cfg_gp = e_bp_unicore_zynqparrot_prefetch16k_cfg;' not in pkg:raise ValueError('new static source provenance mismatch')
    return dict(trace=bind(fst),geometry=geometry,actual_parameter_values=values,physical_bank_indices=sorted(banks),
                command=command,constant_events=bind(output/'constant-events.tsv'),sources=sources)


def main():
    target=HERE/'geometry.json'
    if target.exists():raise ValueError('preserve existing proof')
    results={
      'old_native_ef0c_and_f1_clone':one('old-native',OLD,ROOT/'research/retained-natural-control-20261121/cohort-v3-01/mode0/trace.fst',4096),
      'new_static_prefetch16k':one('new-static',NEW,NEW/'advisory/trace.fst',16384)}
    out=dict(state='PASS-source-and-actual-FST-L2-geometry',results=results,reader=bind(READER),source=bind(__file__),
             scope='Geometry/provenance only; no model run, no cross-platform effect bridge, no functional/performance reclassification. Old ef0c/f1 is1bank4KiB; static prefetch16k is2banks16KiB; ordinary L1 I/D remain32KiB each.')
    target.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v['geometry'] for k,v in results.items()},indent=2))


if __name__=='__main__':main()
