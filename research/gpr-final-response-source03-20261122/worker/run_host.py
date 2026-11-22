#!/usr/bin/env python3
"""ROOT-priced GPR component generation/build/oracle only; never vendor/board.

Metadata --prepare does not allocate the native stage or launch any command.
Execution requires a distinct immutable ROOT admission/release with all OTHER
reservations priced. All original prototype files remain unchanged.
"""
import argparse, hashlib, json, os, re, resource, shutil, signal, socket, sys, time
from pathlib import Path
sys.dont_write_bytecode=True
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
PACKET=Path('/home/coyang/fpga-artifacts/context-resume/gpr-prefetch-final-borrow-preparation03-20261122/preparation01')
PRODUCTION=Path('/dev/shm/zp-linux-csr-unmasked256-fpga-source-20261122-03')
RUN=Path('/run/user/1001/zp-gpr-prefetch-borrow-component-20261122-03')
VERILATOR=Path('/home/coyang/zynq-parrot/install/bin/verilator')
VINC=Path('/home/coyang/zynq-parrot/install/share/verilator/include')
PREPARED=HERE/'prepared.json'
FINAL=HERE/'admission.ROOT.json'
PACKET_SHA='8af7890cc28d8282b2b300ed8dbd99127a306072d2a75c43bf5261b58fed96b9'
OWNER_SHA='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5'
CLAIM='ONE GPR first-copy/final-borrow component; normal+collision+two mutations; no integration or area claim'
CAP=128*1024**2
HOME_CAP=8*1024**2
SOURCE_CAP=64*1024
LIMITS=dict(native_stage_bytes=CAP,HOME_family_bytes=HOME_CAP,new_source_packet_bytes=SOURCE_CAP,
 original_source_packet_bytes=65536,wave_bytes=0,workers=2,phase_seconds=120,batch_seconds=1320,
 teardown_seconds=5,attempts=1,retries=0,extensions=0,cache=False,PCH=False,
 RUN_floor_bytes=512*1024**2,HOME_floor_bytes=2*1024**3,SHM_floor_bytes=512*1024**2,
 address_space_bytes=4*1024**3,MemAvailable_bytes=2*1024**3)
SOURCE_NAMES=['gpr_context_reference.sv','gpr_context_held.sv','gpr_prefetch_shell.sv','gpr_prefetch_miter.sv','driver.cpp']

def need(x,m):
 if not x:raise ValueError(m)

def bind(p):
 p=Path(p);h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())

def check(row):need(bind(row['path'])==row,'literal frozen input drift '+row['path'])

def save(p,o):
 tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(o,indent=2)+'\n');tmp.replace(p)

def size(p):
 return sum(x.lstat().st_size for x in p.rglob('*') if x.is_file() or x.is_symlink()) if p.exists() else 0

def verify_packet():
 need(bind(PACKET/'handoff.json')['sha256']==PACKET_SHA,'exact source-only prototype/history')
 packet=json.loads((PACKET/'handoff.json').read_text())
 for row in packet['history_inputs']:check(row)
 failure=json.loads(Path(packet['history_inputs'][1]['path']).read_text())
 need(failure['state']=='FAIL preserve all; no retries' and failure['source_endcheck']=='PASS' and failure['owned_groups_absent'] is True and failure['all_original_bytes_preserved'] is True,'preserved precompile generation failure/ownership/source closure')
 check(packet['failure02_closure_binding']);failure02=json.loads(Path(packet['failure02_closure_binding']['path']).read_text())
 need(failure02['state']=='FAIL preserve all; no retries' and failure02['source_endcheck']=='PASS' and failure02['owned_groups_absent'] is True and failure02['all_original_bytes_preserved'] is True,'exact preserved02 pre-runtime C++ failure')
 for row in packet['sources']:check(row)
 check(packet['source_contract'])
 need(size(PACKET.parent)<=LIMITS['original_source_packet_bytes'],'original whole source family cap')
 rows=[]
 for row in packet['production_sources']:
  actual=bind(PRODUCTION/row['path']);need(actual['bytes']==row['bytes'] and actual['sha256']==row['sha256'],'source-exact BP1e7 production '+row['path']);rows.append(actual)
 return packet,rows

