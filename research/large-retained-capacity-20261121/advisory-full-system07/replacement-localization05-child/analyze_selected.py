#!/usr/bin/env python3
"""Offline original07 warm-up replacement/retirement localization; no target run."""
import collections,gzip,hashlib,importlib.util,json
from pathlib import Path
ROOT=Path('/home/coyang/zynq-parrot-linux-capacity')
BASE=ROOT/'research/large-retained-capacity-20261121/advisory-full-system07'
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('advisory_validate',ROOT/'testing/rtl/retained-advisory-trace/validate.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
selected=BASE/'trace-audit03-child/selected-events.tsv.gz'
refills=[];tags=[];retired=collections.Counter();functions=collections.Counter();queries=[]
seen={};begin=62075000
with gzip.open(selected,'rt') as stream:
 for t,clocks,s in v.edge_samples(stream):
  if t<=begin:continue
  if 'be.clk' in clocks and not s['be.reset'] and s['be.instret']:
   pc=s['be.pc'];retired[pc]+=1
   if 0x80001000<=pc<0x8000b000 and (pc&4095)<64:
    functions[(pc-0x80001000)//4096]+=1
  for lane,target in [('i',v.CODE),('d',v.DATA)]:
   if lane+'.bclk' in clocks and not s[lane+'.breset'] and s[lane+'.lv'] and s[lane+'.lr']:
    queries.append({'time':t,'lane':lane,'address':s[lane+'.la']})
   if lane+'.cclk' not in clocks or s[lane+'.creset']:continue
   g=lambda k:s[lane+'.'+k]
   if g('tv') and g('ty') and g('tag.opcode')==1 and g('tag.index')==0:
    tags.append({'time':t,'lane':lane,'address':g('tag.tag')<<12,'way':g('tag.way_id'),'state':g('tag.state'),'uce_state':g('state'),'control':s['control']})
   if g('v') and g('yumi') and g('pkt.opcode')==0 and g('pkt.fill_index')==1 and g('pkt.index')==0:
    address=g('pkt.addr')&~63
    if target<=address<=target+9*4096:
     aborted=lane=='i' and any(g(k) for k in ['abort_miss','abort_miss_r','miss_abort_i'])
     refills.append({'time':t,'lane':lane,'line':(address-target)//4096,'address':address,'packet_address':g('pkt.addr'),'way':g('pkt.way_id'),'uce_state':g('state'),'slow_write':g('slow'),'aborted':bool(aborted),'control':s['control']})
report={'purpose':'Same closed07 warm-up localization, not a new target run or performance result','input':v.binding(selected),'analyzer':v.binding(__file__),'validator':v.binding(ROOT/'testing/rtl/retained-advisory-trace/validate.py'),'critical_rtl':v.source_bindings(BASE/'model-source-list.json'),'refill_first_beats':refills,'index0_tag_installs':tags,'function_instruction_retirements':dict(functions),'warm_load_instruction_retirements':{'target0_word_loop_at_8000b1a0':retired[0x8000b1a0],'evictor_line_loop_at_8000b1b8':retired[0x8000b1b8]},'retained_queries':queries}
HERE.joinpath('localization.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
