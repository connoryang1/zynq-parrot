"""Pinned semantic method slices only; no constructors/lifecycle/tool imports."""
from csr1280_support import require


class SingleMethods:
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


class LaneMethods(SingleMethods):
    """Joint LaneValidator sample/finish are byte-identical to SingleMethods."""
    pass


class JointMethods:
    def sample(self,t,clocks,v):
        for validator in self.lanes.values():validator.sample(t,clocks,v)
        be_ready=self.lanes['i'].reset.reset_seen.get('be') and v.get('be.reset')==0
        if 'be.clk' in clocks and be_ready and v.get('be.instret'):
            pc=v['be.pc']
            for key,address in self.markers.items():
                if pc==address:
                    require(key not in self.marked,'unique joint marker')
                    self.marked[key]=t
            if 'populate_begin' in self.lanes['i'].marked and 'joint_verified' not in self.marked:
                self.controlled_retirements+=1
                instruction=0
                for field,width in (('funct7',7),('rs2_addr',5),('rs1_addr',5),('funct3',3),('rd_addr',5),('opcode',7)):
                    require(v.get('be.instr.'+field) is not None,'known full retired instruction')
                    instruction=(instruction<<width)|v['be.instr.'+field]
                opcode=instruction&127;rd=(instruction>>7)&31
                require(opcode not in (0x23,0x2f,0x0f),'no retired store/atomic/fence during combined population+check')
                if opcode==3:
                    require('verify_begin' in self.lanes['d'].marked and ((instruction>>12)&7)==3 and ((instruction>>15)&31)==6,'only protected target LD via t1')
                if opcode in (0x6f,0x67) and rd!=0:
                    require(opcode==0x67 and rd==1 and pc==self.call,'only declared I-target call site')
                if opcode==0x73:
                    csr=instruction>>20;funct3=(instruction>>12)&7;rs1=(instruction>>15)&31
                    if funct3==2 and rs1==0:
                        require(csr in (0x5c2,0x7c0,0x9c0),'only declared status CSR reads')
                    else:
                        require(funct3==1 and csr in (0x7c0,0x9c0) and 'joint_populated' not in self.marked,'only preverification direct hints; no control writes')
        if any(x.actual_pub for x in self.lanes.values()) and 'joint_verified' not in self.marked:
            require(v.get('control')==3 and v.get('i.enable')==v.get('d.enable')==1,'joint lookups remain enabled')
            require(v.get('i.demand_copy')==v.get('d.demand_copy')==0,'both demand-copy paths remain off')
            for key in ('be.reset','store.reset','i.breset','d.breset','i.creset','d.creset'):
                require(v.get(key)==0,'no reset after joint population begins')

    def finish(self):
        require(set(self.marked)==set(self.markers),'all joint retired milestones')
        result={lane:validator.finish() for lane,validator in self.lanes.items()}
        i,d=self.lanes['i'],self.lanes['d']
        ordered=[i.marked['populate_begin'],self.marked['i_populated'],d.marked['populate_begin'],
                 self.marked['joint_populated'],i.marked['verify_begin'],i.marked['verified'],
                 d.marked['verify_begin'],d.marked['verified'],self.marked['joint_verified']]
        require(all(a<b for a,b in zip(ordered,ordered[1:])),'I population then D population then I checks then D checks')
        require(max(x['time']for x in i.actual_pub.values())<d.marked['populate_begin'],'full I published before D population')
        last_publication=max(x['time']for lane in self.lanes.values()for x in lane.actual_pub.values())
        first_query=min(x['lookup']for lane in self.lanes.values()for x in lane.actual_hit.values())
        require(last_publication<first_query and last_publication<self.marked['joint_populated'],'both full payload sets coexist before any target demand')
        # FE may accept I lookup before the BE verify marker retires. Do not
        # treat that marker as the exact demand start or omit any such event.
        for lane,proof in result.items():
            proof['sets']=self.program['sets']
            proof['limits']='Joint256+256 actual full64B simulation mechanism; advisory-backed, demand-copy off; no physical/fit/application/performance inference.'
        return dict(state='PASS joint configured I+D publications/full512 hits/eight real L1 writes/all target execution',
                    i=result['i'],d=result['d'],joint_markers=self.marked,
                    complete_protected_retirements=self.controlled_retirements,
                    all_publications_before_first_target_lookup=True,
                    expected_six_GP0=[256,256,256,256,2048,2048],
                    actual_GP0='Must be separately checked against unchanged counter projection/checker and complete native result',
                    scope='One sequential survival/interference correctness case; not simultaneous peak lookup throughput or a natural demand workload.')
