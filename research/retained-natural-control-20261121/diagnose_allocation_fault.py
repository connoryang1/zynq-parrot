#!/usr/bin/env python3
"""Recover allocation exception kind/address from the failed partial FST only."""
import gzip,json,subprocess,threading,time
from pathlib import Path
from prepare import bind,ROOT,HERE


def main():
 out=HERE/'failed-allocation-fault01';out.mkdir(exist_ok=False)
 m=json.loads((HERE/'cohort01/cohort.json').read_text());fst=m['runs'][0]['trace'];assert bind(fst['path'])==fst
 core='TOP.bsg_nonsynth_zynq_testbench.dut.top_fpga_inst.blackparrot.processor.u.unicore.unicore_lite';be=core+'.core_minimal.be';csr=be+'.calculator.pipe_sys.csr.gen_csr[0].csr_inst'
 paths={'clock':be+'.clk_i','reset':be+'.reset_i','cycle':be+'.calculator.pipe_sys.csr.global_cycle_r','pc':be+'.commit_pkt.pc','exception':be+'.commit_pkt.exception','npc':be+'.commit_pkt.npc','vaddr':be+'.commit_pkt.vaddr','debug':csr+'.debug_mode_r'}
 for n in ['load_misaligned','load_page_fault','load_access_fault','illegal_instr','store_misaligned','store_page_fault','store_access_fault','instr_misaligned','instr_access_fault','instr_page_fault','ebreak']:
  paths[n]=csr+'.retire_pkt_cast_i.exception.'+n
 selection=out/'selection.tsv';selection.write_text(''.join(k+'\t'+p+'\n' for k,p in paths.items()));reader=ROOT/'research/retained-system-geometry-20261121/reader/fst_events';cmd=[str(reader),fst['path'],str(selection.resolve())]
 mapping={};values={};changes={};stamp=None;events=[];err=None;end=False
 def number(n):
  raw=values.get(n,'x');return None if any(c in raw.lower() for c in 'xz') else int(raw,2)
 def group():
  new=dict(values);new.update(changes)
  if values.get('clock')=='0' and new.get('clock')=='1' and number('reset')==0 and number('cycle') is not None and number('cycle')>=100000 and number('exception'):
   events.append(dict(tick=stamp,**{k:number(k) for k in paths if k not in ('clock','reset')}))
  values.update(changes);changes.clear()
 start=time.monotonic()
 with gzip.open(out/'selected-events.tsv.gz','wt') as saved,(out/'reader.stderr').open('w') as stderr:
  p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=stderr,text=True);timer=threading.Timer(90,p.kill);timer.daemon=True;timer.start()
  try:
   for line in p.stdout:
    saved.write(line);f=line.rstrip('\n').split('\t')
    if f[0]=='#SIGNAL':mapping.setdefault(int(f[3]),[]).append(f[1])
    elif f[0]=='#END':group();end=True
    elif f[0].isdigit():
     t=int(f[0])
     if stamp is not None and t!=stamp:group()
     stamp=t
     for k in mapping[int(f[1])]:changes[k]=f[2]
   if changes:group()
  except BaseException as e:err=repr(e);p.kill()
  finally:rc=p.wait();timer.cancel()
 record=dict(scope='Recovered prefix of interrupted/unfinalized FST; allocation exception diagnosis only, no accepted coverage/performance.',trace=fst,trace_unchanged=bind(fst['path'])==fst,reader=bind(reader),source=bind(__file__),command=cmd,selection=bind(selection),events=events,returncode=rc,end_marker=end,error=err,elapsed_seconds=time.monotonic()-start,selected_events=bind(out/'selected-events.tsv.gz'))
 (out/'diagnostic.json').write_text(json.dumps(record,indent=2)+'\n');print('partial exception events',len(events),'first',events[:1],'last',events[-1:])

if __name__=='__main__':main()
