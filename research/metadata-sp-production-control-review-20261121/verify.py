#!/usr/bin/env python3
"""Independently close only the completed SP production-control arm offline."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

HERE=Path(__file__).resolve().parent
BASE=Path('/home/coyang/fpga-artifacts/context-resume/retained-metadata-production-controls-20261121')
ARM=BASE/'sp-i-invalidate-zero01'

def require(ok,message):
 if not ok:raise ValueError(message)
def bind(path):
 data=path.read_bytes();return dict(path=str(path.resolve()),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def check(record):require(bind(Path(record['path']))==record,'binding drift '+record['path'])

def inspect():
 s=json.loads((ARM/'session.json').read_text());plan=json.loads((BASE/'plan.json').read_text())
 require(s['state']=='PASS constant-I-invalidation standalone synthesis only' and s['case']=='sp-i-invalidate-zero'
  and s['plan']==plan,'actual closed SP source-bound session')
 require([row['label'] for row in s['commands']]==['admission','upload','synthesis','collect','no-orphans']
  and all(row['returncode']==0 for row in s['commands']),'five complete successful commands')
 for row in s['commands']:check(row['log'])
 require('timeout --kill-after=15s 580s' in s['commands'][2]['argv'][-1]
  and s['commands'][2]['timeout']==620,'fixed bounded native control')
 check(s['admission']);admitted=json.loads(Path(s['admission']['path']).read_text())
 require(admitted==dict(state='ROOT-APPROVED two new production-control arms only',plan=plan),'actual exact root admission')
 require(bind(BASE/'run_control.py')['sha256']==plan['runner_sha256']=='2dd580f182e77909e5a4f2a5e10b1a0b1327913073ee69641c255fa5027869d8','frozen runner')
 case=plan['cases']['sp-i-invalidate-zero'];require(case['commit']=='d766d42cdf04ee43ca1e915fb9da06f5cc117dde','immutable SP source')
 source=subprocess.check_output(['git','-C',case['repo'],'show',case['commit']+':bp_common/src/v/bp_retained_line_store.sv'])
 require(hashlib.sha256(source).hexdigest()==case['sha256']=='aa36581844c5563f77bcc12f531776a4c858b1470a202d8f8394c7a02a7f8ea7','actual full body hash')
 for name,row in s['inputs'].items():
  check(row);require(bind(ARM/'remote'/name)['sha256']==row['sha256'],'collected actual input '+name)
 require((ARM/'source.sv').read_bytes()==source,'SP Git body exact')
 wrapper=(ARM/'wrapper.sv').read_text();body=wrapper[wrapper.index('\n  bp_retained_line_store'):]
 expected='clk_i reset_i clear_i invalidate_v_i invalidate_addr_i lookup_v_i lookup_ready_o lookup_addr_i resp_v_o resp_ready_i resp_hit_o resp_data_o insert_v_i insert_ready_o insert_addr_i insert_data_i insert_replace_i insert_cancel_i insert_done_o insert_published_o busy_o epoch_wrap_o'.split()
 for name in expected:
  target={'invalidate_v_i':"{invalidate_v_i[1], 1'b0}",'invalidate_addr_i':"{invalidate_addr_i[1], {paddr_width_p{1'b0}}}"}.get(name,name)
  require(body.count('.'+name+'('+target+')')==1,'only reviewed connection '+name)
 require(bind(ARM/'wrapper.sv')['sha256']==plan['wrapper_sha256']=='8d71f55d3074f4994fd859d661118280eb9046d865dd471aa0b9d5f4ca99d845','wrapper identity')
 require(bind(ARM/'probe.tcl')['sha256']==plan['tcl_sha256']=='40db936508a672c2cbc6a60fd883785d3cd8d0e19f3e05bd2e1bc124e932b93d','actual Tcl identity')
 check(plan['production_source']);production=Path(plan['production_source']['path']).read_text()
 require(".invalidate_v_i({dcache_retained_mutation_v, 1'b0})" in production and
  ".invalidate_addr_i({dcache_retained_mutation_paddr, {paddr_width_p{1'b0}}})" in production,'production constant provenance')
 for record in s['outputs'].values():check(record)
 check(s['comparison']);summary=json.loads(Path(s['comparison']['path']).read_text())
 report=(ARM/'remote/utilization.rpt').read_text()
 row=re.search(r'^\| retained_production_controls\s*\|\s*\(top\)\s*\|([^\n]+)\|$',report,re.M)
 require(row is not None,'actual wrapper top report');values=[int(x.strip()) for x in row[1].split('|')]
 require(values==[4314,4314,0,0,5855,40,2,0],'actual resource tuple')
 require(summary['resources']==dict(zip(('LUT','logic_LUT','LUTRAM','SRL','FF','RAMB36','RAMB18','DSP','tile_equivalents'),values+[41.0])), 'report/summary equality')
 primitives=[]
 for line in (ARM/'remote/primitives.tsv').read_text().splitlines():
  fields=line.split('\t');require(len(fields)==7 and fields[2]=='TDP','actual BRAM schema/mode');primitives.append(fields)
 require(Counter(x[1] for x in primitives)==dict(RAMB36E1=40,RAMB18E1=2),'actual42 BRAM objects/41tiles')
 require(not (ARM/'remote/distributed-primitives.tsv').read_text(),'actual zero distributed primitive census')
 log=(ARM/'remote/vivado.log').read_text()
 for name,value in plan['parameters'].items():
  found=re.findall(r'Parameter '+name+r" bound to: 32'b([01]+)",log)
  require(len(found)==2 and all(int(v,2)==value for v in found),'actual wrapper/child parameter '+name)
 require('synth_design completed successfully' in log and not re.search(r'^ERROR:',log,re.M),'actual complete successful synthesis')
 require('No global retiming is needed without any clock constraint' in log,'unconstrained standalone caveat')
 with zipfile.ZipFile(ARM/'remote/synthesized.dcp') as archive:require(archive.testzip() is None,'DCP archive integrity')
 return dict(state='PASS independent offline SP production-control closure only',session=bind(ARM/'session.json'),plan=bind(BASE/'plan.json'),
  inputs=s['inputs'],outputs=s['outputs'],resources=summary['resources'],primitive_count=len(primitives),
  primitive_mode='TDP all42; physical clock connectivity unproven',native_limit_s=580,
  actual_tool_synthesis_elapsed_s=509,actual_source=case,wrapper_constants_only=['I invalidate valid0','I invalidate address0'],
  no_clock_constraint=True,no_whole_CPU_projection=True,metadata_result_reviewed=False,
  actual_log=bind(ARM/'remote/vivado.log'),report=bind(HERE/'README.md'),verifier=bind(Path(__file__)),
  reviewer_remote_operations=0,reviewer_tool_runs=0,reviewer_board_actions=0)

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--record',action='store_true');args=ap.parse_args()
 value=inspect();path=HERE/'verification.json'
 if args.record:
  require(not path.exists(),'new SP review record required');path.write_text(json.dumps(value,indent=2)+'\n')
 else:require(json.loads(path.read_text())==value,'SP review source/evidence drift')
 print('PASS SP only:4314LUT,5855FF,41tiles,0LUTRAM; standalone/noXDC; metadata not reviewed')

if __name__=='__main__':main()
