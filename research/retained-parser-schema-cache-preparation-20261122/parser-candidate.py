#!/usr/bin/env python3
"""Complete per-address real-publication/hit/SRAM proof for closed capacity cases."""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import threading

from build import ROOT,bind,require,image_from_elf
import generate

spec=importlib.util.spec_from_file_location('strict_advisory',ROOT/'testing/rtl/retained-advisory-trace/validate.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)


def selection():
    result=original.selections()
    result.update({'mutation':('unicore_lite.dcache_retained_mutation_v',1),
        'maintenance':('unicore_lite.dcache_retained_maintenance_v',1),
        'obs.hits':('retained_observe.counts.hits_o',32),
        'obs.published':('retained_observe.counts.published_o',32),
        'obs.beats':('retained_observe.counts.write_beats_o',32)})
    return result


def edges(lines,selected):
    mapping={};widths={};values={};changes={};time=None;ended=False;schema_complete=False
    clocks=('be.clk','i.bclk','i.cclk','d.bclk','d.cclk')
    def sample(t,updates):
        rising=[key for key in clocks if values.get(mapping[key])==0 and updates.get(mapping[key],values.get(mapping[key]))==1]
        if rising:yield t,rising,{key:values.get(handle) for key,handle in mapping.items()}
        values.update(updates)
    for line in lines:
        parts=line.rstrip('\n').split('\t')
        if parts[0]=='#SIGNAL':
            require(time is None and len(parts)==5,'signal declaration order');_,key,width,handle,name=parts
            require(key in selected and key not in mapping and int(width)==selected[key][1],'exact selected signal/width')
            suffix=selected[key][0];require(name==suffix or name.endswith('.'+suffix),'exact selected path')
            mapping[key]=int(handle);widths[int(handle)]=int(width)
        elif parts[0]=='#FST':require(len(parts)==4 and int(parts[2])>int(parts[1]),'nonempty FST')
        elif parts[0]=='#END':require(not ended,'duplicate EOF');ended=True
        else:
            require(not ended and len(parts)==3 and (schema_complete or set(mapping)==set(selected)),'complete event schema')
            current,handle=int(parts[0]),int(parts[1]);bits=parts[2].lower()
            require(handle in widths and len(bits)==widths[handle] and set(bits)<=set('01xz'),'known event format')
            require(time is None or current>=time,'monotonic time')
            if time is not None and current!=time:yield from sample(time,changes);changes={}
            time=current;require(handle not in changes,'one settled value per timestamp');changes[handle]=None if set(bits)&set('xz') else int(bits,2)
            schema_complete=True
    require(ended and time is not None,'closed complete FST');yield from sample(time,changes)


class Validator:
    def __init__(self,program,role):
        self.program=program;self.lane=role[0];self.active=role.endswith('enabled');self.mode=(1 if self.lane=='i' else 2) if self.active else 0
        self.lines=64;self.sets=64;self.targets={};self.marked={};self.inflight=None;self.lookup=None
        self.actual_pub={};self.actual_hit={};self.retained={};self.normal={};self.burst=None
        self.retired={};self.d_load_retirements=0;self.last_values=None;self.target_mem_before_pub=[]
        self.reset=original.Validator({'i':[0]*8,'d':[0]*8},{})
        for slot in range(self.lines):
            index=(slot&~63)+((slot*0xaaaaaaaaaaaaaaab)&63)
            addr=program['code_base']+192*index if self.lane=='i' else program['data_base']+64*slot
            self.targets[addr]=dict(slot=slot,index=index,words=generate.code_words(index) if self.lane=='i' else generate.data_words(slot))
        names=('populate_begin','verify_begin','verified')
        self.markers={name:program['symbols']['retained_capacity_'+self.lane+'_'+name]['address'] for name in names}
        self.d_begin=program['symbols']['retained_capacity_d_populate_begin']['address'];self.d_end=program['symbols']['retained_capacity_d_verified']['address']

    def sample(self,t,clocks,v):
        self.last_values=v
        def get(key):
            value=v.get(key);require(value is not None,'unknown consulted '+key);return value
        g=lambda key:get(self.lane+'.'+key)
        if 'be.clk' in clocks and self.reset.reset_gate('be',v.get('be.reset'),t) and get('be.instret'):
            require(not get('be.ctxtsw') and not get('be.exception'),'single-context nonexception retirement')
            pc=get('be.pc');instruction=0
            for field,width in (('funct7',7),('rs2_addr',5),('rs1_addr',5),('funct3',3),('rd_addr',5),('opcode',7)):
                instruction=(instruction<<width)|get('be.instr.'+field)
            for key,address in self.markers.items():
                if pc==address:require(key not in self.marked,'marker duplicate');self.marked[key]=t
            if self.lane=='d' and self.d_begin<=pc<self.d_end:
                require(instruction&127 not in (0x23,0x2f),'actual retired store/atomic in D protected phase')
                if instruction&127==3:self.d_load_retirements+=1
            if self.lane=='i' and (pc&~63) in self.targets:
                target=pc&~63;word=self.targets[target]['words'][(pc&63)//8];expected=(word>>((pc&7)*8))&0xffffffff
                require(pc%4==0 and instruction==expected,'all actual retired target instruction words')
                self.retired.setdefault(target,[]).append(pc)
        if self.lane+'.bclk' in clocks:
            lane=int(self.lane=='d');packed=v.get('store.reset');store_reset=None if packed is None else ((packed>>lane)&1)
            ready=self.reset.reset_gate(self.lane+'.uce',v.get(self.lane+'.breset'),t)
            ready=self.reset.reset_gate(self.lane+'.store',store_reset,t) and ready
            if ready:
                for key in ('lv','lr','rv','rr','rh','iv','ir','done','published'):
                    require(g(key)==((get('store.'+key)>>lane)&1),'real backend/client handshake '+key)
                if self.lane=='d' and self.actual_pub and 'verified' not in self.marked:
                    require(get('mutation')==get('maintenance')==0,'D mutation/maintenance after first publication')
                require(not g('published') or g('done'),'publication requires done')
                if g('iv') and g('ir'):
                    require(self.inflight is None,'one insert owner');self.inflight=dict(time=t,address=g('ia'),data=g('id'))
                if g('done'):
                    require(self.inflight is not None,'terminal insert owner');ins=self.inflight
                    if g('published'):
                        addr=ins['address'];require(self.active and addr in self.targets and addr not in self.actual_pub,'exact unique target publication')
                        require(get('control')==self.mode and g('enable') and not g('demand_copy') and g('owned') and g('pf') and g('owned_addr')==addr,'advisory-only PF-owned publication')
                        expected=sum(word<<(64*n) for n,word in enumerate(self.targets[addr]['words']))
                        require(ins['data']==expected,'full512-bit publication payload');self.actual_pub[addr]=dict(time=t,accepted=ins['time'])
                    self.inflight=None
                if g('lv') and g('lr'):
                    require(self.lookup is None,'one lookup owner');self.lookup=dict(time=t,address=g('la'))
                if g('rv') and g('rr'):
                    require(self.lookup is not None,'accepted lookup owns response');query=self.lookup;addr=query['address']
                    if g('rh'):
                        require(self.active and addr in self.targets and addr not in self.actual_hit,'exact unique target retained hit')
                        require(addr in self.actual_pub and self.actual_pub[addr]['time']<query['time'],'hit follows true publication')
                        require(get('control')==self.mode and not g('demand_copy'),'same advisory-only control at hit')
                        require(g('rd')==sum(word<<(64*n) for n,word in enumerate(self.targets[addr]['words'])),'full512-bit hit payload')
                        self.actual_hit[addr]=dict(time=t,lookup=query['time'])
                    self.lookup=None
        if self.lane+'.cclk' not in clocks:return
        if not self.reset.reset_gate(self.lane+'.cache',v.get(self.lane+'.creset'),t):return
        target=g('pkt.addr')&~63
        if not(g('v') and g('yumi') and g('pkt.opcode')==0 and target in self.targets):return
        aborted=self.lane=='i' and bool(g('abort_miss') or g('abort_miss_r'))
        if not g('slow') or aborted:return
        retained=g('state')==22;word=(g('pkt.addr')&63)//8
        if self.active:require(retained,'normal-memory target fill violates cold retained-use proof')
        else:
            require(not retained,'negative has retained fill')
            way=g('pkt.way_id');bank=(word+way)%8;expected=self.targets[target]['words'][word]
            require(0<=way<8 and g('pkt.data')==expected and g('pkt.fill_index')==1<<word,'negative ordinary full-word packet')
            require(g('slow')==1<<bank and g('mem_v')&(1<<bank) and g('mem_w')&(1<<bank),'negative actual ordinary SRAM write')
            require(g('mem.addr.'+str(bank))==((target>>6)&63)*8+word and g('mem.data.'+str(bank))==expected,'negative actual ordinary SRAM address/data')
            if self.lane=='d':require(g('mem.mask.'+str(bank))==255,'negative SRAM full byte mask')
            burst=self.normal.setdefault(target,dict(address=target,words={}))
            burst['words'][word]=dict(time=t,address=g('pkt.addr'),data=expected,bank=bank)
            return
        if word==0:
            require(self.burst is None,'new fill cannot replace an unfinished burst')
            if retained:require(target in self.actual_hit and self.actual_hit[target]['time']<t,'real hit before restore')
            self.burst=dict(address=target,retained=retained,time=t,way=g('pkt.way_id'),words=[],request=g('req_addr'))
        burst=self.burst;require(burst is not None and burst['address']==target and burst['retained']==retained,'fill starts at word0 and keeps owner')
        bank=(word+burst['way'])%8;expected=self.targets[target]['words'][word]
        require(word==len(burst['words']) and 0<=burst['way']<8 and g('pkt.way_id')==burst['way'],'ascending eight distinct words/same way')
        require(g('pkt.addr')==target+8*word and g('pkt.index')==((target>>6)&63) and g('pkt.data')==expected and g('pkt.fill_index')==1<<word,'exact normal fill packet')
        require(g('slow')==1<<bank and g('mem_v')&(1<<bank) and g('mem_w')&(1<<bank),'actual SRAM write enable')
        require(g('mem.addr.'+str(bank))==((target>>6)&63)*8+word and g('mem.data.'+str(bank))==expected,'actual SRAM address/full64b data')
        if self.lane=='d':
            require(g('mem.mask.'+str(bank))==255,'full SRAM byte mask')
            require(burst['request']==target+24,'critical offset3 actual demand')
        require(g('critical')==int(word==((burst['request']>>3)&7)) and g('last')==int(word==7),'critical/last ownership')
        if word==0:
            require(g('tv') and g('ty') and g('tag.opcode')==1 and g('tag.index')==((target>>6)&63)
                    and g('tag.way_id')==burst['way'] and g('tag.tag')==target>>12 and g('tag.state')==6,'actual accepted normal L1 tag write')
        burst['words'].append(dict(time=t,address=g('pkt.addr'),data=expected,bank=bank))
        if word==7:
            destination=self.retained if retained else self.normal
            require(target not in destination,'no duplicate winning target fill');destination[target]=burst;self.burst=None

    def finish(self):
        require(set(self.marked)==set(self.markers) and self.marked['populate_begin']<self.marked['verify_begin']<self.marked['verified'],'all retired phase boundaries')
        require(self.inflight is None and self.lookup is None and self.burst is None,'no unfinished protocol owner')
        wanted=set(self.targets)
        if self.active:
            require(set(self.actual_pub)==set(self.actual_hit)==set(self.retained)==wanted and not self.normal,'all configured distinct full-line entries genuinely used')
            require(max(row['time'] for row in self.actual_pub.values())<min(row['time'] for row in self.actual_hit.values()),'all publications precede first target demand')
        else:
            require(not self.actual_pub and not self.actual_hit and not self.retained and set(self.normal)==wanted,'negative complete ordinary-memory fallback')
            require(all(set(burst['words'])==set(range(8)) for burst in self.normal.values()),'negative all8 words actually stored normally')
        if self.lane=='d':require(self.d_load_retirements==8*self.lines,'all eight words per D line architecturally loaded')
        else:
            require(set(self.retired)==wanted,'all I target functions retired')
            for addr,pcs in self.retired.items():require(pcs==list(range(addr,addr+64,4)),'all16 instructions per function exactly once')
        for burst in (self.retained if self.active else self.normal).values():
            words=burst['words'] if self.active else burst['words'].values()
            require(max(word['time'] for word in words)<self.marked['verified'],'winning writes before complete checks')
        return dict(state='PASS actual distinct configured-line publications/hits/full-SRAM payload and checked execution' if self.active else 'PASS negative actual ordinary-memory fallback with primary retained-use rejection',
            lane=self.lane,lines=self.lines,markers=self.marked,targets=self.targets,publications=self.actual_pub,hits=self.actual_hit,
            retained_bursts=self.retained,ordinary_bursts=self.normal,retired_instruction_pcs=self.retired,
            d_protected_load_retirements=self.d_load_retirements,reset_observations=self.reset.reset_observations,
            limits='Only actual64/64 configured model. Aggregate physical counters remain weaker than per-address model proof; no FPGA/fit/speedup claim.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('case','reader','out'):parser.add_argument('--'+name,required=True,type=Path)
    a=parser.parse_args();run=json.loads((a.case/'verification.json').read_text());admission=json.loads((a.case/'admission.json').read_text())
    for record in run['files']+[run['admission']]:require(bind(record['path'])==record,'closed run binding changed')
    program=json.loads(Path(admission['program']['path']).read_text());require(bind(admission['program']['path'])==admission['program'],'program binding')
    original.source_bindings(Path(admission['compiled_sources']['path']))
    a.out.mkdir(parents=True,exist_ok=False);selected=selection();sel=a.out/'selection.tsv'
    sel.write_text(''.join(key+'\t'+suffix+'\n' for key,(suffix,_) in selected.items()))
    fst=a.case/'trace.fst';before=bind(fst);validator=Validator(program,run['role']);command=[str(a.reader.resolve()),str(fst.resolve()),str(sel.resolve())]
    with (a.out/'reader.stderr').open('w') as error,gzip.open(a.out/'selected-events.tsv.gz','wt') as saved:
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=error,text=True);timer=threading.Timer(600,process.kill);timer.daemon=True;timer.start()
        try:
            def stream():
                for line in process.stdout:saved.write(line);yield line
            for t,clocks,values in edges(stream(),selected):validator.sample(t,clocks,values)
            require(process.wait()==0,'reader completion')
        except BaseException:process.kill();process.wait();raise
        finally:timer.cancel()
    report=validator.finish();require(bind(fst)==before,'closed FST unchanged')
    report['bindings']=dict(fst=before,run=bind(a.case/'verification.json'),admission=bind(a.case/'admission.json'),
        program=bind(admission['program']['path']),auditor=bind(__file__),reader=bind(a.reader),selection=bind(sel),events=bind(a.out/'selected-events.tsv.gz'))
    (a.out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(a.out/'verification.json')


if __name__=='__main__':main()
