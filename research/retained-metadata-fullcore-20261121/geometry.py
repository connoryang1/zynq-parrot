#!/usr/bin/env python3
"""Actual closed-FST parameter corroboration, no target execution or geometry inference."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import threading

EXPECTED={'num_threads_p':2,'num_contexts_p':4,'icache_sets_p':64,'icache_assoc_p':8,'icache_block_width_p':512,
          'dcache_sets_p':64,'dcache_assoc_p':8,'dcache_block_width_p':512,'l2_banks_p':2,'l2_sets_p':64,
          'l2_assoc_p':2,'l2_block_width_p':512,'retained_store.storage.i_lines_p':1280,
          'retained_store.storage.d_lines_p':1280,'retained_store.storage.sets_p':256,
          'retained_store.storage.epoch_width_p':8}

def bind(p):
    p=Path(p).resolve();h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())

def parse(lines):
    handles={};values={};seen=set();ended=False;interval=None;last=None
    for line in lines:
        parts=line.rstrip('\n').split('\t')
        if parts[0]=='#FST':
            if interval is not None or len(parts)!=4 or int(parts[2])<=int(parts[1]):raise ValueError('FST interval')
            interval=parts[1:]
        elif parts[0]=='#SIGNAL':
            if ended or len(parts)!=5:raise ValueError('signal frame')
            _,key,width,handle,name=parts
            if key not in EXPECTED or key in seen or int(width)!=32 or not name.endswith('.unicore_lite.'+key):
                raise ValueError('exact parameter path/width')
            handles.setdefault(int(handle),[]).append(key);seen.add(key)
        elif parts[0]=='#END':
            if ended:raise ValueError('duplicate EOF')
            ended=True
        else:
            if ended or len(parts)!=3 or seen!=set(EXPECTED):raise ValueError('parameter event schema')
            t,handle=int(parts[0]),int(parts[1]);bits=parts[2]
            if last is not None and t<last:raise ValueError('time order')
            last=t
            if handle not in handles or len(bits)!=32 or set(bits)-set('01'):raise ValueError('unknown parameter')
            v=int(bits,2)
            for key in handles[handle]:
                if v!=EXPECTED[key]:raise ValueError('actual parameter differs '+key)
                values[key]=v
    if not ended or interval is None or values!=EXPECTED:raise ValueError('incomplete actual parameters/EOF')
    return dict(values=values,interval=interval,clean_eof=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('fst','reader','out'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(exist_ok=False);before=bind(a.fst)
    selection=a.out/'selection.tsv';selection.write_text(''.join(k+'\tunicore_lite.'+k+'\n' for k in EXPECTED))
    cmd=list(map(str,(a.reader.resolve(),a.fst.resolve(),selection.resolve())))
    with (a.out/'reader.stderr').open('wb') as error,(a.out/'events.tsv').open('w') as saved:
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=error,text=True)
        timer=threading.Timer(600,p.kill);timer.daemon=True;timer.start()
        def lines():
            for line in p.stdout:saved.write(line);yield line
        try:
            facts=parse(lines())
            if p.wait(timeout=30)!=0:raise ValueError('reader failed')
        except BaseException:p.kill();p.wait();raise
        finally:timer.cancel()
    if bind(a.fst)!=before:raise ValueError('closed FST changed')
    result=dict(state='PASS actual closedFST2resident4logical-L1I32K-L1D32K-L2two-bank16K-retained1280sets256epoch8',facts=facts,
                bindings=dict(fst=before,reader=bind(a.reader),auditor=bind(__file__),selection=bind(selection),events=bind(a.out/'events.tsv')),
                scope='Elaborated parameter corroboration only; no fit/FPGA/capacity/performance claim.')
    (a.out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
