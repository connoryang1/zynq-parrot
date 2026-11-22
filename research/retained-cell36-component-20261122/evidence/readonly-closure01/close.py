#!/usr/bin/env python3
"""Separate read-only component closure; one missing FST header reader only."""
import argparse,copy,hashlib,importlib.util,json,os,resource,shutil,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
FAMILY=ROOT.parent
ATTEMPT=FAMILY/'attempt02'
HELPER=ATTEMPT/'helper'
sys.path.insert(0,str(HELPER))
import software_owned_v2 as owned
spec=importlib.util.spec_from_file_location('frozen_component',HELPER/'run_host.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
STAGES=[f.OLD_STAGE,f.STAGE]
RAM=Path('/dev/shm/zp-retained-cell36-ro-closure-20261121-01')
RECEIPT=ATTEMPT/'host-supervision02.json'
RECEIPT_SHA='6e25dacdf685f6f6f5f1a4246ecfb3c74f0ef3b17e75378134290e23b358fb7d'
LAST_FAILURE="ValueError('128MiB stage /64MiB aggregate family trace cap')"
TRACE_BYTES=68366449
NEW_CAP=2*1024**2
HELPER_CAP=8*1024**2
TOTAL_CAP=128*1024**2
FLOOR=512*1024**2

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def size(p):return sum(q.stat().st_size for q in p.rglob('*') if q.is_file()) if p.exists() else 0
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')
def validate_receipt(doc):
 require(doc['state']=='FAIL preserved; no retry/extension/coverage claim' and doc['error']==LAST_FAILURE,'preserve original exact budget FAIL')
 require(len(doc['commands'])==35 and len(doc['runs'])==11 and len(doc['executables'])==6,'original complete-command shape')
 commands=doc['commands'];index=0;runtime=[];missing=None
 for name,ilines,dlines,sets,epoch in f.CASES:
  out=f.STAGE/name;src=f.STAGE/'source'
  gen=[str(f.VERILATOR),'--cc','--exe','--trace-fst','--assert','-Wall','-DBP_RETAINED_METADATA_VERIFY','--top-module','retained_cell36_wrapper',
       '-GI_LINES='+str(ilines),'-GD_LINES='+str(dlines),'-GRETAINED_SETS='+str(sets),'-GEPOCH_WIDTH='+str(epoch),'-CFLAGS','-std=c++14',
       '--Mdir',str(out/'obj'),str(src/'bp_retained_line_store.sv'),str(src/'bp_retained_line_store_reference.sv'),str(src/'retained_cell36_wrapper.sv'),str(src/'driver.cpp')]
  compile=['make','-C',str(out/'obj'),'-f','Vretained_cell36_wrapper.mk','-f',str(src/'no-pch.mk'),'-j4','OBJCACHE=']
  entries=[(gen,out,120,'generate'),(compile,out,180,'compile')]
  exe=doc['executables'][name];require(exe['path']==str(out/'obj/Vretained_cell36_wrapper'),'exact unit ELF')
  for mode in ['inverted','different-periods']:
   d=out/mode;entries.append(([exe['path']]+([] if mode=='inverted' else [mode]),d,120,'runtime'))
   entries.append(([str(f.READER),str(d/'retained-line-store.fst'),'--list'],d,30,'reader'))
  for argv,cwd,timeout,kind in entries:
   if index==len(commands):
    require(name==f.CASES[-1][0] and kind=='reader','only final metadata reader missing')
    missing=dict(argv=argv,cwd=str(cwd),timeout_seconds=timeout,case=name,mode='different-periods');continue
   row=commands[index];last=index==len(commands)-1
   require(row['argv']==argv and row['cwd']==str(cwd) and row['deadline_seconds']==timeout,'exact maintained command/order')
   life=row['owned_receipt'];require(row['returncode']==life['returncode']==0 and row['owned_group_remaining'] is False and life['owned_group_remaining'] is False,'all actual command returns/owned groups')
   require(life['argv']==argv and life['group_states'][-1]['phase']=='cleanup_complete' and life['group_states'][-1]['members']==[],'actual owned cleanup receipt')
   for phase in life['group_states']:
    if phase['phase']!='normal_parent_exit_before_reap':require(not phase['members'],'no live owned member after reap')
    else:require(all(x['state']=='Z' for x in phase['members']),'normal exit had live descendants')
   if last:
    require(kind=='runtime' and name==f.CASES[-1][0] and argv[-1]=='different-periods','last error after12th runtime')
    require(row.get('failure')==life['failure']==LAST_FAILURE,'only exact post-run resource failure')
    require([x['phase'] for x in life['group_states']]==['normal_parent_exit_before_reap','normal_parent_exit_after_reap','exception_before_cleanup','cleanup_complete'],'guard failed only after normal parent exit/reap')
   else:require(row.get('failure') is None and life['failure'] is None,'no other command failure')
   if kind=='runtime':runtime.append((name,'different-periods' if argv[-1]=='different-periods' else 'inverted',row))
   index+=1
 require(index==35 and len(runtime)==12 and missing is not None,'all12 runtimes and only missing metadata')
 return runtime,missing

def header(text):
 require(text.startswith('#FST\t') and text.endswith('#END\n'),'finalized FST hierarchy EOF')
 start,end,scale=map(int,text.splitlines()[0].split('\t')[1:]);require(end>start,'nonempty closed FST')
 for leaf,width in [('clk_i',2),('reset_i',2),('mismatch_o',2),('resp_v_o',2),('resp_hit_o',2),('resp_data0_o',512),('resp_data1_o',512)]:
  rows=[line.split('\t') for line in text.splitlines() if line.startswith('#VAR\t') and line.split('\t')[-1]=='TOP.retained_cell36_wrapper.'+leaf]
  require(len(rows)==1 and int(rows[0][1])==width,'known full profile '+leaf)
 return dict(start=start,end=end,timescale=scale,clean_list_EOF=True)

def inspect_inputs():
 require(bind(RECEIPT)['sha256']==RECEIPT_SHA,'frozen original FAIL receipt')
 doc=json.loads(RECEIPT.read_text());runtime,missing=validate_receipt(doc)
 sourceproof=f.preflight(json.loads(f.A.read_text()))
 require(all(s.is_dir() for s in STAGES),'actual host namespace/stages required')
 require(not list(p for s in STAGES for p in s.rglob('*.gch')),'no PCH artifact')
 for name,rec in doc['executables'].items():
  require(bind(rec['path'])==rec and Path(rec['path']).read_bytes()[:4]==b'\x7fELF','exact completed model ELF '+name)
 for row in doc['commands']:require(bind(row['log']['path'])==row['log'],'exact actual command log')
 rows=[]
 for name,mode,row in runtime:
  text=Path(row['log']['path']).read_text()
  for marker in ['RETAINED_METADATA_MITER_PASS ','RETAINED_METADATA_HAZARDS_PASS ','RETAINED_PACKED_COLLECTOR_HAZARDS_PASS ','RETAINED_TEST_EXIT_CLEAN']:
   require(text.count(marker)==1,'complete runtime marker '+marker)
  _,ilines,dlines,sets,epoch=next(c for c in f.CASES if c[0]==name)
  for lane,lines in [(0,ilines),(1,dlines)]:require(text.count('RETAINED_CAPACITY_CHECK lane='+str(lane)+' lines='+str(lines)+' full64B=1')==1,'exact all-slot64B capacity marker')
  fst=f.STAGE/name/mode/'retained-line-store.fst';require(fst.is_file(),'closed actual FST')
  old=next((r for r in doc['runs'] if r['case']==name and r['mode']==mode),None)
  if old:require(bind(fst)==old['fst'],'first11 bound FSTs unchanged')
  rowproof=dict(case=name,mode=mode,log=bind(row['log']['path']),FST=bind(fst),runtime_returncode=0)
  existing=f.STAGE/name/(mode+'-hierarchy.tsv')
  if existing.exists():rowproof['metadata']=dict(file=bind(existing),facts=header(existing.read_text()))
  else:require(name==f.CASES[-1][0] and mode=='different-periods','only final header absent')
  rows.append(rowproof)
 trace=sum(x['FST']['bytes'] for x in rows);require(trace==TRACE_BYTES and trace>64*1024**2,'admit exact immutable trace excess, not new trace capacity')
 input_files=[]
 for stage in STAGES:
  for p in sorted(stage.rglob('*')):
   if p.is_file():require(not p.is_symlink(),'no stage symlink substitution');input_files.append(bind(p))
 source=f.STAGE/'source'
 for staged,expected in [('bp_retained_line_store.sv',f.WORKTREE/f.REL),('bp_retained_line_store_reference.sv',HELPER/'reference.sv'),('retained_cell36_wrapper.sv',HELPER/'wrapper.sv'),('driver.cpp',HELPER/'driver.cpp'),('no-pch.mk',HELPER/'no-pch.mk')]:require((source/staged).read_bytes()==expected.read_bytes(),'actual consumed source snapshot '+staged)
 return dict(original_receipt=bind(RECEIPT),original_admission=bind(f.A),sourceproof=sourceproof,rows=rows,missing=missing,immutable_stage_inventory=input_files,
             stage_bytes={str(s):size(s) for s in STAGES},family_trace_bytes=trace,prior_trace_limit_bytes=64*1024**2,trace_excess_bytes=trace-64*1024**2,PCH_artifacts=0,scope='All12 actual runtime checks complete; original aggregate trace budget FAIL remains. No new runtime authorized.')

def guard():
 old=sum(size(s) for s in STAGES);scratch=size(RAM)
 require(old+scratch<=TOTAL_CAP and scratch<=HELPER_CAP,'original128MiB family /new8MiB helper RAM cap')
 require(size(ROOT)<=NEW_CAP,'2MiB new closure output cap')
 require(size(FAMILY)+size(f.WORKTREE)<=f.HOME_CAP,'original8MiB source/helper HOME family cap')
 require(shutil.disk_usage('/dev/shm').free>=FLOOR+TOTAL_CAP-old-scratch,'512MiB floor plus remaining family allocation')
 require(shutil.disk_usage(ROOT).free>=f.HOME_RESERVE+NEW_CAP-size(ROOT),'3GiB HOME plus remaining closure allocation')
 require(not list(RAM.rglob('*.fst')) if RAM.exists() else True,'read-only closure cannot create a trace')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--execute',action='store_true');args=parser.parse_args();require(args.prepare!=args.execute,'one explicit action')
 path=ROOT/'admission.json'
 if args.prepare:
  require(not path.exists(),'preserve existing preparation')
  inputs=inspect_inputs();guard()
  a=dict(schema='cell36-readonly-composite-closure-v1',state='PREPARED READ-ONLY, root review before one missing metadata reader',source=bind(__file__),inputs=inputs,helper=bind(HELPER/'software_owned_v2.py'),reader=bind(f.READER),limits=dict(new_output_bytes=NEW_CAP,helper_RAM_bytes=HELPER_CAP,total_family_RAM_bytes=TOTAL_CAP,RAM_floor_bytes=FLOOR,reader_seconds=30,owned_cleanup_seconds=5),original_operational_budget_compliance=False,targets=0,model_executions=0,compiler_executions=0)
  save(path,a);guard();print(path,bind(path));return
 require(path.exists() and not RAM.exists() and not (ROOT/'completion.json').exists(),'one fresh read-only execution')
 a=json.loads(path.read_text());require(a['source']==bind(__file__) and a['helper']==bind(HELPER/'software_owned_v2.py') and a['reader']==bind(f.READER),'frozen closure implementation')
 require(inspect_inputs()==a['inputs'],'existing source/log/model/FST inventory drift')
 guard();RAM.mkdir();proof=dict(state='RUNNING READ-ONLY missing-metadata/source closure',admission=bind(path),original_operational_budget_compliance=False,derived_component_correctness=False,commands=[])
 def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(NEW_CAP,NEW_CAP))
 try:
  m=a['inputs']['missing'];output=ROOT/'last-hierarchy.tsv';row=dict(argv=m['argv'],cwd=m['cwd'])
  proof['commands'].append(row)
  with output.open('wb') as log:
   try:row['owned_receipt']=owned.run(m['argv'],m['cwd'],dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(RAM)),log,30,guard,limits)
   except BaseException as e:row['owned_receipt']=getattr(e,'owned_receipt',dict(owned_pgid=None,failure=repr(e),owned_group_remaining=False,scope='prePopen refusal'));raise
  require(row['owned_receipt']['returncode']==0,'only missing FST header reader failed')
  proof['last_FST_metadata']=dict(file=bind(output),facts=header(output.read_text()))
  require(inspect_inputs()==a['inputs'],'source/model/log/FST changed during read-only closure')
  guard();proof.update(state='PASS separate derived component correctness; original execution FAIL trace-budget noncompliance preserved',derived_component_correctness=True,original_operational_budget_compliance=False,source_controller_byteproof=a['inputs']['sourceproof'],no_PCH_artifacts=True,actual_family_stage_bytes=a['inputs']['stage_bytes'],immutable_trace_bytes=TRACE_BYTES,scope='Component only at stated six geometries/two clocks, not synthesis/mapping/fullcore/fit/application/FPGA; no target retry or budget extension.')
 except BaseException as e:proof.update(state='FAIL preserved read-only closure',error=repr(e));raise
 finally:save(ROOT/'completion.json',proof);print(ROOT/'completion.json',proof['state'])
if __name__=='__main__':main()
