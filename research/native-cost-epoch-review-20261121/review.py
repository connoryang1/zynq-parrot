#!/usr/bin/env python3
"""Reuse closed accepted ledgers, bounded semantic events and source; no target/tool run."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
BASE=Path('/home/coyang/zynq-parrot-linux-capacity/research/retained-natural-control-20261121')
MODEL=BASE.parent/'retained-system-geometry-20261121/full-system1280-native0-03'
REPO=Path('/home/coyang/zynq-parrot-retained-sp/import/black-parrot')
LIMIT=128*1024*1024
def require(ok,message):
 if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(raw),sha256=sha(raw))
def checked(r):require(bind(r['path'])==r,'input binding '+r['path']);return Path(r['path'])

def inspect():
 p=BASE/'comparison-v3-01/comparison.json';comparison=json.loads(p.read_text());records=[bind(p)]
 require(sha(p.read_bytes())=='ada9f5d99311e80d091abeeae35bb1a6ef92a66f3b0487900ee0694e941d1634','exact accepted comparison')
 service_p=BASE/'comparison-v3-01/retained-service.json';service=json.loads(service_p.read_text());checked(service['comparison']);checked(service['events']);records.append(bind(service_p))
 actual=json.loads((MODEL/'actual-source-list.json').read_text());records.append(bind(MODEL/'actual-source-list.json'));source={}
 for suffix in ('bp_common/src/v/bp_retained_line_store.sv','bp_top/src/v/bp_unicore_lite.sv','bp_be/src/v/bp_be_dcache/bp_be_dcache.sv','bp_common/src/include/bp_common_aviary_cfg_pkgdef.svh'):
  r=subprocess.check_output(['git','-C',str(REPO),'show','e10992a3e:'+suffix]);row=next(v for k,v in actual.items() if k.endswith('/'+suffix));require(len(r)==row['bytes'] and sha(r)==row['sha256'],'actual ingested source '+suffix);source[suffix]=dict(revision='e10992a3e',bytes=len(r),sha256=sha(r))
 backend=subprocess.check_output(['git','-C',str(REPO),'show','e10992a3e:bp_common/src/v/bp_retained_line_store.sv']).decode()
 require('wire clear_now = clear_i[lane] || wrap;' in backend and '&& (&epochs_r[inv_set])' in backend,'wrap source semantics')
 build=(MODEL/'build.log').read_text();records.append(bind(MODEL/'build.log'))
 macros=sorted(set(re.findall(r'(?:-D|\+define\+)(BP_[A-Z0-9_]+(?:=[^\s\\"]+)?)',build)))
 require('BP_CUSTOM_BASE_CFG=bp_unicore_zynqparrot_cfg_p' in macros and 'BP_AXI_RESPONSE_DELAY=0' in macros,'exact old native configuration')
 arms={}
 for mode,bindings in comparison['bindings'].items():
  guest=json.loads(checked(bindings['guest']).read_text());phases=guest['phases'];records.append(bindings['guest'])
  audit=json.loads(checked(bindings['retained']).read_text());require(audit['state']=='PASS-retained-port-audit','accepted port audit');records.append(bindings['retained'])
  require(audit['report']['counts']==comparison['results'][mode]['retained_counts'],'accepted counts agree')
  p=checked(bindings['retained_events']);require(p.stat().st_size<16*1024*1024,'compressed reader bound');records.append(bindings['retained_events'])
  counts=Counter();special=[];nbytes=0
  with gzip.open(p,'rb') as f:
   while True:
    line=f.readline(1024*1024);require(len(line)<1024*1024,'bounded event line')
    if not line:break
    nbytes+=len(line);require(nbytes<=LIMIT,'bounded event stream');e=json.loads(line);c=e['global_cycle'];phase='pre_whole' if c<phases['whole_begin'] else 'whole' if c<phases['whole_end'] else 'post_whole'
    counts[(phase,e['lane'],e['event'])]+=1
    if e['event'] in ('writes','clear_episodes','epoch_wrap_pulses'):special.append(dict(e,phase=phase))
  wraps=[e for e in special if e['event']=='epoch_wrap_pulses'];commands=[e for e in special if e['event']=='writes'];clears=[e for e in special if e['event']=='clear_episodes']
  require(len(wraps)==13 and all(e['lane']=='d' and e['phase']=='post_whole' for e in wraps),'all wraps outside WHOLE')
  require([e['value'] for e in commands]==[int(mode),0] and len(clears)==4 and all(any(e['global_cycle']==cmd['global_cycle']+1 for cmd in commands) for e in clears),'two explicit controls explain both lane clear pulses')
  for phase in ('whole','timed_ring','program'):
   d=audit['report']['counts'][phase]['d'];require(d.get('epoch_wrap_pulses',0)==(13 if phase=='program' else 0),'accepted wrap window')
  arms[mode]=dict(phases=phases,retained_counts=audit['report']['counts'],normal_store_counts={w:c['reference_store'] for w,c in comparison['results'][mode]['normal_dcache_counts'].items()},special_events=special,
   first_wrap_after_whole=wraps[0]['global_cycle']-phases['whole_end'],semantic_stream_bytes=nbytes,
   mutation_accepted_by_phase={w:counts[(w,'d','mutation_invalidate_accepted')] for w in ('pre_whole','whole','post_whole')})
 cot={}
 for n in ('scheduler_retained29_cost_benchmark.c','scheduler_retained29_regex_cost_benchmark.c','retained29_cost_protocol.py','retained29_protocol.py'):
  p=HERE.parents[1]/'linux-tests'/n;cot[n]=bind(p)
 return dict(state='PASS existing accepted native cost evidence review only',inputs=records,actual_ingested_sources=source,old_model=comparison['model'],old_trace_bindings={m:b['trace'] for m,b in comparison['bindings'].items()},
  old_configuration_macros=macros,platform='Old4KiB-L2 base:32sets x2ways x64B per slice;2slices. Not current16KiB-L2 candidate; never pool.',arms=arms,accepted_service=service['result'],endpoints=comparison['endpoints'],current_COT_sources=cot,
  clear_accounting='WHOLE two explicit commands/clear pulses per lane, no wraps. Accepted off ledger counts2560 busy samples/lane=2x1280 sweep-state cycles.2x1281 may include initiating transition edges; it is not the accepted busy-sample metric and is not wrap overhead.',
  current_status='CSR[10]I/[11]D are sticky wrap-seen flags since last control command. active_raw before cleanup can detect enabled-cell wraps before its sample; cleanup command resets them. Off COST cells issue0 commands so sticky history may include earlier reporting/previous cells. Flags are not counts and two snapshots cannot locate all cleanup/whole activity.',
  limits='No critical-stall partition or causal cycle attribution. Mutation offers/accepted source events are not numbers of valid entries evicted or retired stores. No raw FST/selected-wave decode, target/model/board run, policy change or pooled platform inference.',source=bind(__file__),documentation=bind(HERE/'README.md'))

if __name__=='__main__':
 require(shutil.disk_usage(HERE).free>=3*1024**3+LIMIT,'3GiB reserve and128MiB output cap')
 value=inspect();p=HERE/'review.json';raw=(json.dumps(value,indent=2)+'\n').encode();require(len(raw)<=LIMIT,'output cap')
 if p.exists():require(json.loads(p.read_text())==value,'closed review drift')
 else:p.write_bytes(raw)
 print('PASS reused closed ledgers/events: no WHOLE wraps;13 D post-WHOLE wraps/arm; no target/FST run')
