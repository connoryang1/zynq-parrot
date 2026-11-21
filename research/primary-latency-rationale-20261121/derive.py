#!/usr/bin/env python3
"""Unit conversions only. No simulation, target or network activity."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def derive():
 frequencies=[0.5,1.0,2.0]
 scenarios=[dict(assumed_GHz=f,selected_latency_ns=[60,100],derived_core_cycles=[int(f*60),int(f*100)],
                 assumed_peak_8B_per_cycle_GB_s=8*f) for f in frequencies]
 endpoints=[dict(added_response_age_cycles=n,closed_SP_AR_first_accept_cycles=n+1,closed_SP_AR_full_accept_cycles=n+8,
                 actual_20MHz_extra_microseconds=n/20,
                 hypothetical_added_ns_by_GHz={str(f):n/f for f in frequencies}) for n in (0,40,200)]
 assert scenarios[0]['derived_core_cycles']==[30,50] and scenarios[-1]['derived_core_cycles']==[120,200]
 assert endpoints[1]['closed_SP_AR_full_accept_cycles']==48 and endpoints[-1]['closed_SP_AR_full_accept_cycles']==208
 return dict(state='DERIVED-arithmetic-only-not-calibration-or-performance',formula='cycles = GHz * ns; additional ns = added cycles / GHz',
             scenarios=scenarios,existing_synthetic_endpoints=endpoints,
             interpretation='Selected60-100ns × hypothetical0.5-2GHz spans30-200cycles. Added40/200 are coarse sensitivity controls, not a strict total-latency bracket or representative calibrated machine.',
             limitations=['No frequency claim for current20MHz FPGA or modified ASIC RTL.','Published latency differences are not HP0 AR-first/full measurements.',
                          'Bandwidth, outstanding requests, cache/UCE timing, source arbitration and complete execution remain separate.'])

if __name__=='__main__':
 output=HERE/'derived.json';result=derive()
 if output.exists():assert json.loads(output.read_text())==result,'preserve changed arithmetic'
 else:output.write_text(json.dumps(result,indent=2)+'\n')
 print('PASS independent unit conversions only')
