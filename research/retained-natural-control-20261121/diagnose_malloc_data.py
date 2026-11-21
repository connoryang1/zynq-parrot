#!/usr/bin/env python3
"""Read-only first-allocation-fault input/writeback/refill recovery, prefix only."""
import collections,gzip,json,subprocess,threading,time
from pathlib import Path
from prepare import bind,ROOT,HERE


def main():
 out=HERE/'failed-malloc-data01';out.mkdir(exist_ok=False)
 cohort=json.loads((HERE/'cohort01/cohort.json').read_text());fst=cohort['runs'][0]['trace'];assert bind(fst['path'])==fst
 core='TOP.bsg_nonsynth_zynq_testbench.dut.top_fpga_inst.blackparrot.processor.u.unicore.unicore_lite';be=core+'.core_minimal.be';mem=be+'.calculator.pipe_mem';dc=mem+'.dcache';rf=be+'.scheduler.int_regfile'
 paths={'beclk':be+'.clk_i','reset':be+'.reset_i','cycle':be+'.calculator.pipe_sys.csr.global_cycle_r','instret':be+'.commit_pkt.instret','pc':be+'.commit_pkt.pc','exception':be+'.commit_pkt.exception','faultaddr':be+'.commit_pkt.vaddr','dclk':dc+'.clk_i'}
 for n in ['rd_w_v_i','rd_thread_id_i','rd_addr_i','rd_data_i']:paths['rf_'+n]=rf+'.'+n
 for n in ['pc','rs1','imm','eaddr','is_req']:paths['mem_'+n]=mem+'.'+n
 for n in ['data_mem_pkt_v_i','data_mem_pkt_yumi_o','data_mem_slow_write','cache_req_critical_i','cache_req_last_i','tag_mem_pkt_v_i','tag_mem_pkt_yumi_o','cache_req_v_o','cache_req_yumi_i']:paths['dc_'+n]=dc+'.'+n
 for n in ['addr','data','fill_index','way_id','opcode']:paths['pkt_'+n]=dc+'.data_mem_pkt_cast_i.'+n
 for n in ['index','way_id','tag','state','opcode']:paths['tag_'+n]=dc+'.tag_mem_pkt_cast_i.'+n
 for n in ['addr','msg_type']:paths['req_'+n]=dc+'.cache_req_cast_o.'+n
 for bank in range(8):
  for n in ['data','mask']:paths[f'bank{bank}_{n}']=dc+f'.data_mem_{n}_li[{bank}]'
 selection=out/'selection.tsv';selection.write_text(''.join(k+'\t'+p+'\n' for k,p in paths.items()));reader=ROOT/'research/retained-system-geometry-20261121/reader/fst_events';cmd=[str(reader),fst['path'],str(selection.resolve())]
 mapping={};values={};changes={};stamp=None;seen=False;regs=[None]*32;lastwrites=[None]*32;retired=collections.deque(maxlen=32);writes=collections.deque(maxlen=40);memops=collections.deque(maxlen=24);fills=collections.deque(maxlen=40);tags=collections.deque(maxlen=16);reqs=collections.deque(maxlen=16);fault=None;error=None;intentional=False
 def v(n):
  bits=values.get(n,'x');return None if any(c in bits.lower() for c in 'xz') else int(bits,2)
 def group():
  nonlocal seen,fault
  new=dict(values);new.update(changes)
  if values.get('dclk')=='0' and new.get('dclk')=='1' and seen and v('reset')==0:
   cycle=v('cycle')
   if v('mem_is_req') and v('mem_pc') in range(0x800010a0,0x80001714):memops.append(dict(tick=stamp,cycle=cycle,**{k:v(k) for k in paths if k.startswith('mem_')}))
   if v('dc_cache_req_v_o') and v('dc_cache_req_yumi_i'):reqs.append(dict(tick=stamp,cycle=cycle,addr=v('req_addr'),msg_type=v('req_msg_type')))
   if v('dc_data_mem_pkt_v_i') and v('dc_data_mem_pkt_yumi_o') and v('dc_data_mem_slow_write'):
    fills.append(dict(tick=stamp,cycle=cycle,**{k:v(k) for k in paths if k.startswith(('pkt_','bank')) or k in ('dc_cache_req_critical_i','dc_cache_req_last_i','dc_data_mem_slow_write')}))
   if v('dc_tag_mem_pkt_v_i') and v('dc_tag_mem_pkt_yumi_o'):tags.append(dict(tick=stamp,cycle=cycle,**{k:v(k) for k in paths if k.startswith('tag_')}))
  if values.get('beclk')=='0' and new.get('beclk')=='1':
   if v('reset'):seen=True
   elif seen:
    cycle=v('cycle');pc=v('pc')
    if v('rf_rd_w_v_i') and v('rf_rd_thread_id_i')==0:
     rd=v('rf_rd_addr_i');data=v('rf_rd_data_i')
     if rd is not None and data is not None:
      e=dict(tick=stamp,cycle=cycle,rd=rd,data=data&((1<<64)-1),raw66=data,near_commit_pc=pc);regs[rd]=e['data'];lastwrites[rd]=e;writes.append(e)
    if v('instret'):retired.append(dict(tick=stamp,cycle=cycle,pc=pc))
    if v('exception') and pc==0x80001232 and fault is None:
     fault=dict(tick=stamp,cycle=cycle,pc=pc,vaddr=v('faultaddr'),registers=list(regs),last_a3_write=lastwrites[13],last_t1_write=lastwrites[6],last_a6_write=lastwrites[16],last_a7_write=lastwrites[17],retired=list(retired),writebacks=list(writes),memops=list(memops),last_fills=list(fills),last_tags=list(tags),last_requests=list(reqs))
  values.update(changes);changes.clear()
 start=time.monotonic()
 with gzip.open(out/'selected-events.tsv.gz','wt') as save,(out/'reader.stderr').open('w') as stderr:
  p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=stderr,text=True);timer=threading.Timer(90,p.kill);timer.daemon=True;timer.start()
  try:
   for line in p.stdout:
    save.write(line);f=line.rstrip('\n').split('\t')
    if f[0]=='#SIGNAL':mapping.setdefault(int(f[3]),[]).append(f[1])
    elif f[0]=='#END':group()
    elif f[0].isdigit():
     t=int(f[0])
     if stamp is not None and t!=stamp:
      group()
      if fault is not None:intentional=True;p.kill();break
     stamp=t
     for k in mapping[int(f[1])]:changes[k]=f[2]
  except BaseException as e:error=repr(e);p.kill()
  finally:rc=p.wait();timer.cancel()
 record=dict(scope='UNFINALIZED capped trace, deliberately selected prefix through first allocation exception only. No full access, completion, capacity or performance acceptance.',trace=fst,trace_unchanged=bind(fst['path'])==fst,reader=bind(reader),source=bind(__file__),selection=bind(selection),command=cmd,returncode=rc,intentionally_stopped_after_first_fault=intentional,error=error,elapsed_seconds=time.monotonic()-start,fault=fault,selected_events=bind(out/'selected-events.tsv.gz'),stderr=bind(out/'reader.stderr'))
 (out/'diagnostic.json').write_text(json.dumps(record,indent=2)+'\n')
 print('firstfault',fault and {k:fault[k] for k in ('cycle','pc','vaddr','last_a3_write','last_t1_write','last_a6_write','last_a7_write')},'reader',rc,'stopped',intentional,'error',error)

if __name__=='__main__':main()