def commands(p):
 tools=p['tools'];result=[]
 for variant,value in [('normal',0),('negative1',1),('negative2',2)]:
  obj=RUN/variant
  gen=[tools['verilator']['requested'],'--cc','--exe','--assert','--Wall','--top-module','gpr_prefetch_miter','--Mdir',str(obj),'-Gnegative_p='+str(value)]
  gen += [str(PACKET/n) for n in SOURCE_NAMES]
  make=[tools['make']['resolved'],'-C',str(obj),'-f','Vgpr_prefetch_miter.mk','-f',str(HERE/'no-pch.mk'),'-j2','OBJCACHE=','CXX='+tools['g++']['resolved'],'LINK='+tools['g++']['resolved'],'Vgpr_prefetch_miter']
  result += [dict(label=variant+'-generate',kind='generate',variant=variant,argv=gen,cwd=str(RUN)),dict(label=variant+'-build',kind='build',variant=variant,argv=make,cwd=str(RUN)),dict(label=variant+'-run',kind='run',variant=variant,argv=[str(obj/'Vgpr_prefetch_miter')]+([] if value==0 else ['--negative']),cwd=str(RUN))]
  if value==0:result.append(dict(label='normal-collision',kind='collision',variant=variant,argv=[str(obj/'Vgpr_prefetch_miter'),'--collision'],cwd=str(RUN)))
 return result

def prepare():
 need(not PREPARED.exists() and not (HERE/'admission.DRAFT.json').exists(),'fresh metadata-only prepare')
 need(Path(owned.__file__).resolve()==HERE/'software_owned_v2.py' and bind(HERE/'software_owned_v2.py')['sha256']==OWNER_SHA,'unchanged qualified owner bytes')
 packet,production=verify_packet()
 paths=[HERE/n for n in ('run_host.py','software_owned_v2.py','no-pch.mk','README.md','handoff.json')]
 paths += [PACKET/'handoff.json',Path(packet['source_contract']['path'])]+[Path(r['path']) for r in packet['sources']]+[Path(r['path']) for r in packet['history_inputs']]
 paths += [Path(r['path']) for r in production]
 tools={}
 for name,path in [('verilator',VERILATOR),('g++',Path(shutil.which('g++') or '/missing-g++')),('make',Path(shutil.which('make') or '/missing-make'))]:
  need(path.is_file(),'installed tool '+name);resolved=path.resolve();tools[name]=dict(requested=str(path),resolved=str(resolved),identity=bind(resolved));paths.extend([path,resolved])
 paths += [VERILATOR.with_name('verilator_bin')]
 # Actual installed sources used by ordinary single-threaded Verilator model.
 paths += [VINC/n for n in ('verilated.h','verilated.cpp','verilated_threads.h','verilated_threads.cpp','verilated_imp.h','verilated.mk')]
 paths += [Path(sys.executable).resolve()]
 rows=[bind(p) for p in dict.fromkeys(paths)]
 p=dict(schema='gpr-final-borrow-owned-preparation-v1',state='PREPARED SOURCE ONLY; no build or stage',stage=str(RUN),inputs=rows,tools=tools,limits=LIMITS,original_packet_sha256=PACKET_SHA,production=production)
 p['commands']=commands(p);need(len(p['commands'])==10,'fixed ten commands')
 need(size(HERE.parent)+16384<SOURCE_CAP,'new complete helper including prospective metadata <=64KiB')
 save(PREPARED,p)
 save(HERE/'admission.DRAFT.json',dict(schema='gpr-final-borrow-owned-admission-v1',ROOT_approved=False,prepared=bind(PREPARED),limits=LIMITS,linux_claim=CLAIM,ROOT_release=None,fixed_OTHER_reservations=None))
 print(json.dumps(dict(state='PREPARED no native allocation/commands',prepared=bind(PREPARED),DRAFT=bind(HERE/'admission.DRAFT.json'))))

