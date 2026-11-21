#!/usr/bin/env python3
"""Measure own-lane accepted-edge service from CLOSED retained-store FSTs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess

PIN = None # New source is bound by the closed manifest and snapshots, not an old backend hash.
NAMES = {'clk_i':2, 'reset_i':2, 'clear_i':2, 'lookup_v_i':2, 'lookup_ready_o':2,
         'resp_v_o':2, 'resp_ready_i':2, 'resp_hit_o':2, 'insert_v_i':2,
         'insert_ready_o':2, 'insert_done_o':2, 'insert_published_o':2}
for lane in range(2):
    for stem,width in [('lookup_addr',34),('insert_addr',34),('insert_data',512),('resp_data',512)]:
        NAMES[f'{stem}{lane}_'+('o' if stem=='resp_data' else 'i')] = width


def artifact(path):
    path=Path(path).resolve()
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=h.hexdigest())


def payload(addr,salt=0):
    return sum((((0x13579bdf02468ace ^ addr)+word*0x1111111111111111+salt)&((1<<64)-1))<<(64*word) for word in range(8))


def prefix(lane,n,sets):
    base=0x1000000+lane*0x400000
    q=[(base,False,0,'empty_miss')]
    ins=[]
    if not n: return q,[(base,False,0,'disabled_insert')]
    ins=[(base+64*i,True,0,'fill_insert') for i in range(n)]
    q += [(base+64*i+17,True,0,'all_slot_hit') for i in range(n)]
    conflict=base+((n+sets-1)//sets)*sets*64
    ins += [(conflict,False,9,'pinned_refusal'),(conflict,True,9,'replacement_insert')]
    q += [(base,True,0,'retained_hit'),(base,False,0,'full_set_miss'),(conflict,True,9,'replacement_hit')]
    if n>1:
        ins += [(base+64,True,31,'refresh_insert')]
        q += [(base+64,True,31,'refresh_hit')]
    return q,ins


class Audit:
    def __init__(self,lines,sets):
        self.lines,self.sets=lines,sets
        self.rows=max((n+sets-1)//sets for n in lines)<=8
        self.expected=[prefix(i,n,sets) for i,n in enumerate(lines)]
        self.edge=[0,0]; self.pending=[[None,None],[None,None]]
        self.counts=[[0]*5 for _ in range(2)]; self.samples={}
        self.clearing=[None,None];self.clear_samples=[[],[]]

    def expected_service(self,lane,typ,addr,label):
        n=self.lines[lane]
        if not n:return 1
        ordinal=((addr&~63)-(0x1000000+lane*0x400000))//64
        local_set=ordinal%self.sets
        ways=(n-1-local_set)//self.sets+1
        if typ==0:
            if label in ('empty_miss','full_set_miss'):return 3 if self.rows else 2*ways+1
            way=ordinal//self.sets if label=='all_slot_hit' else 0
            return 12 if self.rows else 12+2*way
        if label=='pinned_refusal':return 3 if self.rows else 2*ways+1
        if label=='refresh_insert':return 12
        return 12 if self.rows else 2*ways+10

    def step(self,old,new):
        def value(name, lane=None, before=True):
            raw=(old if before else new).get(name,'x')
            if any(c in raw.lower() for c in 'xz'): raise ValueError('unknown qualified '+name)
            n=int(raw,2)
            return n if lane is None else (n>>lane)&1
        for lane in range(2):
            if value('clk_i',lane) or not value('clk_i',lane,False): continue
            self.edge[lane]+=1
            if value('reset_i',lane):
                if any(self.pending[lane]): raise ValueError('reset discarded owned operation')
                continue
            if value('clear_i',lane):self.clearing[lane]=self.edge[lane]
            elif self.clearing[lane] is not None and value('lookup_ready_o',lane):
                cost=self.edge[lane]-self.clearing[lane]
                expected=(self.sets if self.rows else self.lines[lane])+1 if self.lines[lane] else 1
                if cost!=expected:raise ValueError('clear sweep service mismatch '+str((lane,cost,expected)))
                self.clear_samples[lane].append(cost);self.clearing[lane]=None
            for typ,qualified in [(0,value('resp_v_o',lane) and value('resp_ready_i',lane)),
                                  (1,value('insert_done_o',lane))]:
                if not qualified: continue
                token=self.pending[lane][typ]
                if token is None: raise ValueError('unmatched response/terminal')
                idx,addr,started=token
                expected=self.expected[lane][typ]
                hit=value('resp_hit_o' if typ==0 else 'insert_published_o',lane)
                if idx<len(expected):
                    ea,eh,salt,label=expected[idx]
                    if (addr,hit)!=(ea,int(eh)): raise ValueError('prefix address/outcome mismatch')
                    if typ==0 and hit and value(f'resp_data{lane}_o')!=payload(addr&~63,salt):
                        raise ValueError('full64B response payload mismatch')
                    key=f'lane{lane}/{label}'
                    service=self.edge[lane]-started
                    if service!=self.expected_service(lane,typ,addr,label):
                        raise ValueError('unexpected independently measured service '+str((key,service)))
                    self.samples.setdefault(key,[]).append(service)
                self.counts[lane][1 if typ==0 else 3]+=1
                if typ==1: self.counts[lane][4]+=hit
                self.pending[lane][typ]=None
            if value('insert_published_o',lane) and not value('insert_done_o',lane):
                raise ValueError('publication without terminal')
            for typ,valid,ready,stem in [(0,'lookup_v_i','lookup_ready_o','lookup_addr'),(1,'insert_v_i','insert_ready_o','insert_addr')]:
                if not(value(valid,lane) and value(ready,lane)): continue
                if self.pending[lane][typ] is not None: raise ValueError('overlapping owned operation')
                slot=0 if typ==0 else 2
                idx=self.counts[lane][slot]; addr=value(f'{stem}{lane}_i')
                expected=self.expected[lane][typ]
                if idx<len(expected):
                    ea,_,salt,_=expected[idx]
                    if addr!=ea: raise ValueError('prefix accepted address mismatch')
                    if typ==1 and value(f'insert_data{lane}_i')!=payload(addr,salt):
                        raise ValueError('full64B insert payload mismatch')
                self.pending[lane][typ]=(idx,addr,self.edge[lane]);self.counts[lane][slot]+=1
    def finish(self,expected_counts):
        if any(any(row) for row in self.pending): raise ValueError('EOF with owned operation')
        if any(n is not None for n in self.clearing):raise ValueError('EOF during explicit clear')
        if self.counts!=expected_counts: raise ValueError(f'counts mismatch {self.counts} != {expected_counts}')
        for lane in range(2):
            for typ,slot in [(0,0),(1,2)]:
                if self.counts[lane][slot]<len(self.expected[lane][typ]): raise ValueError('incomplete capacity prefix')
        return {key:dict(count=len(v),min=min(v),median=statistics.median(v),max=max(v),
                         histogram=dict(sorted(Counter(v).items()))) for key,v in sorted(self.samples.items())}


def analyze_vcd(stream,audit):
    ids={}; bindings={}; values={}; changes={}; header=True; seen_time=False; last_time=-1; groups=0
    def group():
        nonlocal groups
        if not changes: return
        new=dict(values);new.update(changes)
        if all(name in values for name in NAMES): audit.step(values,new)
        values.update(changes);changes.clear();groups+=1
    for raw in stream:
        line=raw.strip()
        if header:
            if line.startswith('$var '):
                fields=line.split(); width=int(fields[2]); ident=fields[3]; name=fields[4]
                if name in NAMES:
                    if width!=NAMES[name]: raise ValueError('signal width mismatch '+name)
                    if name in bindings and bindings[name]!=ident: raise ValueError('ambiguous signal '+name)
                    bindings[name]=ident;ids.setdefault(ident,[]).append(name)
            if line=='$enddefinitions $end':
                header=False
                if set(bindings)!=set(NAMES): raise ValueError('missing required trace ports')
            continue
        if line.startswith('#'):
            group();stamp=int(line[1:])
            if stamp<last_time: raise ValueError('trace time reversal')
            last_time=stamp;seen_time=True
        elif line and not line.startswith('$'):
            if line[0] in 'bB': bits,ident=line[1:].split()
            elif line[0] in '01xXzZ': bits,ident=line[0],line[1:]
            else: continue
            for name in ids.get(ident,[]): changes[name]=bits
    group()
    if header or not seen_time or not groups: raise ValueError('incomplete VCD')
    return dict(last_trace_tick=last_time,groups=groups,own_lane_edges=audit.edge)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--sets',type=int,required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--fst2vcd',default='/usr/bin/fst2vcd')
    a=ap.parse_args();m=json.loads(a.manifest.read_text())
    if m['state'] != 'PASS-retained-tagrows': raise ValueError('unclosed input')
    if m['sources']['bp_retained_line_store.sv']['sha256']!=artifact(a.manifest.parent/'source/bp_retained_line_store.sv')['sha256']: raise ValueError('backend snapshot mismatch')
    if a.sets not in (64,256) or m.get('retained_sets',64)!=a.sets: raise ValueError('geometry mismatch')
    for name,binding in m['sources'].items():
        snap=a.manifest.parent/'source'/name
        if artifact(snap)['sha256']!=binding['sha256']: raise ValueError('source snapshot mismatch')
    a.output.mkdir(parents=True,exist_ok=False)
    result=dict(scope='Accepted own-lane rising-edge request to accepted response / observed terminal pulse. Includes interface handshake edge; not application time, FPGA timing, or memory latency.',
                input_manifest=artifact(a.manifest),analyzer=artifact(__file__),converter=artifact(a.fst2vcd),retained_sets=a.sets,runs=[])
    for row in m['clock_results']:
        fst=Path(row['fst']['path'])
        if artifact(fst)!=row['fst']: raise ValueError('FST binding mismatch')
        expected=[[int(x) for x in r[1:]] for r in sorted(row['counts'])]
        log=a.manifest.parent/('run-'+row['clock_mode']+'.log')
        if log.read_text().count('RETAINED_TEST_EXIT_CLEAN')!=1: raise ValueError('completion log absent')
        audit=Audit([m['i_lines'],m['d_lines']],a.sets)
        with (a.output/(row['clock_mode']+'-converter.log')).open('w') as err:
            proc=subprocess.Popen([a.fst2vcd,str(fst)],stdout=subprocess.PIPE,stderr=err,text=True)
            try: timing=analyze_vcd(proc.stdout,audit)
            except BaseException: proc.kill();proc.wait();raise
            if proc.wait()!=0: raise ValueError('converter did not reach clean EOF')
        result['runs'].append(dict(clock_mode=row['clock_mode'],fst=row['fst'],log=artifact(log),
                                  counts=audit.counts,service_cycles=audit.finish(expected),clear_cycles=audit.clear_samples,
                                  trace=timing,converter_clean_eof=True))
    result['state']='PASS-closed-trace-service-audit'
    (a.output/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(a.output/'analysis.json')

if __name__=='__main__':main()
