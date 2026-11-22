#!/usr/bin/env python3
"""Thin explicit1792 adapter over the source-bound qualified eleven-phase gate."""
import importlib.util,json,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
import materialize as source,budget
HERE=Path(__file__).resolve().parent;PREVIOUS=source.PREVIOUS
spec=importlib.util.spec_from_file_location('qualified256_fullcore',PREVIOUS/'run_full.py');qualified=importlib.util.module_from_spec(spec);spec.loader.exec_module(qualified)
qualified.HERE=HERE
# Geometry script is already parameterized; no source patch or old-root RTL use.
qualified.GENERATED_GEOMETRY=Path('/home/coyang/zynq-parrot-retained-dense/research/retained-maintenance-acyclic-20261121/bind_geometry.py')
old_commands=qualified.commands
def commands():
 return [('VERILATOR=python3 '+str(PREVIOUS/'verilator_no_pch.py')+' --assert') if v.startswith('VERILATOR=') else v for v in old_commands()]
qualified.commands=commands
def validate_selection(path,sha):
 need=source.require;bind=source.bind;need(bind(path)['sha256']==sha,'exact new ROOT1792 software/source selection')
 a=json.loads(Path(path).read_text());need(a['schema']=='csr-unmasked1792-fullcore-v1' and a['TOP']==source.TOP and a['BP']==source.BP,'exact capacity-only TOP/BP')
 need(a['lines']==1792 and a['geometry']==dict(sets=256,epoch=8,line_bytes=64,l1_i_bytes=32768,l1_d_bytes=32768,l2_bytes=16384,resident=2,logical=4,aclk_mhz=20,delay=0),'all unchanged ordinary/retained topology except line count')
 need(a['workers']==8 and a['cache']=='off' and a['PCH']=='off','eightjobs/cacheoff/PCHoff')
 rec=source.verify();need(bind(budget.BASE/'source-preparation.json')==a['source_preparation'],'actual private source receipt')
 proof=json.loads(Path(a['software_proof']['path']).read_text());need(bind(a['software_proof']['path'])==a['software_proof'],'exact accepted1792 software proof')
 need(proof['expected']==dict(i_lines=1792,d_lines=1792,sets=256) and proof['topology']==dict(resident=2,logical=4),'accepted software matches physical/logical topology')
 need(all(v in proof['actual_gcc_argv'] for v in ['-DNUM_THREADS=2','-DBP_NUM_THREADS=2','-DBP_NUM_CONTEXTS=4','-DBP_EXPECT_I_LINES=1792','-DBP_EXPECT_D_LINES=1792','-DBP_EXPECT_RETAINED_SETS=256']),'exact old1792 macros/flags')
 need(a['programs']==proof['programs'],'unchanged known-good1792 integrity/cold08 pair')
 for role in ('integrity','advisory'):
  for name in ('elf','nbf'):need(bind(a['programs'][role][name]['path'])==a['programs'][role][name],'actual immutable guest bytes')
 need(a['programs']['integrity']['elf']['sha256']=='6dc1d67b880e85d9841c8a2ae5fc86043e2944f2925e5384c6edb8416dfc1277' and a['programs']['integrity']['nbf']['sha256']=='f856b599e14a1567c836b621d80581c533fbeec6955516ebbd6c157891cda9d9','exact prior1792 loaded program')
 need(a['programs']['advisory']['elf']['sha256']=='3fe096173e3a63b2656c1fadf0a058a328fb5f1ee375be652176408856f897b8' and a['programs']['advisory']['nbf']['sha256']=='627662f775f9c2645e5b5687a9df3bfaed25d42265e125a0386047ebe1daad4b','same cold08')
 need(bind(source.GHOST)==a['integration_contract'],'same qualified1754 ghost')
 need(source.git(source.SOURCE,'diff','--name-only','a44c03bb7bc520a3b5727c2bb619a055a7ed5acd',source.TOP).decode().splitlines()==['cosim/black-parrot-example/Makefile.design'],'only capacity defaults change')
 need(qualified.module('strict1792_literal_root',qualified.STRICT).ROOT==source.SOURCE,'strict literal new source root, no old-root mismatch')
 return a
qualified.validate_selection=validate_selection
if __name__=='__main__':
 # Child build must not inherit source/FPGA/NUM/CFG or Git role variables.
 for key in list(os.environ):
  if key.startswith(('GIT_','FPGA_','BP_')) or key in ('NUM_THREADS','NUM_CONTEXTS','CFG'):os.environ.pop(key)
 qualified.main()
 if '--execute' in sys.argv:
  path=budget.BASE/'full01/session.json';record=json.loads(path.read_text());source.require(record['state']=='PASS CSR unmasked256 trace0 clean fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-geometry-source-audits' and record['geometry']['i_lines']==1792 and record['geometry']['d_lines']==1792 and record['source_tree_baseline']==source.TOP,'inherited gate exact1792 result')
  record.update(state='PASS CSR1792 complete eleven-phase native integrity/cold08; scoped/STD/all1792 pending',inherited_qualified_receipt=source.bind(path),inherited_label_scope='Original helper label retained unchanged in original receipt; this adapter binds actual1792geometry and newTOP/BP explicitly')
  out=budget.BASE/'full01/adapter-session.json';out.write_text(json.dumps(record,indent=2)+'\n');budget.check();print(out)
