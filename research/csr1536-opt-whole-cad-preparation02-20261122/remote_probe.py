#!/usr/bin/env python3
"""Read-only CSR1536 ExploreArea trace0 clean snapshot; CONFIG is supplied by the pinned local monitor, never a shell."""
from pathlib import Path
import datetime,hashlib,json,os,re,shutil,socket,subprocess,time
JOB=CONFIG['job']
WORK_ROOT=Path(CONFIG['work_root'])
WORK=WORK_ROOT/('zynq-parrot-fpga-'+JOB)
LOGS=Path(CONFIG['log_root'])/JOB
DESIGN=WORK/'cosim/black-parrot-example/vivado'
RUN=DESIGN/'black_parrot_bd_proj.runs/synth_1'
EXPECTED=CONFIG['expected_defines']

def volume(path):
 p=Path(path)
 while not p.exists():
  if p==p.parent:raise RuntimeError('no existing volume ancestor')
  p=p.parent
 return dict(device=p.stat().st_dev,free_bytes=shutil.disk_usage(p).free,observed_path=str(p.resolve()))
def allocated(path):
 if not path.exists():return 0
 return int(subprocess.check_output(['du','-s','-B1',str(path)],text=True).split()[0])
def resources():
 home=volume('/home/coyang');work=volume(WORK_ROOT);shm=volume('/dev/shm');source=volume(CONFIG['prepared_source_root'])
 evidence_roots=[Path(CONFIG['log_root']),Path(CONFIG['evidence_root'])]
 if any(volume(p)['device']!=home['device'] for p in evidence_roots):
  raise RuntimeError('evidence roots are not on the measured HOME filesystem')
 return dict(volumes=dict(work=work,home=home,shm=shm,source=source),source_allocated_bytes=allocated(Path(CONFIG['prepared_source_root'])),work_allocated_bytes=allocated(WORK_ROOT),evidence_allocated_bytes=sum(allocated(p) for p in evidence_roots),work_root_exists=WORK_ROOT.exists())

def binding(p):
 raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),raw.decode(errors='replace')
def source_record(p,expected):
 mode='120000' if p.is_symlink() else '100755' if p.stat().st_mode & 0o111 else '100644'
 raw=os.readlink(p).encode() if mode=='120000' else p.read_bytes()
 return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),mode=mode)

