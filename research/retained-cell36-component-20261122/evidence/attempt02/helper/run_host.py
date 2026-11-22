#!/usr/bin/env python3
"""Bounded root-host component family; no fullcore, vendor or board launcher."""
import argparse,gzip,hashlib,json,os,resource,shutil,signal,subprocess,time
import software_owned_v2 as owned
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
A=ROOT/'admission.json'
STAGE=Path('/dev/shm/zp-retained-cell36-unit-20261121-02')
OLD_STAGE=Path('/dev/shm/zp-retained-cell36-unit-20261121-01')
FAMILY_HOME=ROOT.parent
RECEIPT=ROOT/'host-supervision02.json'
WORKTREE=Path('/home/coyang/bp-retained-cell36-packing-20261121')
REL='bp_common/src/v/bp_retained_line_store.sv'
BASE='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c'
VERILATOR=Path('/home/coyang/zynq-parrot/install/bin/verilator')
READER=Path('/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121/fst-reader/fst_events')
CASES=[('lines1792',1792,1792,256,8),('lines1856',1856,1856,256,8),
       ('lines1911',1911,1911,256,8),('lines1920',1920,1920,256,8),
       ('sparse-unequal',93,131,256,2),('disabled-I-dense16cells',0,3,1,2)]
CAP=128*1024**2
TRACE_CAP=64*1024**2
HOME_CAP=8*1024**2
HOME_RESERVE=3*1024**3
RAM_RESERVE=512*1024**2
LIMITS=dict(stage_bytes=CAP,family_FST_bytes=TRACE_CAP,HOME_source_helper_bytes=HOME_CAP,
            HOME_reserve_bytes=HOME_RESERVE,RAM_reserve_bytes=RAM_RESERVE,
            build_seconds=300,generation_seconds=120,compile_seconds=180,run_seconds=120,owned_cleanup_seconds=5,workers=4,PCH=False,compiler_cache=False)
state=None

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def save(p,o):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(o,indent=2)+'\n');t.replace(p)
def command(argv,cwd=None):return subprocess.check_output(argv,cwd=cwd,text=True).strip()
def size(p):return sum(x.stat().st_size for x in p.rglob('*') if x.is_file()) if p.exists() else 0
def guard():
 used=size(STAGE)+size(OLD_STAGE);traces=sum(p.stat().st_size for d in [OLD_STAGE,STAGE] if d.exists() for p in d.rglob('*.fst'))
 home=size(FAMILY_HOME)+size(WORKTREE)
 require(used<=CAP and traces<=TRACE_CAP,'128MiB stage /64MiB aggregate family trace cap')
 require(home<=HOME_CAP,'8MiB combined HOME source/helper cap')
 require(shutil.disk_usage('/dev/shm').free>=RAM_RESERVE+CAP-used,'512MiB RAM floor plus remaining allocation')
 require(shutil.disk_usage(ROOT).free>=HOME_RESERVE+HOME_CAP-home,'3GiB HOME floor plus remaining allocation')
 return dict(stage_bytes=used,family_FST_bytes=traces,HOME_source_helper_bytes=home)
def unchanged_controller(original,candidate):
 old=original.decode();new=candidate.decode()
 old=old[old.index('    localparam int ways_lp'):]
 for declaration in ['    logic [tag_width_lp-1:0] ptag_r;\n','    logic [epoch_width_p-1:0] insert_epoch_r;\n','    logic [511:0] insert_data_r;\n']:
  require(old.count(declaration)==1,'unique original register declaration');old=old.replace(declaration,'')
 end=new.index('\n/* verilator lint_off DECLFILENAME */\n/* Canonical no-reset one-write validity storage')
 new=new[new.index('    localparam int ways_lp'):end]
 start=new.index('              // Only hit responses define payload.')
 finish=new.index('              if (word_r == 3\'d7) begin state_r',start)
 new=new[:start]+"              resp_data_r[int'(word_r)*64+:64] <= data_rdata[lane];\n"+new[finish:]
 require(old.rstrip()==new.rstrip(),'FSM/epochs/RR/handshake changed beyond collector and declaration moves')
 return True

