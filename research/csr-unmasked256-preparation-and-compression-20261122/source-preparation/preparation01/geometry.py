#!/usr/bin/env python3
"""Exact ordinary/retained geometry plus actual disabled recorder parameter."""
import argparse
import json
from pathlib import Path
import subprocess
import threading
from materialize import bind,require


def expected(lines):
    values={'num_threads_p':2,'num_contexts_p':4,'icache_sets_p':64,'icache_assoc_p':8,'icache_block_width_p':512,
            'dcache_sets_p':64,'dcache_assoc_p':8,'dcache_block_width_p':512,'l2_banks_p':2,'l2_sets_p':64,
            'l2_assoc_p':2,'l2_block_width_p':512,'retained_store.storage.i_lines_p':lines,
            'retained_store.storage.d_lines_p':lines,'retained_store.storage.sets_p':256,'retained_store.storage.epoch_width_p':8}
    widths={key:32 for key in values};values['core_minimal.cache_miss_trace_p']=0;widths['core_minimal.cache_miss_trace_p']=1
    return values,widths


def parse(stream,lines):
    wanted,widths=expected(lines);handles={};seen=set();values={};ended=False;interval=None;last=None
    for line in stream:
        parts=line.rstrip('\n').split('\t')
        if parts[0]=='#FST':
            require(interval is None and len(parts)==4 and int(parts[2])>int(parts[1]),'FST interval');interval=parts[1:]
        elif parts[0]=='#SIGNAL':
            require(not ended and len(parts)==5,'signal frame')
            _,key,width,handle,name=parts
            require(key in wanted and key not in seen and int(width)==widths[key] and name.endswith('.unicore_lite.'+key),'literal parameter name/width')
            handles.setdefault(int(handle),[]).append(key);seen.add(key)
        elif parts[0]=='#END':require(not ended,'duplicate EOF');ended=True
        else:
            require(not ended and len(parts)==3 and seen==set(wanted),'parameter event schema')
            t,handle=int(parts[0]),int(parts[1]);bits=parts[2]
            require(last is None or t>=last,'parameter time order');last=t
            require(handle in handles and set(bits)<=set('01'),'known parameter')
            for key in handles[handle]:
                require(len(bits)==widths[key] and int(bits,2)==wanted[key],'actual parameter differs '+key);values[key]=int(bits,2)
    require(ended and interval is not None and values==wanted,'all17 actual parameters and EOF')
    return dict(values=values,interval=interval,clean_eof=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('fst','reader','out'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--lines',type=int,required=True);a=ap.parse_args();require(1<=a.lines<=65535,'selected lines')
    a.out.mkdir(exist_ok=False);before=bind(a.fst);values,widths=expected(a.lines)
    selection=a.out/'selection.tsv';selection.write_text(''.join(key+'\tunicore_lite.'+key+'\n' for key in values))
    command=list(map(str,(a.reader.resolve(),a.fst.resolve(),selection.resolve())))
    with (a.out/'reader.stderr').open('wb') as err,(a.out/'events.tsv').open('w') as saved:
        p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=err,text=True)
        timer=threading.Timer(600,p.kill);timer.daemon=True;timer.start()
        def records():
            for row in p.stdout:saved.write(row);yield row
        try:facts=parse(records(),a.lines);require(p.wait(timeout=30)==0,'reader complete exit')
        except BaseException:p.kill();p.wait();raise
        finally:timer.cancel()
    require(bind(a.fst)==before,'closed FST unchanged')
    result=dict(state='PASS all17 actual selected-capacity/ordinary-geometry/trace0 parameters',facts=facts,
                bindings=dict(fst=before,reader=bind(a.reader),auditor=bind(__file__),selection=bind(selection),events=bind(a.out/'events.tsv')),
                scope='Elaborated parameters only, no area/fit/FPGA/application claim.')
    (a.out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