def process_table():
 rows={}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   raw=(p/'stat').read_text();f=raw[raw.rfind(')')+2:].split()
   rows[int(p.name)]=dict(pid=int(p.name),ppid=int(f[1]),pgrp=int(f[2]),sid=int(f[3]),state=f[0],startticks=int(f[19]),utime_ticks=int(f[11]),stime_ticks=int(f[12]),RSS_bytes=int(f[21])*os.sysconf('SC_PAGE_SIZE'),threads=int(f[17]),comm=(p/'comm').read_text().strip(),argv=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace'),argv_tokens=[x.decode(errors='replace') for x in (p/'cmdline').read_bytes().split(b'\0') if x])
  except (FileNotFoundError,ProcessLookupError,PermissionError,ValueError):pass
 return rows

def main():
 now=time.time();hz=os.sysconf('SC_CLK_TCK');up=float(Path('/proc/uptime').read_text().split()[0]);allprocs=process_table();owner_pid=int((LOGS/'pid').read_text().strip()) if (LOGS/'pid').exists() else -1;owner=allprocs.get(owner_pid)
 descendants={owner_pid};changed=True
 while changed:
  changed=False
  for pid,row in allprocs.items():
   if row['ppid'] in descendants and pid not in descendants:descendants.add(pid);changed=True
 result=dict(job=JOB,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),epoch=now,status=(LOGS/'status').read_text().strip() if (LOGS/'status').exists() else 'NOT_STARTED',ticks_per_second=hz,worker=owner,worker_elapsed_seconds=None if not owner else up-owner['startticks']/hz,
   descendants=[r for p,r in allprocs.items() if p in descendants],worker_group=[r for r in allprocs.values() if r['pgrp']==(owner['pgrp'] if owner else CONFIG.get('expected_worker_pid',-1))],all_vivado=[r for r in allprocs.values() if r['comm']=='vivado'],files={},reports=[],identity_violations=[],definitions=[],feature_state='PENDING childTcl',feedback_warnings=[],inference=[],milestones=[],source={},resources={},opt_state='PENDING implementation child')
 if CONFIG.get('expected_worker_startticks') is not None:result['worker_elapsed_seconds']=up-int(CONFIG['expected_worker_startticks'])/hz
 result['global_vendor_tools']=[r for r in allprocs.values() if vendor_process(r)]
 result['foreign_vendor_tools']=[r for r in result['global_vendor_tools'] if r['pid'] not in descendants]
 result['resources']=resources()
 result['hostname']=socket.gethostname()
 if result['hostname']!=CONFIG['expected_hostname']:result['identity_violations'].append(dict(kind='hostname',actual=result['hostname'],expected=CONFIG['expected_hostname']))
 result['operational_source_identity']=[]
 for relative,expected in CONFIG['operational_files'].items():
  op=Path(CONFIG['operational_root'])/relative
  if not op.is_file():result['identity_violations'].append(dict(kind='missing_operational_carrier',path=str(op)));continue
  actual=binding(op)[0];result['operational_source_identity'].append(actual)
  if actual['bytes']!=expected['bytes'] or actual['sha256']!=expected['sha256']:result['identity_violations'].append(dict(kind='operational_carrier_source',path=str(op),actual=actual,expected=expected))
 result['auxiliary_source_identity']=[]
 for expected in CONFIG['auxiliary_bindings']:
  p=Path(expected['path'])
  if not p.is_file():result['identity_violations'].append(dict(kind='missing_private_or_tool_auxiliary',expected=expected));continue
  actual=binding(p)[0];result['auxiliary_source_identity'].append(actual)
  if actual!=expected:result['identity_violations'].append(dict(kind='changed_private_or_tool_auxiliary',actual=actual,expected=expected))
 result['prepared_source_identity']=dict(verified=0,expected=len(CONFIG['prepared_source_files']))
 for relative,expected in CONFIG['prepared_source_files'].items():
  p=Path(CONFIG['prepared_source_root'])/relative
  if not (p.is_file() or p.is_symlink()):result['identity_violations'].append(dict(kind='missing_prepared_source',path=str(p)));continue
  actual=source_record(p,expected)
  if any(actual[k]!=expected[k] for k in ('bytes','sha256','mode')):result['identity_violations'].append(dict(kind='changed_prepared_source',path=str(p),actual=actual,expected=expected))
  else:result['prepared_source_identity']['verified']+=1
 result['cadenv_stub']=[]
 for p in (Path(CONFIG['prepared_source_root'])/'bsg_cadenv/cadenv.mk',WORK/'bsg_cadenv/cadenv.mk'):
  if p.is_file():
   record,_=binding(p);result['cadenv_stub'].append(record)
   if record['bytes']!=0:result['identity_violations'].append(dict(kind='unexpected_nonempty_cadenv',actual=record))
  elif str(p).startswith(CONFIG['prepared_source_root']+'/'):result['identity_violations'].append(dict(kind='missing_prepared_empty_cadenv',path=str(p)))
 result['memory_kB']={k:int(v.split()[0]) for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines()) if k in ('MemAvailable','SwapFree','SwapTotal')}
 paths=[DESIGN/'bsg_blackparrot_pkg.v',DESIGN/'bsg_blackparrot_pkg.sv',LOGS/'revisions.txt',LOGS/'console.log',LOGS/'summary.txt',DESIGN/'config.tcl',RUN/'runme.log',RUN/'vivado.tcl',RUN/'black_parrot_bd_1_wrapper.tcl',DESIGN/'black_parrot_bd_proj.xpr']
 child=RUN/'black_parrot_bd_1_wrapper.tcl'
 impl_child=DESIGN/'black_parrot_bd_proj.runs/impl_1/black_parrot_bd_1_wrapper.tcl'
 receipt=DESIGN/'implementation-selection.tsv'
 paths.extend([impl_child,receipt])
 for p in paths:
  if not p.is_file():continue
  record,text=binding(p);result['files'][str(p)]=record;lines=text.splitlines()
  if p.name in ('console.log','runme.log','summary.txt'):result.setdefault('tails',{})[str(p)]=lines[-10:]
  for number,line in enumerate(lines,1):
   if ('BP_RETAINED_' in line or 'BP_AXI_RESPONSE_DELAY' in line or 'BP_CACHE_MISS_TRACE' in line) and ('BP-EXPERIMENT-CONFIG:' in line or p in (child,DESIGN/'black_parrot_bd_proj.xpr')):result['definitions'].append(dict(path=str(p),line=number,text=line))
   if 'Synth 8-326' in line:result['feedback_warnings'].append(dict(path=str(p),line=number,text=line))
   if any(s in line for s in ('payload_mem','tag_mem','prefetch_fill_bank','epochs_r','epoch_ram','rr_r')) and not line.lstrip().startswith(('##','# ')):
    result['inference'].append(dict(path=str(p),line=number,context=lines[max(0,number-3):number+5]))
   if any(s in line for s in ('Starting Synth','Finished Synth','Start Technology','Starting Technology','Start RTL','Finished RTL','Start Part','End Part','Start Timing','Finished Timing','Start Optimization','Finished Optimization','Start Logic','Finished Logic','Start Phase','Phase ','synth_design completed','route_design completed','place_design completed','write_bitstream completed','ERROR:','CRITICAL WARNING:','BP-EXPERIMENT-CONFIG: project=black_parrot_bd_proj','CLKOUT1_REQUESTED_OUT_FREQ','PCW_FPGA0_PERIPHERAL_FREQMHZ','Multithreading enabled','set ::env(THREADS)','set ::env(ACLK','set ::env(CFG)','bp_cfg_gp','prefetch_fill_bank','posedge_clk')):result['milestones'].append(dict(path=str(p),line=number,text=line))
  if p==child and 'synth_design' in text:
   actual=actual_defines(text,EXPECTED)
   result['clean_synthesis']=clean_script(text)
   result['child_actual_features']=actual
   if all(actual[k]==[v] for k,v in EXPECTED.items()):result['feature_state']='PASS actual seven child defines'
   elif now-p.stat().st_mtime>10:
    result['feature_state']='FAIL actual child defines';result['identity_violations'].append(dict(kind='child_actual_defines',actual=actual,expected=EXPECTED))
 # Bind every generated selected-config package actually copied into the IP.
 for p in DESIGN.glob('**/bsg_blackparrot_pkg.sv'):
  record,text=binding(p);selected=re.findall(r'bp_cfg_gp\s*=\s*(\w+)',text)
  result.setdefault('selected_configuration',[]).append(dict(binding=record,selected=selected,text=text))
  if selected and selected!=['e_bp_unicore_zynqparrot_prefetch16k_cfg']:
   result['identity_violations'].append(dict(kind='generated_static_cfg',path=str(p),actual=selected))
 rev=(LOGS/'revisions.txt').read_text() if (LOGS/'revisions.txt').exists() else ''
 for key,value in {'top_commit':CONFIG['top'],'black_parrot_commit':CONFIG['bp'],'cfg':'e_bp_unicore_zynqparrot_prefetch16k_cfg','vivado_threads':'8','sparse_source':'1','cache_miss_trace':'0','opt_directive':'ExploreArea'}.items():
  actual=re.findall(r'^'+key+r'=(.*)$',rev,re.M)
  if rev and actual!=[value]:result['identity_violations'].append(dict(kind='revision_configuration',key=key,actual=actual,expected=value))
 actual_aclk=re.findall(r'^aclk_mhz=(.*)$',rev,re.M)
 if rev and actual_aclk not in (['20'],['']):result['identity_violations'].append(dict(kind='declared_core_clock',actual=actual_aclk))
 result['core_clock_authority']='Actual final clock-wizard XCI20MHz/8MHz required; empty override means committed design default, not inferred frequency.'
 # Actual final PS configuration is read as text; no Vivado property query.
 for p in list(DESIGN.glob('**/*processing_system7*.xci'))+list(DESIGN.glob('**/*clk_wiz*.xci')):
  record,text=binding(p);hits=[line.strip() for line in text.splitlines() if any(s in line for s in ('PCW_FPGA0_PERIPHERAL_FREQMHZ','PCW_FCLK0_PERIPHERAL_CLKSRC','FCLK_CLK0_FREQ','FREQ_HZ','CLKOUT1_REQUESTED_OUT_FREQ','CLKOUT2_REQUESTED_OUT_FREQ'))]
  if hits:result.setdefault('clock_configuration',[]).append(dict(binding=record,lines=hits))
 for name,repo,expected in [('top',WORK,CONFIG['top']),('bp',WORK/'import/black-parrot',CONFIG['bp'])]:
  if (repo/'.git').exists():
   head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip();result['source'][name]=head
   if head!=expected:result['identity_violations'].append(dict(kind='source_revision',repo=str(repo),actual=head,expected=expected))
 source_ready=bool(re.search(r'^black_parrot_commit=',rev,re.M))
 result['source_archive_identity']=dict(verified=0,expected=len(CONFIG['source_files']))
 for relative,expected in CONFIG['source_files'].items():
  p=WORK/relative
  if p.is_file() or p.is_symlink():
   actual=source_record(p,expected)
   if actual['mode']!=expected['mode']:result['identity_violations'].append(dict(kind='snapshot_source_mode',path=relative,actual=actual['mode'],expected=expected['mode']))
   if actual['sha256']!=expected['sha256'] or actual['bytes']!=expected['bytes']:result['identity_violations'].append(dict(kind='snapshot_source',path=relative,actual=actual,expected=expected))
   else:result['source_archive_identity']['verified']+=1
  elif source_ready:result['identity_violations'].append(dict(kind='missing_snapshot_source',path=relative))
 context_text=(LOGS/'console.log').read_text(errors='replace') if (LOGS/'console.log').exists() else ''
 result['actual_contexts']=contexts(context_text,EXPECTED)
 clocks=[]
 for p in DESIGN.glob('**/*clk_wiz*.xci'):
  record,text=binding(p);clocks.append(dict(binding=record,result=clock_match(text),final_BD=('/black_parrot_bd_proj.gen/' in str(p) or '/black_parrot_bd_proj.srcs/' in str(p))))
 result['actual_clocks']=clocks
 mature=child.is_file() and now-child.stat().st_mtime>10 and 'synth_design' in child.read_text(errors='replace')
 if mature:
  if not any(row['selected']==[CONFIG['cfg']] for row in result.get('selected_configuration',[])):result['identity_violations'].append(dict(kind='missing_actual_generated_static_configuration'))
  if not result.get('clean_synthesis',False):result['identity_violations'].append(dict(kind='nonclean_incremental_reference'))
  if not result['actual_contexts']['valid']:result['identity_violations'].append(dict(kind='actual_three_context_defines',actual=result['actual_contexts']))
  if not clocks or not any(x['final_BD'] for x in clocks) or not all(x['result']['valid'] for x in clocks):result['identity_violations'].append(dict(kind='actual_core_timer_clocks',actual=clocks))
  if result['feature_state']=='PASS actual seven child defines' and result['actual_contexts']['valid'] and clocks and any(x['final_BD'] for x in clocks) and all(x['result']['valid'] for x in clocks) and result['source_archive_identity']['verified']==result['source_archive_identity']['expected'] and not result['identity_violations']:
   result['feature_state']='PASS actual seven defines/three contexts/20MHz-8MHz/source'
 # Additional exact OPT gate, without replacing the seven-define/source gate.
 import importlib.util
 op=Path(CONFIG['opt_checks']['path']);baseline=Path(CONFIG['baseline_XPR']['path'])
 for path,expected in ((op,CONFIG['opt_checks']),(baseline,CONFIG['baseline_XPR'])):
  if not path.is_file() or binding(path)[0]!=expected:raise RuntimeError('changed exact OPT gate/baseline binding '+str(path))
 spec=importlib.util.spec_from_file_location('admitted_opt_gate',op);opt=importlib.util.module_from_spec(spec);spec.loader.exec_module(opt)
 opt_inputs=[LOGS/'revisions.txt',DESIGN/'config.tcl',receipt,LOGS/'console.log',child,impl_child,DESIGN/'black_parrot_bd_proj.xpr',baseline]
 if all(p.is_file() for p in opt_inputs) and 'route_design' in impl_child.read_text(errors='replace'):
  try:
   result['opt_verification']=opt.check_generated_text(*(p.read_text(errors='strict') for p in opt_inputs));result['opt_state']=result['opt_verification']['state']
  except Exception as e:
   result['opt_state']='FAIL actual OPT evidence';result['identity_violations'].append(dict(kind='actual_opt_only',error=repr(e)))
 candidates=set(LOGS.glob('*.rpt'))
 for folder in (RUN,DESIGN/'black_parrot_bd_proj.runs/impl_1'):
  if folder.exists():candidates.update(folder.glob('*.rpt'))
 for p in sorted(candidates):
  record,text=binding(p)
  if record['bytes']<=2*1024**2:result['reports'].append(dict(binding=record,text=text))
  else:result['reports'].append(dict(binding=record,text='OMITTED oversized report; binding retained'))
 result['run_files']={str(folder):[dict(name=p.name,bytes=p.stat().st_size) for p in folder.iterdir() if p.is_file()] for folder in (RUN,DESIGN/'black_parrot_bd_proj.runs/impl_1') if folder.exists()}
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
