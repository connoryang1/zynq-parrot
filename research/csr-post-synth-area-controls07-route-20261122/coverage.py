#!/usr/bin/env python3
"""Classify mapped coverage against the closed, external ROOT observation policy."""
import csv,hashlib,json,sys
from pathlib import Path
POLICY_SHA='6dfc1df776c7686f519e2be825f0aba98bb03a5ea32a88cb587a027722701ea0'
def need(ok,message):
 if not ok:raise ValueError(message+'; STOP ROOT review before placement/acceptance')
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def endpoint_set(p):
 return sorted(x.strip() for x in p.read_text().splitlines() if x.startswith('black_parrot_bd_1_i/'))
def main():
 policy,folder,stage=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
 need(stage in ['mapped'],'fixed coverage stage')
 need(digest(policy)==POLICY_SHA,'external ROOT policy SHA')
 p=json.loads(policy.read_text());need(p['schema']=='root-observed-csr256-clock-policy-v1','ROOT observed policy schema')
 out=dict(state='FAIL',stage=stage,policy_sha256=POLICY_SHA)
 try:
  for filename,key in [('clocks.tsv','exact_clock_table'),('ports.tsv','exact_ports'),('constraints.xdc','exact_constraints')]:
   need(digest(folder/filename)==p[key]['sha256'],'actual clock/source/port/XDC byte identity '+filename)
  need(not (folder/'blackboxes.txt').read_bytes(),'no black boxes')
  table=folder/'clock-sinks.tsv'
  rows=list(csv.DictReader(table.open(),delimiter='\t'))
  need(len(rows)>0 and len({r['pin'] for r in rows})==len(rows),'complete unique mapped clock-sink table')
  # Ordinary optimized endpoint names/counts can change. Domain rules remain
  # strict and all exceptional identities must match the observed policy.
  static=[r for r in rows if r['class'].startswith('STATIC_')]
  need(static==p['exact_static_zero_rows'],'exact static zero pin/ref/driver identities; no new static FF/DSP exemption')
  dual=[r for r in rows if ',' in r['clock_domains']]
  need(dual==p['exact_clint_dual_domain_rows'],'exact 128 mtime_gray dual-domain rows')
  special=[];tags=[];counts={}
  for r in rows:
   counts[r['region']+':'+r['class']]=counts.get(r['region']+':'+r['class'],0)+1
   if r['class']=='CLOCKED':
    if r['clock_domains']==p['core_domain']:continue
    if r in dual:continue
    special.append(r)
   elif r['class'].startswith('STATIC_'):continue
   else:
    need(r['pin'] in p['exact_tag_no_clock_pins'] and r['region']=='SHELL' and r['cell_ref'] in ['FDRE','FDSE'] and r['pin_ref']=='C','only exact existing tag programming clock pins may be unclocked')
    need(r['direct_drivers'] in p['tag_direct_driver_observed_variants'] and r['fanin_startpoints']==p['tag_fanin_timing_startpoint_C'],'actual tag driver and common timing startpoint')
    tags.append(r['pin'])
  need(special==p['exact_MMCM_clock_rows'],'exact two special MMCM domain rows; no new core/processor clock domains')
  need(sorted(tags)==p['exact_tag_no_clock_pins'],'same exact tag programming clock pin set')
  need(endpoint_set(folder/'check-no-clock.rpt')==p['exact_tag_no_clock_pins'],'check_timing exact42 no_clock set')
  need(endpoint_set(folder/'check-unconstrained.rpt')==p['exact_tag_unconstrained_pins'],'check_timing exact76 unconstrained set')
  need('root clock pin: '+p['tag_source_Q']+' (HIGH)' in (folder/'check-no-clock.rpt').read_text(),'verbose actual root clock Q attribution')
  need('checking constant_clock (0)' in (folder/'check-constant-clock.rpt').read_text(),'no newly reported constant clock timing exception')
  out.update(state='PASS',total_clock_sinks=len(rows),counts=counts,tag_no_clock=42,unconstrained=76,static_zero=41,clint_dual=128,special_MMCM=2,scope='Existing explicit tag timing limitation retained; no waiver, full timing signoff or semantic-equivalence claim')
 except BaseException as e:
  out['error']=repr(e);raise
 finally:(folder/'coverage-gate.json').write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':main()
