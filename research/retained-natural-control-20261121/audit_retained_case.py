#!/usr/bin/env python3
"""Actual retained-port ownership, publication provenance and clipped telemetry.
No target execution, trace filtering, cache-model projection or timing attribution.
"""
import argparse
import collections
import gzip
import json
from pathlib import Path
import subprocess
import threading
from prepare import bind,HERE,ROOT
from audit_closed_case import admission,verify


def selections():
    fields=json.loads((HERE/'retention-selection.json').read_text())['fields']
    fields={k:dict(v) for k,v in fields.items()}
    prefix=fields['store_clear_i']['path'].rsplit('.',1)[0]
    for lane in range(2):
        fields[f'store_state_{lane}']=dict(path=f'{prefix}.lane_fsm[{lane}].state_r',width=4)
        for port in ('insert_data_i','resp_data_o'):
            fields[f'store_{port}_{lane}']=dict(path=f'{prefix}.{port}[{lane}]',width=512)
    return fields


class Ports:
    def __init__(self,phases,mode,emit=lambda e:None):
        self.mode=mode;self.emit=emit
        self.windows={'program':None,'whole':(phases['whole_begin'],phases['whole_end']),
                      'timed_ring':(phases['timed_begin'],phases['timed_end'])}
        self.counts={w:{k:collections.Counter() for k in ('i','d','control')} for w in self.windows}
        self.lookup=[None,None];self.insert=[None,None];self.published=[{},{}]
        self.edge=[0,0];self.reset_seen=[False,False];self.clear_previous=[False,False]
        self.actors={str(a):set() for a in range(4)};self.labels=collections.Counter()
        self.last_cycle=None;self.be_reset_seen=False;self.program_started=False

    def count(self,cycle,lane,name,extra=None):
        for window,bounds in self.windows.items():
            if bounds is None or bounds[0]<=cycle<bounds[1]:self.counts[window][lane][name]+=1
        if extra is not None:self.emit(dict(event=name,lane=lane,global_cycle=cycle,**extra))

    def be(self,v):
        if v['be_reset']:
            if self.program_started:raise ValueError('BE reset after program startup')
            self.be_reset_seen=True;self.last_cycle=None
            return
        if not self.be_reset_seen:return
        cycle=v['global_cycle']
        if self.last_cycle is not None and cycle<self.last_cycle:raise ValueError('core-global cycle reversal')
        self.last_cycle=cycle
        if v['retained_control_cmd_v']:
            self.count(cycle,'control','writes',dict(value=v['retained_control_cmd']))
        if v['instret']:
            if v['pc']==0x80000000:self.program_started=True
            actor=v['context'+str(v['retire_slot'])]
            if actor not in range(4):raise ValueError('invalid retired context')
            self.actors[str(actor)].add(v['retire_slot'])
            if v['pc'] in (0x80000236,0x80000404,0x80000428,0x8000044a,0x8000063a,0x80000780,0x8000079a):
                self.labels[hex(v['pc'])]+=1

    def lane(self,lane,v):
        name=('i','d')[lane];edge=self.edge[lane];self.edge[lane]+=1
        bit=lambda k:(v['store_'+k]>>lane)&1
        if bit('reset_i'):
            if self.lookup[lane] or self.insert[lane]:raise ValueError('reset revoked accepted ownership')
            self.reset_seen[lane]=True;self.published[lane].clear();self.clear_previous[lane]=False
            return
        if not self.reset_seen[lane]:
            # The actual testbench has a clock edge before its first asserted
            # reset. No accepted ownership may be discarded in this preamble.
            if (bit('lookup_v_i') and bit('lookup_ready_o')) or (bit('insert_v_i') and bit('insert_ready_o')) or bit('resp_v_o') or bit('insert_done_o'):
                raise ValueError('accepted activity before observed reset')
            return
        cycle=v['global_cycle'];clear=bool(bit('clear_i'));inv=bool(bit('invalidate_v_i'))
        inv_set=(v[f'store_invalidate_addr_i_{lane}']>>6)&255
        if bit('busy_o'):self.count(cycle,name,'busy_sampled_cycles')
        if clear:
            self.count(cycle,name,'clear_asserted_cycles')
            if not self.clear_previous[lane]:self.count(cycle,name,'clear_episodes',{})
        self.clear_previous[lane]=clear
        if inv:
            self.count(cycle,name,'mutation_invalidate_asserted_cycles')
            if v[f'store_state_{lane}']!=0:self.count(cycle,name,'mutation_invalidate_accepted',dict(set=inv_set))
        if bit('epoch_wrap_o'):self.count(cycle,name,'epoch_wrap_pulses',{})
        # Terminal pulses describe the PREVIOUS edge's publication. Process
        # them before this edge's clear/mutation invalidates the resulting line.
        if bit('insert_published_o') and not bit('insert_done_o'):raise ValueError('publication without terminal')
        if bit('insert_done_o'):
            owner=self.insert[lane]
            if owner is None:raise ValueError('insert terminal without accepted owner')
            extra=dict(address=hex(owner['address']),accepted_cycle=owner['cycle'],lane_edges=edge-owner['edge'])
            self.count(cycle,name,'insert_terminal',extra)
            if bit('insert_published_o'):
                if owner['killed']:raise ValueError('killed insertion published')
                self.published[lane][owner['address']]=owner['data']
                self.count(cycle,name,'insert_publication',extra)
            else:self.count(cycle,name,'insert_not_published',extra)
            self.insert[lane]=None
        if clear or bit('epoch_wrap_o'):
            self.published[lane].clear()
            if self.insert[lane]:self.insert[lane]['killed']=True
        elif inv:
            self.published[lane]={a:d for a,d in self.published[lane].items() if ((a>>6)&255)!=inv_set}
            if self.insert[lane] and ((self.insert[lane]['address']>>6)&255)==inv_set:self.insert[lane]['killed']=True
        if bit('insert_cancel_i') and self.insert[lane]:self.insert[lane]['killed']=True
        if bit('resp_v_o') and bit('resp_ready_i'):
            owner=self.lookup[lane]
            if owner is None:raise ValueError('response without accepted lookup')
            hit=bool(bit('resp_hit_o'))
            if hit:
                expected=self.published[lane].get(owner['address'])
                if expected is None:raise ValueError('hit without noninvalidated publication provenance')
                if expected!=v[f'store_resp_data_o_{lane}']:raise ValueError('returned512b differs from published full line')
            self.count(cycle,name,'lookup_response',dict(address=hex(owner['address']),hit=hit,accepted_cycle=owner['cycle'],lane_edges=edge-owner['edge']))
            self.count(cycle,name,'lookup_hit' if hit else 'lookup_miss')
            self.lookup[lane]=None
        if bit('lookup_v_i'):
            self.count(cycle,name,'lookup_valid_cycles')
            if not bit('lookup_ready_o'):self.count(cycle,name,'lookup_blocked_cycles')
        if bit('lookup_v_i') and bit('lookup_ready_o'):
            if self.lookup[lane] is not None:raise ValueError('second lookup before response')
            addr=v[f'store_lookup_addr_i_{lane}']&~63
            self.lookup[lane]=dict(address=addr,cycle=cycle,edge=edge)
            self.count(cycle,name,'lookup_accept',dict(address=hex(addr)))
        if bit('insert_v_i'):
            self.count(cycle,name,'insert_valid_cycles')
            if not bit('insert_ready_o'):self.count(cycle,name,'insert_blocked_cycles')
        if bit('insert_v_i') and bit('insert_ready_o'):
            if self.insert[lane] is not None:raise ValueError('second insert before terminal')
            addr=v[f'store_insert_addr_i_{lane}']
            if addr&63:raise ValueError('unaligned full-line insert')
            self.insert[lane]=dict(address=addr,cycle=cycle,edge=edge,data=v[f'store_insert_data_i_{lane}'],killed=False)
            self.count(cycle,name,'insert_accept',dict(address=hex(addr)))

    def report(self):
        if any(self.lookup) or any(self.insert):raise ValueError('accepted ownership undrained at closed EOF')
        if not all(self.reset_seen):raise ValueError('both actual lane resets required')
        if self.mode==0:
            for lane in ('i','d'):
                for key in ('lookup_accept','insert_accept','insert_publication','lookup_hit'):
                    if self.counts['whole'][lane][key]:raise ValueError('off arm engaged retained work')
        return dict(counts={w:{k:dict(v) for k,v in lanes.items()} for w,lanes in self.counts.items()},
                    retired_context_slots={k:sorted(v) for k,v in self.actors.items()},label_counts=dict(self.labels),
                    sampled_lane_edges=self.edge,ownership_drained=True)