def preflight(a):
 require(a['schema']=='retained-cell36-component-attempt02-v1' and a['stage']==str(STAGE),'fixed admission/stage')
 require(a['cases']==[list(c) for c in CASES] and a['limits']==LIMITS,'fixed full family/budgets')
 for rec in a['inputs']:require(bind(rec['path'])==rec,'input drift '+rec['path'])
 require((WORKTREE/'.git').is_file(),'real BP worktree')
 require(command(['git','rev-parse','HEAD'],WORKTREE)==BASE,'exact BP8df base')
 require(command(['git','branch','--show-current'],WORKTREE)==a['branch'],'dedicated branch')
 require(command(['git','diff','--name-only','HEAD'],WORKTREE).splitlines()==[REL],'one allowed production file')
 require(not command(['git','ls-files','--others','--exclude-standard'],WORKTREE),'untracked BP source')
 command(['git','diff','--check'],WORKTREE)
 original=command(['git','show',BASE+':'+REL],WORKTREE).encode()+b'\n'
 require(original==(HERE/'baseline-8df.sv.txt').read_bytes(),'exact 8df source snapshot')
 old_candidate=Path(a['prior_candidate_snapshot']['path']).read_bytes()
 require((WORKTREE/REL).read_bytes()==old_candidate.replace(b"int'(local_data_addr >> 3)",b"(int'(local_data_addr) >> 3)"),'single explicit cast correction only')
 prior=json.loads(Path(a['prior_receipt']['path']).read_text())
 require(prior['state'].startswith('FAIL preserved') and len(prior['commands'])==1 and not prior['runs'],'prior generation-only failure preserved')
 require(prior['commands'][0]['returncode']==1 and prior['commands'][0]['owned_group_remaining'] is False,'prior failed generation ownership')
 unchanged_controller(original,(WORKTREE/REL).read_bytes())
 ref=original.replace(b'module bp_retained_line_store\n',b'module bp_retained_line_store_reference\n').replace(b'bp_retained_epoch_ram',b'bp_retained_epoch_ram_reference')
 require(ref==(HERE/'reference.sv').read_bytes(),'reference module names only')
 for rec in a['consumer_sources']:
  raw=gzip.decompress(Path(rec['snapshot']['path']).read_bytes())
  expected=subprocess.check_output(['git','show',BASE+':'+rec['relative']],cwd=WORKTREE)
  require(raw==expected and hashlib.sha256(raw).hexdigest()==rec['original_sha256'],'exact actual consumer source')
 s=(HERE/'wrapper.sv').read_text();cpp=(HERE/'driver.cpp').read_text()
 require('if (resp_hit_o[l]) mismatch_o[l] |=' in s,'all512 hit-data comparison')
 require("mismatch_o[l] |= {dut.tag_v[l]" in s,'logical memory-intent miter retained')
 require('rootp' not in cpp and '___024root' not in cpp,'C++ uses explicit wrapper ports only')
 require('d->trace(trace.get(),99)' in cpp,'known full trace profile')
 candidate=(WORKTREE/REL).read_text()
 require(candidate.count('module bp_retained_epoch_ram\n')==1 and candidate.count('module bp_retained_valid_ram\n')==1,'no duplicate helpers')
 require(candidate.count('cell_mem[cell_addr[0]] <=')==candidate.count('cell_mem[cell_addr[1]] <=')==1,'two real cell writers')
 return dict(state='PASS source-only preflight; no component executed',candidate=bind(WORKTREE/REL),baseline=bind(HERE/'baseline-8df.sv.txt'),cases=len(CASES),expected_runtimes=2*len(CASES))
def checkpoint():
 save(STAGE/'session.json',state);save(RECEIPT,state)
def run(argv,cwd,log,seconds,runtime=False):
 row=dict(argv=list(map(str,argv)),cwd=str(cwd),deadline_seconds=seconds)
 state['commands'].append(row);checkpoint();t=time.monotonic()
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));n=TRACE_CAP if runtime else CAP
  resource.setrlimit(resource.RLIMIT_FSIZE,(n,n))
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(STAGE/'tmp'),VERILATOR_ROOT='/home/coyang/zynq-parrot/install/share/verilator',OBJCACHE='',CCACHE_DISABLE='1',SCCACHE_DISABLE='1')
 for key in ['CC','CXX','AR','MAKE','CXXFLAGS','CPPFLAGS','LDFLAGS','MAKEFLAGS','MFLAGS']:env.pop(key,None)
 env['PATH']='/usr/bin:/bin'
 try:
  with log.open('wb') as stream:
   row['owned_receipt']=owned.run(row['argv'],cwd,env,stream,seconds,guard,limits)
  require(row['owned_receipt']['returncode']==0,'component command failed '+str(log))
 except BaseException as e:
  row.setdefault('owned_receipt',getattr(e,'owned_receipt',dict(argv=row['argv'],owned_pgid=None,returncode=None,failure=repr(e),owned_group_remaining=False,group_states=[],reaped_owned_children=[],scope='refused before Popen/no child ownership created')))
  row['failure']=repr(e);raise
 finally:
  life=row['owned_receipt']
  row.update(seconds=time.monotonic()-t,log=bind(log) if log.exists() else None,returncode=life['returncode'],owned_pgid=life['owned_pgid'],owned_group_remaining=life['owned_group_remaining'])
  checkpoint()
 return row