def load(sha):
 need(sha and bind(FINAL)['sha256']==sha,'exact immutable ROOT admission')
 a=json.loads(FINAL.read_text());need(a['schema']=='gpr-final-borrow-owned-admission-v1' and a['ROOT_approved'] is True,'DRAFT cannot execute')
 need(a['limits']==LIMITS and a['linux_claim']==CLAIM and a['prepared']==bind(PREPARED),'fixed source/limits/scope')
 p=json.loads(PREPARED.read_text());need(p['stage']==str(RUN) and p['limits']==LIMITS and p['commands']==commands(p),'fixed literal native commands')
 for row in p['inputs']:check(row)
 verify_packet();check(a['ROOT_release']);release=json.loads(Path(a['ROOT_release']['path']).read_text())
 need(release['allow_GPR_owned_component'] is True and release['original_packet_sha256']==PACKET_SHA and release['linux_claim']==CLAIM and release['limits']==LIMITS,'exact ROOT native release')
 other=a['fixed_OTHER_reservations'];need(set(other)=={'RUN_bytes','HOME_bytes','SHM_bytes'} and all(type(v) is int and v>=0 for v in other.values()),'all-volume prospective OTHER templates ROOT priced')
 need(release['fixed_OTHER_reservations']==other and release['ROOT_no_foreign_producer_writes_to_GPR_roots'] is True,'ROOT artifact ownership/pricing')
 packet=json.loads((PACKET/'handoff.json').read_text());need(release['failed01_closure']==packet['history_inputs'][1],'ROOT exact preserved failure01 anchor')
 need(release['failed02_closure']==packet['failure02_closure_binding'],'ROOT exact preserved failure02 anchor')
 need(socket.gethostname()==release['actual_host'],'exact ROOT host namespace')
 return a,p

def log_gate(row,text):
 lines=[line.rstrip('\r') for line in text.splitlines()]
 need(not any(re.search(r'(?:%Warning|%Error|warning:|fatal error:|GPR_BORROW_FAIL|AddressSanitizer|runtime error:)',line) for line in lines),'warnings/source/compilation/runtime errors reject')
 if row['kind'] in ('generate','build'):return dict(no_warning_or_error=True)
 if row['kind']=='collision':
  need(lines.count('GPR_BORROW_COLLISION_REJECTED exactselectedbank')==1 and not any(line.startswith('GPR_BORROW_PASS') or line.startswith('GPR_BORROW_NEGATIVE_REJECTED') for line in lines),'exact collision rejection only')
  return dict(collision_rejected=True)
 if row['variant']!='normal':
  hits=[line for line in lines if re.fullmatch(r'GPR_BORROW_NEGATIVE_REJECTED full1024 cycle=\d+',line)]
  need(len(hits)==1 and not any(line.startswith('GPR_BORROW_PASS') for line in lines),'exact full1024 mutation rejection')
  return dict(full1024_mutation_rejected=hits[0])
 matches=[re.fullmatch(r'GPR_BORROW_PASS cycles=(\d+) checks=(\d+) reads=(\d+) writes=(\d+) installs=(\d+) launches=(\d+)',line) for line in lines]
 matches=[m for m in matches if m];need(len(matches)==1 and not any(line.startswith('GPR_BORROW_NEGATIVE_REJECTED') for line in lines),'complete exact positive marker')
 values=list(map(int,matches[0].groups()));need(values[0]>0 and values[1]>0 and values[2]>40 and values[3]>0 and values[4]>30 and values[5]>20,'all source-declared coverage counters')
 return dict(zip(('cycles','checks','reads','writes','installs','launches'),values))

