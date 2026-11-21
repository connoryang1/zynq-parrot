#!/usr/bin/env python3
"""One source-unchanged sets1/disabled-I corner component check."""
import json
from pathlib import Path
from run import HERE,SRC,VERILATOR,bind,run,require,guard
out=HERE/'single-set-disabled-I';require(not out.exists(),'fresh corner only');out.mkdir()
state=dict(state='RUNNING',parent=bind(HERE/'session.json'),sources=[bind(p) for p in sorted(SRC.iterdir()) if p.is_file()],commands=[],runs=[])
try:
 argv=[VERILATOR,'--cc','--exe','--build','--trace-fst','--assert','-Wall','-DBP_RETAINED_METADATA_VERIFY','--top-module','retained_metadata_wrapper','-GI_LINES=0','-GD_LINES=3','-GRETAINED_SETS=1','-GEPOCH_WIDTH=2','-CFLAGS','-std=c++14','-j','1','-MAKEFLAGS','VM_PARALLEL_BUILDS=0','--Mdir',out/'obj',SRC/'bp_retained_epoch_ram.sv',SRC/'bp_retained_line_store.sv',SRC/'bp_retained_line_store_reference.sv',SRC/'retained_metadata_wrapper.sv',SRC/'driver.cpp']
 state['commands'].append(run(argv,out,out/'build.log',300))
 for mode in ('inverted','different-periods'):
  runtime=out/mode;runtime.mkdir();entry=run([out/'obj/Vretained_metadata_wrapper']+([] if mode=='inverted' else [mode]),runtime,out/('run-'+mode+'.log'),120)
  text=(out/('run-'+mode+'.log')).read_text();require('RETAINED_METADATA_MITER_PASS I=0 D=3 SETS=1' in text and 'RETAINED_TEST_EXIT_CLEAN' in text and 'RETAINED_METADATA_HAZARDS_PASS' in text,'complete corner markers')
  state['runs'].append(dict(entry,mode=mode,fst=bind(runtime/'retained-line-store.fst')))
 require(state['sources']==[bind(p) for p in sorted(SRC.iterdir()) if p.is_file()],'frozen candidate drift');state.update(state='PASS-single-set-dense-D-disabled-I-both-clocks',artifact_bytes=guard())
except BaseException as error:state.update(state='FAIL-preserved',error=repr(error));raise
finally:(out/'manifest.json').write_text(json.dumps(state,indent=2)+'\n');print(state['state'],flush=True)