def main():
 global state
 p=argparse.ArgumentParser();p.add_argument('--preflight',action='store_true');p.add_argument('--execute',action='store_true');args=p.parse_args()
 require(args.preflight!=args.execute,'one explicit action')
 a=json.loads(A.read_text());proof=preflight(a)
 if args.preflight:print(json.dumps(proof,indent=2));return
 # Actual ROOT namespace sentinel is read-only. Never allocate in agent-private RAM.
 sentinel=Path('/dev/shm/zp-linux-canonical-fulltop-20261121-01')
 require((sentinel/'.git').is_file() and command(['git','rev-parse','HEAD'],sentinel)=='eb7d390134a0025331a2366a979a774263b146d5','actual host source namespace')
 require(not STAGE.exists() and not RECEIPT.exists(),'one fresh attempt only')
 require(OLD_STAGE.is_dir(),'failed stage01 must remain preserved')
 old=json.loads(Path(a['prior_receipt']['path']).read_text())
 require(bind(old['commands'][0]['log']['path'])==old['commands'][0]['log'],'failed strict-WIDTHEXPAND log changed')
 require((OLD_STAGE/'source/bp_retained_line_store.sv').read_bytes()==Path(a['prior_candidate_snapshot']['path']).read_bytes(),'failed actual candidate snapshot changed')
 guard();STAGE.mkdir();(STAGE/'tmp').mkdir();(STAGE/'source').mkdir()
 state=dict(state='RUNNING component-only family',admission=bind(A),preflight=proof,stage=str(STAGE),commands=[],runs=[],no_model_or_vendor_or_board=True)
 def stopped(sig,frame):raise RuntimeError('interrupted by signal '+str(sig))
 for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,stopped)
 checkpoint()
 try:
  shutil.copyfile(WORKTREE/REL,STAGE/'source/bp_retained_line_store.sv')
  for name,target in [('reference.sv','bp_retained_line_store_reference.sv'),('wrapper.sv','retained_cell36_wrapper.sv'),('driver.cpp','driver.cpp'),('no-pch.mk','no-pch.mk')]:shutil.copyfile(HERE/name,STAGE/'source'/target)
  for name,ilines,dlines,sets,epoch in CASES:
   out=STAGE/name;out.mkdir()
   argv=[VERILATOR,'--cc','--exe','--trace-fst','--assert','-Wall','-DBP_RETAINED_METADATA_VERIFY','--top-module','retained_cell36_wrapper',
         '-GI_LINES='+str(ilines),'-GD_LINES='+str(dlines),'-GRETAINED_SETS='+str(sets),'-GEPOCH_WIDTH='+str(epoch),'-CFLAGS','-std=c++14',
         '--Mdir',out/'obj',STAGE/'source/bp_retained_line_store.sv',STAGE/'source/bp_retained_line_store_reference.sv',STAGE/'source/retained_cell36_wrapper.sv',STAGE/'source/driver.cpp']
   run(argv,out,out/'generate.log',120)
   run(['make','-C',out/'obj','-f','Vretained_cell36_wrapper.mk','-f',STAGE/'source/no-pch.mk','-j4','OBJCACHE='],out,out/'compile.log',180)
   require(not list(STAGE.rglob('*.gch')),'unexpected PCH artifact')
   exe=out/'obj/Vretained_cell36_wrapper';state.setdefault('executables',{})[name]=bind(exe)
   for mode in ['inverted','different-periods']:
    d=out/mode;d.mkdir();row=run([exe]+([] if mode=='inverted' else [mode]),d,out/(mode+'.log'),120,True)
    text=Path(row['log']['path']).read_text()
    for marker in ['RETAINED_METADATA_MITER_PASS ','RETAINED_METADATA_HAZARDS_PASS ','RETAINED_PACKED_COLLECTOR_HAZARDS_PASS ','RETAINED_TEST_EXIT_CLEAN']:
     require(text.count(marker)==1,'missing complete runtime marker '+marker)
    fst=d/'retained-line-store.fst';row.update(case=name,mode=mode,fst=bind(fst))
    run([READER,fst,'--list'],d,out/(mode+'-hierarchy.tsv'),30)
    hier=(out/(mode+'-hierarchy.tsv')).read_text();require(hier.startswith('#FST\t') and hier.endswith('#END\n'),'finalized FST header/EOF')
    for leaf,width in [('clk_i',2),('reset_i',2),('mismatch_o',2),('resp_v_o',2),('resp_hit_o',2),('resp_data0_o',512),('resp_data1_o',512)]:
     matches=[l.split('\t') for l in hier.splitlines() if l.startswith('#VAR\t') and l.split('\t')[-1]=='TOP.retained_cell36_wrapper.'+leaf]
     require(len(matches)==1 and int(matches[0][1])==width,'full-profile clock/control/hit-data leaf '+leaf)
    state['runs'].append(row);checkpoint()
  require(len(state['runs'])==2*len(CASES),'complete fixed family')
  state['final_source_check']=preflight(a);require(bind(A)==state['admission'],'admission drift')
  state.update(state='PASS component full-cycle-defined-client/full512-hit/logical-intent/coherence family',resources=guard())
 except BaseException as e:state.update(state='FAIL preserved; no retry/extension/coverage claim',error=repr(e));raise
 finally:checkpoint();print(RECEIPT,state['state'],flush=True)
if __name__=='__main__':main()
