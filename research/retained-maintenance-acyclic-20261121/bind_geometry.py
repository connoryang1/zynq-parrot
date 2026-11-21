#!/usr/bin/env python3
"""Bind static L2 inheritance to actual r2 and combined generated model RAMs."""
import gzip
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'testing/rtl/uce-maintenance'))
from run_endpoint import bind


def require(ok,message):
    if not ok:raise ValueError(message)


def inspect(directory,sha):
    session=json.loads((directory/'session.json').read_text())
    require(session['model']['sha256']==sha and bind(session['model']['path'])['sha256']==sha,'exact closed model')
    obj=directory/'verilator/obj_dir'
    selector=directory/'verilator/bsg_blackparrot_pkg.sv'
    require(re.search(r'bp_cfg_gp\s*=\s*e_bp_unicore_zynqparrot_prefetch16k_cfg\s*;',selector.read_text()),'actual STATIC selector')
    compiled_path=Path(session['actual_source_list']['path']);compiled=json.loads(compiled_path.read_text())['sources']
    sources=[]
    for suffix in ('cosim/black-parrot-example/v/bp_common_pkg.sv',
                   'import/black-parrot/bp_common/src/include/bp_common_aviary_cfg_pkgdef.svh',
                   'import/black-parrot/bp_common/src/include/bp_common_aviary_defines.svh',
                   'import/black-parrot/bp_me/src/v/dev/bp_me_cache_slice.sv'):
        matches=[record for path,record in compiled.items() if path.endswith('/'+suffix)]
        require(len(matches)==1,'one actual consumed geometry source')
        record=bind(matches[0]['path']);require(record['sha256']==matches[0]['sha256'],'compiled geometry source drift')
        require(record['sha256']==bind(ROOT/suffix)['sha256'],'r2/combined geometry source differs')
        sources.append(record)
    root_header=obj/'Vbsg_nonsynth_zynq_testbench___024root.h'
    caches=re.findall(r'^\s*(\w+)\*\s+[^\n]*__DOT__l2s__DOT__bank__BRA__(\d+)__KET____DOT__cache;',root_header.read_text(),re.M)
    require([int(index) for _,index in caches]==[0,1] and len({kind for kind,_ in caches})==1,'exactly two actual L2 cache banks')
    cache_header=obj/(caches[0][0]+'.h');text=cache_header.read_text()
    require('CData/*5:0*/ __PVT__tag_mem_addr_li;' in text and 'CData/*1:0*/ __PVT__tag_hit_v;' in text,'actual64-set/two-way tag interface')
    memories=re.findall(r'^\s*(\w+)\*\s+__PVT__data_mem__DOT__synth__DOT__nz__DOT__bk__BRA__(\d+)__KET____DOT__mem_1rw_sync;',text,re.M)
    require([int(index) for _,index in memories]==list(range(16)) and len({kind for kind,_ in memories})==1,'actual16 byte RAMs per bank')
    memory_header=obj/(memories[0][0]+'.h')
    require('VlUnpacked<CData/*7:0*/, 512> __PVT__synth__DOT__nz__DOT__mem;' in memory_header.read_text(),'actual512x8b byte RAM')
    return dict(model=session['model'],selector=bind(selector),compiled_sources=bind(compiled_path),geometry_sources=sources,
                generated_headers=[bind(path) for path in (root_header,cache_header,memory_header)],
                l2=dict(slices=1,banks=2,sets_per_bank=64,ways=2,line_bytes=64,data_bytes_per_bank=16*512,total_bytes=2*16*512),
                elaboration_checks='two actual cachebank instances;64-entry set address/two-way tag vector;16 actual512x8b data RAMs per bank'),[selector,root_header,cache_header,memory_header]


def main():
    out=HERE/'geometry-supplement001';out.mkdir(exist_ok=False)
    models=[('original-r2',Path('/home/coyang/fpga-artifacts/context-resume/native1280-observe1-r2-20261121/full01'),
             'bdc8b908f55fbdb6e5b9dce22d8588cc163020fff74a44eda8a83a451a1ad8cf'),
            ('combined',Path('/home/coyang/fpga-artifacts/context-resume/retained-maintenance-acyclic-20261121/full01'),
             'ad51327bc6caee899b606ffd5fa80c654954d417a248614fcfab93e47a4a46d2')]
    facts={};copies=[]
    for label,directory,sha in models:
        facts[label],paths=inspect(directory,sha)
        for path in paths:
            target=out/label/(path.name+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(gzip.compress(path.read_bytes(),mtime=0));copies.append(dict(original=bind(path),snapshot=bind(target)))
    for record in facts['combined']['geometry_sources']:
        source=Path(record['path']);target=out/'sources'/(str(source.relative_to(ROOT))+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(gzip.compress(source.read_bytes(),mtime=0));copies.append(dict(original=bind(source),snapshot=bind(target)))
    result=dict(state='PASS source inheritance and actual generated-model L2 geometry both16KiB STATIC; no model pooling',
                models=facts,source_inheritance=['STATIC prefetch16k enum7 selected','prefetch cfg overrides L2banks2',
                   'prefetch16k overrides L2sets64','default L2assoc2/block512b preserved','one slice inherited from unicore cfg'],
                compact_snapshots=copies,combined_full_proof=bind(HERE/'closed-full001/manifest.json'),auditor=bind(__file__),
                limitations='Elaboration corroboration only, not FPGA route/traffic/performance. Original bdc/e109 per-address1280 fixture shares thisSTATIC16KiB L2; old ef0 native application pair uses a distinctCUSTOM model and is not pooled or revalidated here.')
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'manifest.json')


if __name__=='__main__':main()
