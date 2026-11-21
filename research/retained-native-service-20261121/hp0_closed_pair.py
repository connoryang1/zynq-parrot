#!/usr/bin/env python3
"""Reuse unchanged HP0 auditor/edge sampler on exact CLOSED native0 cases."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
NATURAL=ROOT/'research/retained-natural-control-20261121'
HP0=ROOT/'testing/rtl/hp0-closed-trace'
sys.path.insert(0,str(HP0));sys.path.insert(0,str(NATURAL))
import protocol
spec=importlib.util.spec_from_file_location('qualified_hp0_run',HP0/'run.py')
hp0=importlib.util.module_from_spec(spec);spec.loader.exec_module(hp0)


def bind(path):
 p=Path(path).resolve();h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def verify(record):
 if bind(record['path'])!=record:raise ValueError('closed input changed: '+record['path'])


def request_mapping(s,channel):
 pa=s['BP.'+channel+'addr'];base=s['dram_base']
 if None in (pa,base):raise ValueError('unknown observed BP→HP0 address translation')
 expected=((pa^0x80000000)+base)&0xffffffff
 if s[channel+'addr']!=expected:raise ValueError('actual BP→HP0 translation mismatch')
 return dict(BP_PA=pa,dram_base=base)


def expected_signals():
 expected=hp0.selections(0,True)
 expected.update({'BP.araddr':('top_fpga_inst.axi_araddr',32),
                  'BP.awaddr':('top_fpga_inst.axi_awaddr',32),
                  'dram_base':('top_fpga_inst.dram_base_li',32),
                  'be.clk':('unicore_lite.core_minimal.be.clk_i',1),
                  'be.reset':('unicore_lite.core_minimal.be.reset_i',1),
                  'be.retired':('unicore_lite.core_minimal.be.calculator.commit_pkt_cast_o.instret',1),
                  'be.pc':('unicore_lite.core_minimal.be.calculator.commit_pkt_cast_o.pc',39),
                  'be.global':('unicore_lite.core_minimal.be.calculator.pipe_sys.csr.global_cycle_r',64)})
 return expected


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',type=int,choices=(0,15),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 comparison_path=NATURAL/'comparison-v3-01/comparison.json';comparison_before=bind(comparison_path)
 if comparison_before['sha256']!='ada9f5d99311e80d091abeeae35bb1a6ef92a66f3b0487900ee0694e941d1634':raise ValueError('wrong closed pair')
 comparison=json.loads(comparison_path.read_text());cohort_path=Path(comparison['cohort']['path']);verify(comparison['cohort']);cohort=json.loads(cohort_path.read_text())
 if comparison['state']!='CLOSED-complete-audited-single-pair':raise ValueError('complete audited pair required')
 row=next(r for r in cohort['runs'] if r['mode']==a.mode)
 for name in ('trace','log','guest','trace_metadata'):verify(row[name])
 for path in (NATURAL/'protocol.py',ROOT/'testing/check_run.py'):verify(cohort['frozen_inputs'][str(path)])
 guest=json.loads(Path(row['guest']['path']).read_text())
 if protocol.parse(Path(row['log']['path']).read_text(),a.mode,row['returncode'])!=guest:raise ValueError('complete guest/CORE/host recheck failed')
 source_before={str(path):bind(path) for path in (Path(__file__),HP0/'run.py',HP0/'audit.py',NATURAL/'protocol.py',ROOT/'testing/check_run.py')}
 reader=ROOT/'research/retained-system-geometry-20261121/reader/fst_events'
 if bind(reader)['sha256']!='a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541':raise ValueError('wrong frozen FSTAPI reader')
 a.output.mkdir(parents=True,exist_ok=False)
 model_sources=ROOT/'research/retained-system-geometry-20261121/full-system1280-native0-03/actual-source-list.json'
 snapshots=hp0.snapshot_sources(json.loads(model_sources.read_text()),a.output,0,['HEAD','b99e2dd71'])
 expected=expected_signals()
 listing=subprocess.run([str(reader),row['trace']['path'],'--list'],capture_output=True,text=True,timeout=60)
 if listing.returncode or not listing.stdout.rstrip().endswith('#END'):raise ValueError('closed hierarchy read failed')
 declarations=[line.split('\t') for line in listing.stdout.splitlines() if line.startswith('#VAR')]
 resolved={}
 for key,(suffix,width) in expected.items():
  found=[d for d in declarations if d[3]==suffix or d[3].endswith('.'+suffix)]
  if len(found)!=1 or int(found[0][1])!=width:raise ValueError('missing/ambiguous/wrong-width '+key)
  resolved[key]=found[0][3]
 selection=a.output/'selection.tsv';selection.write_text(''.join(k+'\t'+path+'\n' for k,path in resolved.items()))
 command=[str(reader),row['trace']['path'],str(selection.resolve())]
 observed=hp0.audit.Auditor(0);endpoints={lane:hp0.audit.UceEndpoints(lane) for lane in ('i','d')}
 metadata={};started=False;be_resets=[];be_periods={};last_be=None;first_start=None
 error=None;report=None
 with gzip.open(a.output/'selected-events.tsv.gz','wt') as saved,(a.output/'reader.stderr').open('w') as err:
  proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=err,text=True);timer=threading.Timer(600,proc.kill);timer.daemon=True;timer.start()
  def lines():
   for line in proc.stdout:saved.write(line);yield line
  try:
   for tick,clocks,s in hp0.edge_samples(lines(),expected,metadata):
    if 'be.clk' in clocks:
     if s['be.reset']:
      if started:raise ValueError('BE reset after program start')
      be_resets.append(tick);last_be=None
     else:
      if last_be is not None:be_periods[tick-last_be]=be_periods.get(tick-last_be,0)+1
      last_be=tick
      if s['be.retired'] and s['be.pc']==0x80000000:
       started=True;first_start=dict(tick=tick,global_cycle=s['be.global'])
    if 'clk' in clocks:
     if started and s['resetn']==0:raise ValueError('AXI reset after architectural startup')
     mapping={channel:request_mapping(s,channel) for channel in ('ar','aw') if s['resetn'] and s[channel+'valid'] and s[channel+'ready']}
     observed.step(tick,s)
     for channel,translation in mapping.items():
      records=observed.core.reads if channel=='ar' else observed.core.writes
      if not records or records[-1]['request_time']!=tick:raise ValueError('AR/AW mapping lost accepted transaction')
      records[-1].update(translation)
    for lane,endpoint in endpoints.items():
     if lane+'.clk' in clocks:endpoint.step(tick,s)
   if proc.wait()!=0:raise ValueError('reader failed/timed out')
   report=observed.finish()
   if any(r['AR_transactions'] or r['AW_transactions'] or r['pending_AR'] for r in report['discarded_on_actual_AXI_reset']):raise ValueError('actual reset discarded accepted traffic')
   if len(be_periods)!=1:raise ValueError('BE clock period changed')
   report.update(FST_timebase=metadata,BE_clock_period_ticks=next(iter(be_periods)),first_architectural_start=first_start,
                 UCE_endpoints={lane:endpoint.finish() for lane,endpoint in endpoints.items()})
   if any(v['unfinished_requests'] for v in report['UCE_endpoints'].values()):raise ValueError('closed UCE request did not fully ACK')
   normal=json.loads(Path(comparison['bindings'][str(a.mode)]['normal']['path']).read_text())
   if report['UCE_endpoints']['d']['completed_requests']!=normal['counts']['program']['fill_complete']:raise ValueError('UCE normal D refill total differs from existing full-cache audit')
  except BaseException as e:error=repr(e);proc.kill();proc.wait()
  finally:timer.cancel()
 transactions=dict(BP_reads=observed.core.reads,BP_writes=observed.core.writes,external_reads=observed.external.reads,external_writes=observed.external.writes,
                   R_shift=observed.streams[0].completed,B_shift=observed.streams[1].completed,UCE={lane:endpoint.completed for lane,endpoint in endpoints.items()})
 with gzip.open(a.output/'transactions.json.gz','wt') as f:json.dump(transactions,f,separators=(',',':'))
 for record in source_before.values():verify(record)
 verify(row['trace']);verify(comparison_before)
 output=dict(state='PASS-closed-native-HP0-audit' if report is not None and error is None else 'FAIL-no-accepted-service-result',error=error,
 comparison=comparison_before,cohort=comparison['cohort'],mode=a.mode,trace=row['trace'],guest=row['guest'],sources=source_before,
 reader=bind(reader),selection=bind(selection),command=command,timeout_seconds=600,selected_events=bind(a.output/'selected-events.tsv.gz'),model_source_list=bind(model_sources),compiled_source_snapshots=snapshots,
 transactions=bind(a.output/'transactions.json.gz'),report=report,
 scope='Unchanged existing HP0 opaque/per-ID/burst auditor and UCE endpoints. Added actual BP→HP0 address provenance and architectural reset guard only. Native simulation, no physical calibration or exclusive-stall attribution.')
 (a.output/'analysis.json').write_text(json.dumps(output,indent=2)+'\n')
 if error:raise ValueError(error)
 print(json.dumps(dict(state=output['state'],mode=a.mode,external=report['external'],BP_facing=report['BP_facing']),indent=2))


if __name__=='__main__':main()
