#!/usr/bin/env python3
"""Bind closed service evidence and exclude I/advisory aliasing of D-hit joins."""
import gzip
import json
from pathlib import Path
import subprocess
import sys
from hp0_closed_pair import HERE,NATURAL,HP0,bind,verify


def main():
 comparison=NATURAL/'comparison-v3-01/comparison.json';base=bind(comparison)
 if base['sha256']!='ada9f5d99311e80d091abeeae35bb1a6ef92a66f3b0487900ee0694e941d1634':raise ValueError('wrong closed paired result')
 joined_path=HERE/'matched-service01/analysis.json';joined=json.loads(joined_path.read_text())
 if joined['state']!='PASS-closed-matched-service-and-HP0-join':raise ValueError('all matched joins required')
 verify(joined['joins'])
 with gzip.open(joined['joins']['path'],'rt') as f:rows=[json.loads(line) for line in f]
 hitlines={int(r['line'],16) for r in rows if r['retained_hit']}
 proofs={};exclusion={}
 for mode in (0,15):
  proofs[str(mode)]={}
  for suffix,state in (('hp0','PASS-closed-native-HP0-audit'),('dcache','PASS-closed-Dcache-service-intervals'),('time-index','PASS-HP0-actual-time-core-counter-index'),('offers','PASS-actual-offer-wait-and-gating-audit')):
   p=HERE/f'mode{mode}-{suffix}/analysis.json';record=json.loads(p.read_text())
   if record['state']!=state:raise ValueError('incomplete '+suffix)
   proofs[str(mode)][suffix]=bind(p)
  h=json.loads((HERE/f'mode{mode}-hp0/analysis.json').read_text());verify(h['trace']);verify(h['transactions'])
  with gzip.open(h['transactions']['path'],'rt') as f:transactions=json.load(f)
  instruction_lines={r['address']&~63 for r in transactions['UCE']['i']}
  overlap=instruction_lines&hitlines
  if overlap:raise ValueError('D-hit physical line also requested by I: source association needs refinement')
  t=json.loads((HERE/f'mode{mode}-time-index/analysis.json').read_text())
  if t['advisory_admissions']:raise ValueError('actual advisory traffic confounds source association')
  exclusion[str(mode)]=dict(distinct_I_request_lines=len(instruction_lines),overlap_with_any_joint_D_hit_line=0,advisory_admissions=0,
      explanation='All110instruction request lines over each full trace are disjoint from every joint D-hit line. Combined with the one-owned-normal-D-miss interval and unique physical-line HP0 read, this excludes same-line I/advisory ambiguity; RID0 is not used as a source label.')
 commands=[([sys.executable,'-m','unittest','test_hp0_closed_pair','test_dcache_intervals','test_join_service','test_offer_waits'],HERE),([sys.executable,'-m','unittest','test_audit'],HP0)]
 log=''
 for cmd,cwd in commands:
  r=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True);log+=r.stdout+r.stderr
  if r.returncode:raise ValueError('host tests failed')
 (HERE/'host-tests.log').write_text(log)
 paths=[p for p in HERE.glob('*.py')]+[HERE/'README.md',HERE/'host-tests.log']
 output=dict(state='CLOSED-READONLY-native-service-audits-PASS',comparison=base,matched_service=bind(joined_path),proofs=proofs,
             I_and_advisory_source_exclusion=exclusion,source_and_tests={p.name:bind(p) for p in sorted(paths)},
             host_tests=dict(new=25,unchanged_HP0=21,total=46),scope='No target/model/RTL/ELF changes or new execution. Complete original negative result remains unchanged. This is descriptive bottleneck evidence, not exclusive-stall attribution or FPGA/Linux calibration.')
 target=HERE/'closed-inputs.json'
 if target.exists():raise ValueError('preserve existing closure')
 target.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(dict(state=output['state'],tests=46,I_alias_exclusion=exclusion),indent=2))


if __name__=='__main__':main()
