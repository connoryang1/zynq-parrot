#!/usr/bin/env python3
"""Corroborate every counter transition/clock edge in a CLOSED actual-model FST."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import threading
from build_full import binding as complete_binding


def require(ok,message):
    if not ok:raise ValueError(message)


def bind(path):
    path=Path(path).resolve();h=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=h.hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('fst','reader','strict-proof','run-proof','out'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    initial=bind(a.fst);strict=json.loads(a.strict_proof.read_text());run=json.loads(a.run_proof.read_text())
    require(strict['accepted'] is True and strict['bindings']['fst']==initial,'accepted same-FST strict payload proof')
    require(run['state'].startswith('PASS complete scoped wholecore and actual GP0'),'actual GP0 read proof')
    for record in run['files']:require(complete_binding(record['path'])==record,'closed run artifact changed')
    prefix='retained_observe.counts.'
    selected={key:(prefix+key,width) for key,width in [('clk_i',2),('reset_i',1),('bp_reset_i',1),
        ('hit_i',2),('published_i',2),('write_beat_i',2),('hits_o',32),('published_o',32),('write_beats_o',32)]}
    selected.update({'i_clock':('unicore_lite.icache_uce.clk_i',1),'d_clock':('unicore_lite.dcache_uce.clk_i',1)})
    selection=a.out/'selection.tsv';selection.write_text(''.join(key+'\t'+suffix+'\n' for key,(suffix,_) in selected.items()))
    command=[str(a.reader.resolve()),str(a.fst.resolve()),str(selection.resolve())]
    handles={};widths={};values={};changes={};time=None;seen_reset=False;ended=False
    expected=[[0,0,0],[0,0,0]];transitions=[];edges=[0,0];reset_times=[]
    inputs=('hit_i','published_i','write_beat_i');outputs=('hits_o','published_o','write_beats_o')
    def sample(t,update):
        nonlocal seen_reset
        after=dict(values);after.update(update)
        def get(key,state):
            value=state.get(handles[key]);require(value is not None,'unknown counter signal '+key);return value
        if get('reset_i',after):
            if not seen_reset:reset_times.append(t)
            seen_reset=True
            for lane in range(2):expected[lane][:]=[0,0,0]
        elif seen_reset:
            before_clock=get('clk_i',values);after_clock=get('clk_i',after)
            for lane in range(2):
                if not before_clock&(1<<lane) and after_clock&(1<<lane):
                    edges[lane]+=1
                    if get('reset_i',values):expected[lane][:]=[0,0,0]
                    elif not get('bp_reset_i',values):
                        increment=[(get(key,values)>>lane)&1 for key in inputs]
                        for field,inc in enumerate(increment):expected[lane][field]=min(65535,expected[lane][field]+inc)
                        if any(increment):transitions.append(dict(time=t,lane='d' if lane else 'i',increment=increment,after=list(expected[lane])))
        if seen_reset:
            clock=get('clk_i',after)
            require(get('i_clock',after)==clock&1 and get('d_clock',after)==(clock>>1)&1,'actual UCE/counter edge mismatch')
            for field,key in enumerate(outputs):
                require(get(key,after)==expected[0][field]|(expected[1][field]<<16),'counter transition/reset mismatch '+key+' at '+str(t))
        values.update(update)
    with (a.out/'reader.stderr').open('w') as error,gzip.open(a.out/'selected-events.tsv.gz','wt') as saved:
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=error,text=True)
        timer=threading.Timer(180,process.kill);timer.daemon=True;timer.start()
        try:
            for line in process.stdout:
                saved.write(line);parts=line.rstrip('\n').split('\t')
                if parts[0]=='#FST':require(len(parts)==4 and int(parts[2])>int(parts[1]),'nonempty FST')
                elif parts[0]=='#SIGNAL':
                    require(time is None and len(parts)==5,'declaration ordering')
                    _,key,width,handle,name=parts;require(key in selected and key not in handles,'declared counter key')
                    suffix,wanted=selected[key];require(int(width)==wanted and (name==suffix or name.endswith('.'+suffix)),'counter signal width/path')
                    handles[key]=int(handle);widths[int(handle)]=int(width)
                elif parts[0]=='#END':ended=True
                else:
                    require(not ended and len(parts)==3 and set(handles)==set(selected),'complete selected event schema')
                    current,handle=int(parts[0]),int(parts[1]);bits=parts[2].lower()
                    require(handle in widths and len(bits)==widths[handle] and set(bits)<=set('01xz'),'counter event value')
                    require(time is None or current>=time,'monotonic FST time')
                    if time is not None and current!=time:sample(time,changes);changes={}
                    time=current;require(handle not in changes,'duplicate settled event');changes[handle]=None if set(bits)&set('xz') else int(bits,2)
            require(process.wait(timeout=30)==0 and ended and time is not None,'closed complete counter stream')
            sample(time,changes)
        except BaseException:process.kill();process.wait();raise
        finally:timer.cancel()
    require(seen_reset and all(edges),'counter reset and both actual clock domains observed')
    require(expected==[[1,1,8],[1,1,8]],'expected fulltop firsttouch counts')
    require(tuple(map(int,run['counter_values']))==(1,1,1,1,8,8),'actual host counts')
    for lane in ('i','d'):
        facts=strict['lanes'][lane]
        require(len(facts['publications'])==1 and len(facts['hits'])==1 and len(facts['bursts'])==1
                and len(facts['bursts'][0]['beats'])==8,'independent strict real-event counts')
    require(bind(a.fst)==initial,'FST changed during audit')
    report=dict(state='PASS actual counter transitions and GP0 values match strict real publication/hit/nonaborted full-L1 write proof',
        firsttouch_counts=dict(i=expected[0],d=expected[1]),field_order=['accepted_hits','published_insertions','retained_SRAM_write_beats'],
        observed_rising_edges=edges,external_reset_times=reset_times,nonzero_event_edges=transitions,
        bindings=dict(fst=initial,strict=bind(a.strict_proof),run=bind(a.run_proof),reader=bind(a.reader),
            auditor=bind(__file__),selection=bind(selection),events=bind(a.out/'selected-events.tsv.gz')),
        limits='Single synthetic64/64 firsttouch; no address coverage/unique capacity, FPGA, route, timing or performance claim. Saturation and reset-after-events separately tested in unit02.')
    (a.out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(a.out/'verification.json')


if __name__=='__main__':main()
