#!/usr/bin/env python3
"""Second bounded read-only UNFINALIZED diagnostic: initial control/redirects."""
import collections,gzip,json,subprocess,threading,time
from pathlib import Path
from prepare import bind,ROOT,HERE


def main():
 out=HERE/'failed-control-diagnostic01';out.mkdir(exist_ok=False)
 m=json.loads((HERE/'cohort01/cohort.json').read_text());fst=m['runs'][0]['trace'];assert bind(fst['path'])==fst
 spec=json.loads((HERE/'retention-selection.json').read_text())['fields'];keys=['be_clock','be_reset','global_cycle','instret','pc','retained_status','retained_control_cmd_v','retained_control_cmd','retained_control_r','store_clear_i','store_busy_o','retained_uce_idle'];paths={k:spec[k]['path'] for k in keys}
 core=paths['retained_status'].rsplit('.',1)[0];be=core+'.core_minimal.be';csr=be+'.calculator.pipe_sys.csr.gen_csr[0].csr_inst'
 for n in ['exception','npc_w_v','npc','priv_n','_interrupt']:paths['commit_'+n]=be+'.commit_pkt.'+n
 for n in ['priv_mode_r','debug_mode_r','is_m_mode','csr_w_v_li','csr_addr_li','csr_data_li','csr_data_lo','mcause_lo.ecode','mcause_lo._interrupt']:
  paths['csr_'+n.replace('.','_')]=csr+'.'+n
 for n in ['illegal_instr','ecall_m','ecall_s','ecall_u','load_access_fault','store_access_fault']:
  paths['exception_'+n]=csr+'.retire_pkt_cast_i.exception.'+n
 for lane,p in [('i','icache_uce'),('d','dcache_uce')]:
  for n in ['retained_idle_o','state_r','credit_count_lo']:paths[lane+'_'+n]=core+'.'+p+'.'+n
 selection=out/'selection.tsv';selection.write_text(''.join(k+'\t'+p+'\n' for k,p in paths.items()))
 reader=ROOT/'research/retained-system-geometry-20261121/reader/fst_events';cmd=[str(reader),fst['path'],str(selection.resolve())]
 values={};changes={};mapping={};stamp=None;reset_seen=False;events=[];tail=collections.deque(maxlen=12);hist=collections.Counter();pc_counts=collections.Counter();cmds=0;clear_cycles=[0,0];retired=0;error=None;ended=False
 def v(name):
  bits=values.get(name,'x')
  if any(c in bits.lower() for c in 'xz'):return None
  return int(bits,2)
 def group():
  nonlocal reset_seen,cmds,retired
  new=dict(values);new.update(changes)
  if values.get('be_clock')=='0' and new.get('be_clock')=='1':
   if v('be_reset'):reset_seen=True
   elif reset_seen:
    cycle=v('global_cycle');pc=v('pc')
    if v('retained_control_cmd_v'):cmds+=1
    clear=v('store_clear_i')
    if clear is not None:
     for lane in range(2):clear_cycles[lane]+=(clear>>lane)&1
    if v('instret'):
     retired+=1;pc_counts[pc]+=1
     if pc==0x80000f60:hist[(v('retained_status'),v('store_busy_o'),v('retained_uce_idle'),v('store_clear_i'),v('csr_debug_mode_r'))]+=1
    if v('commit_exception') or v('commit__interrupt') or (v('instret') and pc in (0x80000236,0x8000029c)):
     e={k:v(k) for k in paths if k not in ('be_clock','be_reset')};e['tick']=stamp;e['pc']=hex(pc) if pc is not None else None
     if len(events)<180:events.append(e)
    if v('instret') and pc==0x80000f60:tail.append({k:v(k) for k in paths if k not in ('be_clock','be_reset')})
  values.update(changes);changes.clear()
 start=time.monotonic()
 with gzip.open(out/'selected-events.tsv.gz','wt') as save,(out/'reader.stderr').open('w') as err:
  p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=err,text=True);timer=threading.Timer(120,p.kill);timer.daemon=True;timer.start()
  try:
   for line in p.stdout:
    save.write(line);f=line.rstrip('\n').split('\t')
    if f[0]=='#SIGNAL':mapping.setdefault(int(f[3]),[]).append(f[1])
    elif f[0]=='#END':group();ended=True
    elif f[0].isdigit():
     t=int(f[0])
     if stamp is not None and t!=stamp:group()
     stamp=t
     for k in mapping[int(f[1])]:changes[k]=f[2]
   if changes:group()
  except BaseException as e:error=repr(e);p.kill()
  finally:rc=p.wait();timer.cancel()
 record=dict(scope='UNFINALIZED interrupted writer; recovered selected prefix diagnostic ONLY, not completion/performance/full-access acceptance.',trace=fst,trace_unchanged=bind(fst['path'])==fst,reader=bind(reader),source=bind(__file__),selection=bind(selection),command=cmd,reader_returncode=rc,end_marker=ended,error=error,elapsed_seconds=time.monotonic()-start,
             control_command_sample_cycles=cmds,clear_active_be_sample_cycles=clear_cycles,visible_retired=retired,
             poll_status_histogram=[dict(raw_status=hex(k[0]) if k[0] is not None else None,backend_busy=k[1],uce_idle=k[2],clear=k[3],debug=k[4],samples=n) for k,n in hist.items()],label_exception_interrupt_events=events,poll_tail=list(tail),selected_events=bind(out/'selected-events.tsv.gz'),stderr=bind(out/'reader.stderr'))
 (out/'diagnostic.json').write_text(json.dumps(record,indent=2)+'\n');print('diagnostic',rc,ended,'commands',cmds,'clear',clear_cycles,'pollstates',record['poll_status_histogram'],'events',len(events))

if __name__=='__main__':main()
