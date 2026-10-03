#!/usr/bin/env python3
import hashlib,json,re,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROW=re.compile(r'^RESULT sample=(\d+) order=(\d+) mode=([^ ]+) ns=(\d+) requests=(\d+) checksum=(\d+) cycles=(\d+)$',re.M)

def text(name): return (HERE/name).read_text(errors='replace').replace('\r','')
def rows(name):
 return [{'sample':int(a),'order':int(b),'mode':c,'ns':int(d),'requests':int(e),'checksum':int(f),'cycles':int(g)} for a,b,c,d,e,f,g in ROW.findall(text(name))]
def status(name): return json.loads((HERE/name).read_text())
def sha(name): return hashlib.sha256((HERE/name).read_bytes()).hexdigest()

def summarize(rs):
 out={}
 for mode in sorted({r['mode'] for r in rs}):
  selected=[r for r in rs if r['mode']==mode]
  cyc=[r['cycles'] for r in selected]
  out[mode]={'samples':len(selected),'cycles':cyc,'median_cycles':statistics.median(cyc),
             'median_cycles_per_request':statistics.median(cyc)/8192}
 return out

original=rows('board.log'); primed=rows('primed-board.log')
phased=text('register-probe-attempt2-phase256-stall.log')
passes=[int(x) for x in re.findall(r'\[PREFETCH-SWITCH-REG\] phase pass (\d+)',phased)]
begins=[int(x) for x in re.findall(r'\[PREFETCH-SWITCH-REG\] phase begin (\d+)',phased)]
primed_summary=summarize(primed)
linux=primed_summary['linux-threads-demand']['median_cycles']
hwd=primed_summary['resident-demand-handoff']['median_cycles']
hwp=primed_summary['resident-prefetch-yield-load']['median_cycles']
report={
 'accepted_integrated_result':False,
 'endpoint':{'bit_sha256':'9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf',
             'linux_nbf_sha256':'af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3',
             'clock_mhz':18},
 'unprimed_full':{'status':status('board-status.json')['status'],'complete_result_rows':len(original),
                  'rows':original,'last_result_mode':original[-1]['mode'],
                  'failure':'sample 1 resident-prefetch-yield-load did not return before the 600-second watchdog'},
 'unprimed_phased_probe':{'passed_phases':passes,'begun_phases':begins,
                          'first_nonreturning_phase':begins[-1],
                          'status':status('register-probe-attempt2-phase256-status.json')['status']},
 'matched_256_controls':{
   'unprimed':{'outcome':'STALL','status':status('unprimed256-probe-status.json')['status']},
   'fence_only':{'outcome':'STALL','status':status('fence-probe-status.json')['status']},
   'eight_same_page_demand_reads':{'outcome':'PASS','status':status('samepagewarm-probe-status.json')['status']},
   'eight_one_per_page_demand_reads':{'outcome':'PASS','status':status('translation-probe-status.json')['status']},
 },
 'four_lines_per_context_full_run':{
   'accepted':False,'hardware_primed_lines_per_context':4,
   'primed_fraction_of_8192_requests':8/8192,
   'complete_result_rows':len(primed),'summaries_are_incomplete_diagnostics':True,
   'partial_mode_summary':primed_summary,
   'complete_prefetch_measured_samples':primed_summary['resident-prefetch-yield-load']['samples'],
   'failure':'warmup and samples 1-3 completed all modes; sample 4 resident-prefetch-yield-load did not return',
   'partial_linux_over_hardware_demand_ratio':linux/hwd,
   'partial_linux_over_hardware_prefetch_ratio':linux/hwp,
 },
 'interpretation':[
   'Direct hardware handoff and hardware demand controls complete; the sustained failure is specific to the prefetch-plus-handoff path.',
   'A full fence alone does not repair the matched 256-line failure.',
   'Eight demand reads repair one 256-line run whether spread across pages or confined to one page, rejecting translation coverage as the sole explanation.',
   'Eight launch reads are not a sustained fix: the full workload completes four prefetch invocations including warmup, then stalls on the fifth.',
   'The repeat count is consistent with finite cache/prefetch state accumulating across launches, but occupancy was not directly observed and two leaked entries per launch remains a hypothesis.',
   'Partial timing rows are not an accepted speedup because the benchmark does not complete all seven samples.'
 ],
 'artifact_sha256':{}
}
for name in ['request_benchmark_dynamic','request_benchmark_dynamic_diagnostic','request_benchmark_dynamic_primed',
 'prefetch_switch_register_probe','prefetch_switch_unprimed256_probe','prefetch_switch_fence_probe',
 'prefetch_switch_samepagewarm_probe','prefetch_switch_translation_probe']:
 report['artifact_sha256'][name]=sha(name)
assert report['endpoint']['linux_nbf_sha256']==status('board-status.json')['linux_nbf_sha256']
assert len(original)==2 and original[-1]['mode']=='resident-demand-handoff'
assert passes==[1,2,4,8,9,16,64] and begins[-1]==256
assert status('unprimed256-probe-status.json')['status']=='MEASURED_STALL'
assert status('fence-probe-status.json')['status']=='MEASURED_STALL'
assert status('samepagewarm-probe-status.json')['status']=='PASS'
assert status('translation-probe-status.json')['status']=='PASS'
assert len(primed)==15 and primed_summary['resident-prefetch-yield-load']['samples']==3
print(json.dumps(report,indent=2,sort_keys=True))