def consume(lines,fields,phases,mode,emit=lambda e:None):
    ports=Ports(phases,mode,emit);mapping={};names=set();values={};changes={};stamp=None;ended=False
    def group():
        new=dict(values);new.update(changes)
        if values and len(values)==len(fields):
            if values['be_clock']==0 and new['be_clock']==1:ports.be(values)
            for lane in range(2):
                if not(values['store_clk_i']&(1<<lane)) and new['store_clk_i']&(1<<lane):ports.lane(lane,values)
        values.update(changes);changes.clear()
    for line in lines:
        p=line.rstrip('\n').split('\t')
        if p[0]=='#FST':continue
        if p[0]=='#SIGNAL':
            if stamp is not None or len(p)!=5 or p[1] in names or p[1] not in fields:raise ValueError('bad declaration')
            key=p[1]
            if int(p[2])!=fields[key]['width'] or p[4]!=fields[key]['path']:raise ValueError('wrong width/path')
            names.add(key);mapping.setdefault(int(p[3]),[]).append(key)
        elif p[0]=='#END':
            if ended:raise ValueError('duplicate EOF')
            group();ended=True
        else:
            if ended or len(p)!=3 or names!=set(fields):raise ValueError('incomplete/late events')
            tick,handle=int(p[0]),int(p[1])
            if stamp is not None and tick<stamp:raise ValueError('time reversal')
            if stamp is not None and tick!=stamp:group()
            stamp=tick
            for key in mapping[handle]:
                if key in changes or len(p[2])!=fields[key]['width'] or set(p[2])-set('01'):raise ValueError('duplicate/unknown/wrong event width')
                changes[key]=int(p[2],2)
    if not ended:raise ValueError('missing recoverable EOF')
    return ports.report()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cohort',type=Path,required=True);p.add_argument('--mode',type=int,choices=(0,15),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    before=bind(a.cohort);cohort=json.loads(a.cohort.read_text());row=next(r for r in cohort['runs'] if r['mode']==a.mode)
    for b in cohort['frozen_inputs'].values():verify(b)
    for name in ('trace','log','guest','trace_metadata'):verify(row[name])
    guest=json.loads(Path(row['guest']['path']).read_text());metadata=json.loads(Path(row['trace_metadata']['path']).read_text())
    admission(cohort,a.mode,Path(row['log']['path']).read_text(),guest,metadata)
    a.output.mkdir(parents=True,exist_ok=False);fields=selections();selection=a.output/'selection.tsv';selection.write_text(''.join(k+'\t'+v['path']+'\n' for k,v in fields.items()))
    reader=ROOT/'research/retained-system-geometry-20261121/reader/fst_events';cmd=[str(reader),row['trace']['path'],str(selection)]
    result=None;error=None
    with gzip.open(a.output/'selected-events.tsv.gz','wt') as saved,gzip.open(a.output/'events.jsonl.gz','wt') as events,(a.output/'reader.stderr').open('w') as err:
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=err,text=True);timer=threading.Timer(600,proc.kill);timer.daemon=True;timer.start()
        def lines():
            for line in proc.stdout:saved.write(line);yield line
        try:
            result=consume(lines(),fields,guest['phases'],a.mode,lambda e:events.write(json.dumps(e,separators=(',',':'))+'\n'))
            if proc.wait()!=0:raise ValueError('reader failed/timed out')
        except BaseException as e:error=repr(e);proc.kill();proc.wait()
        finally:timer.cancel()
    if bind(a.cohort)!=before:raise ValueError('cohort changed during closed audit')
    for name in ('trace','log','guest','trace_metadata'):verify(row[name])
    report=dict(state='PASS-retained-port-audit' if result is not None and error is None else 'FAIL-no-accepted-telemetry',error=error,
                scope='Actual accepted retained port transactions, ownership, full512b publication-to-hit data provenance and clipped counters. Not a model of unique retained capacity or execution.',
                cohort=before,mode=a.mode,trace=row['trace'],guest=row['guest'],source=bind(__file__),reader=bind(reader),selection=bind(selection),command=cmd,report=result,
                limits=['Publication provenance remembers prior noninvalidated lines without simulating physical way replacement. It checks actual hit data provenance, not a capacity curve or absence of false hits after replacement.',
                        'Coarse same-set mutation kills are counted; valid/asserted cycles are not called dropped transactions. Busy occupancy is not critical-path stall time.',
                        'All cycle windows use actual checked CSR values, half-open. No FPGA/Linux or calibrated-memory projection.'])
    (a.output/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
    if error:raise ValueError(error)
    print(json.dumps(dict(state=report['state'],mode=a.mode,report=result),indent=2))


if __name__=='__main__':main()
