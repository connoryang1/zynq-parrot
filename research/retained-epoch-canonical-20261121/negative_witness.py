#!/usr/bin/env python3
"""Driver-only negative witness; reuse the frozen corrected negative RTL archive."""
from pathlib import Path
import json,shlex
from run import HERE,SRC,bind,require,run,guard
parent=HERE/'corrected-miter-02';obj=parent/'negative-clear0/obj';out=HERE/'negative-allcell-witness';require(not out.exists(),'fresh witness only');out.mkdir()
tracked=[bind(p) for p in sorted(obj.iterdir()) if p.is_file()]
src=(parent/'source/driver.cpp').read_text().replace('#include "Vretained_metadata_wrapper.h"','#include "Vretained_metadata_wrapper.h"\n#include "Vretained_metadata_wrapper___024root.h"')
needle='void eval(){d->eval();require(d->mismatch_o==0,'
extra='''void eval(){d->eval();if(d->mismatch_o){
 auto r=d->rootp;
 bool protocol=(d->lookup_ready_o!=r->retained_metadata_wrapper__DOT__ref_lookup_ready)
  ||(d->resp_v_o!=r->retained_metadata_wrapper__DOT__ref_resp_v)
  ||(d->insert_ready_o!=r->retained_metadata_wrapper__DOT__ref_insert_ready)
  ||(d->insert_done_o!=r->retained_metadata_wrapper__DOT__ref_insert_done)
  ||(d->insert_published_o!=r->retained_metadata_wrapper__DOT__ref_insert_published)
  ||(d->busy_o!=r->retained_metadata_wrapper__DOT__ref_busy)
  ||(d->epoch_wrap_o!=r->retained_metadata_wrapper__DOT__ref_epoch_wrap);
 std::fprintf(stderr,"EPOCH_NEGATIVE_WITNESS tick=%llu total=%u epochI=%u epochD=%u protocol=%u candidate_set0=%u reference_set0=%u candidate_stateD=%u reference_stateD=%u\\n",
 (unsigned long long)ticks,unsigned(d->mismatch_o),
 unsigned(r->retained_metadata_wrapper__DOT__miter__BRA__0__KET____DOT__epoch_mismatch),
 unsigned(r->retained_metadata_wrapper__DOT__miter__BRA__1__KET____DOT__epoch_mismatch),unsigned(protocol),
 unsigned(r->retained_metadata_wrapper__DOT__dut__DOT__lane_fsm__BRA__1__KET____DOT__distributed_epochs__DOT__epoch_ram__DOT__mem[0]),
 unsigned(r->retained_metadata_wrapper__DOT__reference__DOT__lane_fsm__BRA__1__KET____DOT__epochs_r[0]),
 unsigned(r->retained_metadata_wrapper__DOT__dut__DOT__lane_fsm__BRA__1__KET____DOT__state_r),
 unsigned(r->retained_metadata_wrapper__DOT__reference__DOT__lane_fsm__BRA__1__KET____DOT__state_r));
 trace->dump(ticks);
 }require(d->mismatch_o==0,'''
require(src.count(needle)==1,'unique driver witness anchor');src=src.replace(needle,extra);(out/'driver.cpp').write_text(src)
lines=(parent/'negative-clear0/build.log').read_text().splitlines();compile_argv=next(shlex.split(l) for l in lines if l.startswith('g++ ') and l.endswith('/source/driver.cpp'))
compile_argv[compile_argv.index('-o')+1]=str(out/'driver.o');compile_argv[-1]=str(out/'driver.cpp')
link=next(shlex.split(l) for l in lines if l.startswith('g++ ') and 'driver.o verilated.o' in l and ' -o ' in l);link[link.index('driver.o')]=str(out/'driver.o');link[link.index('-o')+1]=str(out/'witness')
state=dict(state='RUNNING-driver-only-negative-witness',parent=bind(parent/'session.json'),source=bind(out/'driver.cpp'),original_object_inventory=tracked,commands=[])
try:
 state['commands'].append(run(compile_argv,obj,out/'compile.log',60))
 state['commands'].append(run(link,obj,out/'link.log',60))
 state['commands'].append(run([out/'witness'],out,out/'run.log',30,True))
 text=(out/'run.log').read_text();require('EPOCH_NEGATIVE_WITNESS tick=70 total=2 epochI=0 epochD=1 protocol=0 candidate_set0=255 reference_set0=0 candidate_stateD=0 reference_stateD=0' in text,'negative explicit all-cell-only witness')
 require(tracked==[bind(p) for p in sorted(obj.iterdir()) if p.is_file()],'frozen RTL/runtime object inventory changed')
 state.update(state='PASS-expected-negative-explicit-D-epoch-allcell-witness',binary=bind(out/'witness'),trace=bind(out/'retained-line-store.fst'),log=bind(out/'run.log'),artifact_bytes=guard())
except BaseException as error:state.update(state='FAIL-preserved',error=repr(error));raise
finally:(out/'manifest.json').write_text(json.dumps(state,indent=2)+'\n');print(state['state'],flush=True)