def run(sha):
 a,p=load(sha);need(not RUN.exists(),'fresh one-shot native stage only');started=time.monotonic();other=a['fixed_OTHER_reservations']
 # No vendor inventory/claim: ROOT may overlap its own fully priced Vivado.
 # This worker only owns the compiler/model PG created by software_owned_v2.
 def budget():
  runbytes=size(RUN);source=size(HERE.parent);original=size(PACKET.parent);home=source+original
  need(runbytes<=CAP and source<=SOURCE_CAP and original<=65536 and home<=HOME_CAP,'complete no-exclusion stage/source/HOME caps')
  need(not any(RUN.rglob('*.fst')) and not any(RUN.rglob('*.vcd')),'no waveform creation admitted')
  need(shutil.disk_usage(RUN.parent).free>=LIMITS['RUN_floor_bytes']+CAP-runbytes+other['RUN_bytes'],'RUN floor+all remaining+OTHER')
  need(shutil.disk_usage(HERE).free>=LIMITS['HOME_floor_bytes']+HOME_CAP-home+other['HOME_bytes'],'HOME floor+all remaining+OTHER')
  need(shutil.disk_usage('/dev/shm').free>=LIMITS['SHM_floor_bytes']+other['SHM_bytes'],'SHM all fixed charges')
  mem=next(int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:'));need(mem>=LIMITS['MemAvailable_bytes'],'physical memory headroom')
  need(time.monotonic()-started<LIMITS['batch_seconds'],'fixed1320s whole native gate')
 budget();RUN.mkdir();stat=Path('/proc/self/stat').read_text();fields=stat[stat.rfind(')')+2:].split()
 state=dict(schema='gpr-final-borrow-owned-session-v1',state='RUNNING native component; no source integration',admission=bind(FINAL),prepared=bind(PREPARED),worker=dict(host=socket.gethostname(),pid=os.getpid(),pgid=os.getpgrp(),startticks=int(fields[19])),commands=[])
 def guard():
  budget();need(bind(FINAL)['sha256']==sha,'immutable authority changed')
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_AS,(LIMITS['address_space_bytes'],)*2)
 def interrupted(sig,frame):raise RuntimeError('ROOT native signal '+str(sig))
 for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,interrupted)
 env={k:v for k,v in os.environ.items() if k not in ('MAKEFLAGS','MFLAGS','GNUMAKEFLAGS','VERILATOR_ROOT','OBJCACHE','CCACHE_PREFIX','SCCACHE_DIR')}
 env.update(PYTHONDONTWRITEBYTECODE='1',CCACHE_DISABLE='1',SCCACHE_DISABLE='1',OBJCACHE='',CXX=p['tools']['g++']['resolved'],TMPDIR=str(RUN))
 state['fixed_environment']={k:env[k] for k in ('PYTHONDONTWRITEBYTECODE','CCACHE_DISABLE','SCCACHE_DISABLE','OBJCACHE','CXX','TMPDIR')}
 try:
  for specification in p['commands']:
   load(sha);guard();row=dict(specification);state['commands'].append(row);save(RUN/'session.json',state)
   with (RUN/(row['label']+'.log')).open('wb') as log:
    try:row['owned']=owned.run(row['argv'],Path(row['cwd']),env,log,120,guard,limits)
    except BaseException as e:row['owned']=getattr(e,'owned_receipt',dict(error=repr(e),scope='prePopen refusal'));raise
   need(row['owned']['returncode']==0 and row['owned']['failure'] is None and not row['owned']['owned_group_remaining'],'complete native phase/owned child closure')
   row['log']=bind(RUN/(row['label']+'.log'));row['analysis']=log_gate(row,(RUN/(row['label']+'.log')).read_text())
   if row['kind']=='generate':
    ingestion=RUN/row['variant']/'Vgpr_prefetch_miter__verFiles.dat';text=ingestion.read_text();need(all(str(PACKET/n) in text for n in SOURCE_NAMES),'actual all five frozen source ingestion');row['source_ingestion']=bind(ingestion)
    header=RUN/row['variant']/'Vgpr_prefetch_miter.h';need('VL_INW(&w_data_i,127,0,4);' in header.read_text(),'actual four32-bit input words');row['actual_header']=bind(header)
   if row['kind']=='build':
    obj=RUN/row['variant'];need(not list(obj.rglob('*.gch')) and not list(obj.rglob('*.pch')),'no PCH actual generated files');row['executable']=bind(obj/'Vgpr_prefetch_miter')
   guard();save(RUN/'session.json',state)
  need(len(state['commands'])==10,'normal generation/build/run/collision +two full negative generation/build/runs')
  state['state']='PASS GPR full1024 leaf/controller oracle, collision and both mutations; no production/area/fit claim'
 except BaseException as e:state.update(state='FAIL preserve all; no retries',error=repr(e));raise
 finally:
  for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,signal.SIG_IGN)
  try:load(sha);budget();state['source_endcheck']='PASS'
  except BaseException as e:state.update(state='FAIL literal source/end-resource check',end_error=repr(e))
  groups=[row.get('owned',{}).get('owned_pgid') for row in state['commands']];groups=[x for x in groups if x]
  remaining={str(g):owned.group_state(g) for g in groups};remaining={k:v for k,v in remaining.items() if v}
  if remaining:state.update(state='FAIL native owned group remains',remaining=remaining)
  state.update(elapsed_seconds=time.monotonic()-started,owned_groups_absent=not remaining,no_vendor_operations=True);save(RUN/'session.json',state)
 need(state['state'].startswith('PASS GPR'),'final fail-closed acceptance');print(state['state'])

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);g=ap.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--execute',action='store_true');ap.add_argument('--admission-sha256');args=ap.parse_args()
 need(bind(HERE/'software_owned_v2.py')['sha256']==OWNER_SHA,'qualified copied owner')
 if args.prepare:prepare()
 else:run(args.admission_sha256)
