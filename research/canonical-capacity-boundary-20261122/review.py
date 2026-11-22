#!/usr/bin/env python3
"""Closed canonical boundary acquisition review; no tool/model/reader execution."""
import csv,collections,hashlib,json,re
from pathlib import Path
R=Path('/home/coyang/fpga-artifacts/context-resume/retained-canonical-boundary-mapping-20261122/preparation01')

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p);h=hashlib.sha256();n=0
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b);n+=len(b)
 return dict(path=str(p),bytes=n,sha256=h.hexdigest())
def review():
 a=json.loads((R/'admission.json').read_text());s=json.loads((R/'run01/session.json').read_text())
 require(bind(R/'admission.json')['sha256']=='4a0966bac67f9476e1985de915bca95260d1bfd88e2e64cf69019e4d0fcbfb63' and s['admission']==bind(R/'admission.json'),'exact resource-only admission')
 require(s['state']=='PASS two unmeasured-depth canonical resource acquisitions; no functional/fit claim','closed two acquisitions')
 require(s['ownership_final']['linux_claim_state']=='RELEASED' and not s['ownership_final']['owned_group_remaining'],'closed ownership')
 require(not s['foreign_inventory_events'] and s['no_board_operations'] and s['source_endcheck']=='PASS','no foreign/board/source issue')
 require(a['resource_only'] and a['functional_claim'] is False and a['canonical_source']['commit']=='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c','canonical resource scope')
 for row in a['sources']:
  v=bind(R/row['name']);require(all(v[k]==row[k] for k in ('bytes','sha256')),'uploaded source drift')
 require(bind(R/'backend-canonical.sv')['sha256']=='68d1dd0c7df7e56ffe76317f9bae5a3ca3e09d13cb44d1167c0f737acefcbea6','actual full canonical source')
 prior=json.loads(Path(a['prior_production1792']['path']).read_text());require(bind(a['prior_production1792']['path'])==a['prior_production1792'],'prior actual1792 source/proof')
 baseline=next(x['analysis']['resources'] for x in prior['arms'] if x['arm']=='baseline1792')
 require(baseline['BRAM36_tiles']==56 and baseline['LUT']==1142,'same production1792 context')
 arms={};raw=[]
 for arm in s['arms']:
  life=arm['owned_receipt'];require(life['returncode']==0 and life['failure'] is None and not life['owned_group_remaining'] and not arm['prelaunch_global_idle']['vendor_processes'],'native0/idle/cleanup')
  for row in arm['artifacts']:require(bind(row['path'])==row,'closed artifact drift')
  folder=R/'run01'/arm['arm'];text=(folder/'utilization.rpt').read_text();m=re.search(r'^\| retained_production_controls\s*\|\s*\(top\)\s*\|([^\n]+)\|$',text,re.M);require(m is not None,'actual report row')
  values=[int(x.strip()) for x in m[1].split('|')];require(len(values)==8,'resource columns')
  resources=dict(zip(['LUT','logic_LUT','LUTRAM','SRL','FF','RAMB36','RAMB18','DSP'],values));resources['BRAM36_tiles']=resources['RAMB36']+resources['RAMB18']/2
  require(resources==arm['analysis']['resources'],'independent report totals')
  ports=list(csv.DictReader((folder/'block-ports.tsv').open(),delimiter='\t'));require(len(ports)==resources['RAMB36']+resources['RAMB18'],'physical BRAM count')
  groups={}
  for lane in (0,1):
   for kind in ('payload_mem','tag_mem'):
    part=[p for p in ports if f'lane_fsm[{lane}].{kind}' in p['name']]
    groups[f'{lane}:{kind}']=dict(collections.Counter('/'.join(p[k] for k in ('REF_NAME','READ_WIDTH_A','READ_WIDTH_B')) for p in part))
  primitives=list(csv.DictReader((folder/'primitives.tsv').open(),delimiter='\t'));require(sum(x['IS_PRIMITIVE']=='1' and x['REF_NAME']=='DSP48E1' for x in primitives)==resources['DSP'],'actual DSP count')
  require(not (folder/'blackboxes.txt').read_text().strip(),'no blackboxes')
  require(arm['analysis']['actual_clocks']=={'I_owning_clock':[50.0,[0.0,25.0]],'D_owning_clock':[50.0,[25.0,50.0]]},'actual phase/period controls')
  arms[arm['arm']]=dict(resources=resources,native_seconds=life['elapsed_s'],RAM_groups=groups)
  raw += [bind(folder/f) for f in ('functional.v','synthesized.dcp')]
 require(set(arms)=={'canonical1793','canonical1824'},'only requested capacities')
 require(arms['canonical1793']['resources']['LUT']==1123 and arms['canonical1824']['resources']['LUT']==1112 and all(x['resources']['BRAM36_tiles']==60 and x['resources']['FF']==2213 for x in arms.values()),'actual outcomes')
 r7=Path('/home/coyang/zynq-parrot-linux-capacity/research/fpga-native1792-canonical-r7-closed-20261122/verification.json');d=json.loads(r7.read_text());require(d['optimized_whole']['BRAM_tiles']==140 and d['optimized_focused_nonadditive']['6']['BRAM_tiles']==56,'old hierarchy facts')
 trace=Path('/home/coyang/zynq-parrot-linux-capacity/research/cache-miss-trace-opportunity-20261122/audit.json');traceproof=json.loads(trace.read_text())
 for row in traceproof['actual_closed_primitive_evidence']['files']:require(bind(row['path'])==row,'old trace hierarchy source')
 require(traceproof['actual_closed_primitive_evidence']['RAMB36E1']==2,'two measured old trace RAMs')
 return dict(state='PASS independent closed canonical1793/1824 resource review',session=bind(R/'run01/session.json'),admission=bind(R/'admission.json'),settings=a['settings'],baseline1792=baseline,arms=arms,external_raw_artifacts=raw,
  interpretation='In this exact canonical production source/options context,1792->1793 increases standalone store56->60tiles;1824 also60. It does not establish a global maximum or all intervening mappings. No new-depth functional/whole-device fit claim.',
  conditional_old_R7_budget=dict(source=bind(r7),old_optimized_whole_tiles=140,old_retained_tiles=56,old_others_including_trace=84,old_trace_named_tiles=2,trace_primitive_proof=bind(trace),projected_others_if_only_those_two_removed=82,projected_total_with60tile_store=142,scope='Arithmetic projection from old placement-failed R7 hierarchy. Borrow/traceoff may change other mappings; current whole-device job not read or evaluated.'),
  no_vendor_model_board_or_reader_run_by_review=True)
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);x=p.parse_args();x.out.write_text(json.dumps(review(),indent=2)+'\n');print(json.dumps(bind(x.out)))
