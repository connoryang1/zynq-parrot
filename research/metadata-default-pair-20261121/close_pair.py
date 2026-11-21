#!/usr/bin/env python3
"""Losslessly close the immutable Default-directive pair; never run a tool."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE=Path(__file__).resolve().parent
BASE=Path('/home/coyang/fpga-artifacts/context-resume/retained-metadata-default-inference-20261121')
CASES=('sp-i-invalidate-zero','metadata-i-invalidate-zero')

def require(ok,message):
 if not ok:raise ValueError(message)
def digest(data):return hashlib.sha256(data).hexdigest()
def info(path):
 raw=path.read_bytes();return dict(bytes=len(raw),sha256=digest(raw))
def binding(path):return dict(path=str(path.resolve()),**info(path))
def check(record):require(binding(Path(record['path']))==record,'original binding drift '+record['path'])

def inspect():
 plan=json.loads((BASE/'plan.json').read_text());files={BASE/name for name in ('README.md','run_control.py','verify_prepare.py','frozen-inputs.json','derivation.diff','root-decision.json',
  'plan.json','root-admission.json','host-verification.json','wrapper.sv','probe.tcl','source-sp-i-invalidate-zero.sv','source-metadata-i-invalidate-zero.sv')}
 require(info(BASE/'run_control.py')['sha256']==plan['runner_sha256']=='c9ff931543bf0741705f38e1e61340e25cb74d0501956886138909be8bd0d8b9','frozen bounded runner')
 require(info(BASE/'wrapper.sv')['sha256']==plan['wrapper_sha256']=='8d71f55d3074f4994fd859d661118280eb9046d865dd471aa0b9d5f4ca99d845','frozen common wrapper')
 require(info(BASE/'probe.tcl')['sha256']==plan['tcl_sha256']=='299ca300c61d4a7392d5ba83a894447837eda76a2d513dabba476133ce4248f1','frozen Default directive')
 require(plan['parameters']==dict(paddr_width_p=34,i_lines_p=1280,d_lines_p=1280,sets_p=256,epoch_width_p=8)
  and plan['threads']==8 and plan['native_timeout_s']==180,'fixed parameters/budget')
 production=Path('/home/coyang/fpga-artifacts/context-resume/retained-metadata-production-controls-20261121')
 require((BASE/'wrapper.sv').read_bytes()==(production/'wrapper.sv').read_bytes(),'unchanged original I-inv0 wrapper')
 require((BASE/'probe.tcl').read_text().replace('-directive Default','-directive AreaOptimized_high')==(production/'probe.tcl').read_text(),'only synthesis directive changed')
 require(plan['synthesis_directive']=='Default','actual Default plan')
 for case in CASES:require((BASE/('source-'+case+'.sv')).read_bytes()==(production/('source-'+case+'.sv')).read_bytes(),'unchanged source '+case)
 require(json.loads((BASE/'root-admission.json').read_text())==dict(state='ROOT-APPROVED two new Default-directive arms only',plan=plan),'exact root admission')
 arms={};large={}
 for case in CASES:
  arm=BASE/(case+'01');s=json.loads((arm/'session.json').read_text());files.add(arm/'session.json')
  require(s['case']==case and s['plan']==plan,'same closed pair plan')
  require([row['label'] for row in s['commands']]==['admission','upload','synthesis','collect','no-orphans'],'complete command receipts')
  codes=[row['returncode'] for row in s['commands']]
  require(codes==([0,0,0,0,0] if case==CASES[0] else [0,0,124,0,0]),'exact closed command outcomes')
  require('timeout --kill-after=15s 180s' in s['commands'][2]['argv'][-1] and s['commands'][2]['timeout']==220,'bounded180 tool/220SSH')
  for row in s['commands']:check(row['log']);files.add(Path(row['log']['path']))
  for name,record in s['inputs'].items():
   check(record);files.add(Path(record['path']));files.add(arm/'remote'/name)
   require(info(arm/'remote'/name)['sha256']==record['sha256'],'collected actual input '+case+'/'+name)
  require(s['inputs']['source.sv']['sha256']==plan['cases'][case]['sha256'],'exact source body '+case)
  files.update((arm/'remote/vivado.log',arm/'remote/vivado.jou'))
  if case==CASES[0]:
   require(s['state']=='PASS Default-directive standalone inference only','actual SP success')
   for name,record in s['outputs'].items():
    check(record)
    if name=='synthesized.dcp':
     with zipfile.ZipFile(record['path']) as archive:require(archive.testzip() is None,'SP DCP integrity')
     large[name]=record
    else:files.add(Path(record['path']))
   check(s['comparison']);files.add(Path(s['comparison']['path']))
   table=(arm/'remote/utilization.rpt').read_text();row=re.search(r'^\| retained_production_controls\s*\|\s*\(top\)\s*\|([^\n]+)\|$',table,re.M)
   require(row is not None and [int(v.strip()) for v in row[1].split('|')]==[4065,4065,0,0,5831,40,2,0],'actual SP resource row')
   resources=json.loads(Path(s['comparison']['path']).read_text())['resources']
  else:
   require(s['state']=='FAIL preserved Default-directive inference arm; no fit conclusion','actual metadata timeout failure')
   require(not any((arm/'remote'/name).exists() for name in ('utilization.rpt','synthesized.dcp'))
    and 'outputs' not in s and 'comparison' not in s,'metadata no resource/checkpoint result')
   resources=None
  arms[case]=dict(session=binding(arm/'session.json'),source=plan['cases'][case],command_returncodes=codes,
   started_utc=s['started_utc'],closed_utc=s['closed_utc'],resources=resources)
 require(arms[CASES[0]]['closed_utc']<arms[CASES[1]]['started_utc'],'sequential independent arms')
 prior=HERE.parents[1]/'research/metadata-production-control-pair-20261121/verification.json'
 return dict(state='CLOSED SP PASS / metadata native180 timeout124; no metadata area conclusion',arms=arms,
  inputs=[binding(path) for path in sorted(files)],external_large_artifacts=large,
  prior_production_pair=dict(relative_path='../metadata-production-control-pair-20261121/verification.json',**info(prior)),
  cause='Unknown. Default directive did not yield metadata completion within180s. No resource delta can be calculated.',
  no_metadata_resource_delta=True,no_wholeCPU_projection=True,nonproduction_directive=True,no_XDC=True,
  closer=info(Path(__file__)),documentation=info(HERE/'README.md'),reviewer_remote_operations=0,reviewer_tool_runs=0,reviewer_board_actions=0)

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--archive',action='store_true');args=ap.parse_args()
 value=inspect();path=HERE/'verification.json'
 if args.archive:
  require(not path.exists(),'fresh pair archive required');blobs={};aliases=[];(HERE/'snapshots').mkdir()
  for record in value['inputs']:
   raw=Path(record['path']).read_bytes();name='snapshots/'+record['sha256']+'.gz';target=HERE/name
   if name not in blobs:
    target.write_bytes(gzip.compress(raw,mtime=0));require(gzip.decompress(target.read_bytes())==raw,'lossless archive round trip');blobs[name]=info(target)
   aliases.append(dict(original=record,snapshot=name))
  require(inspect()==value,'originals changed while archiving')
  value.update(archives=blobs,snapshot_aliases=aliases)
  path.write_text(json.dumps(value,indent=2)+'\n')
 else:
  recorded=json.loads(path.read_text())
  for key,item in value.items():require(recorded[key]==item,'pair evidence drift '+key)
  for name,record in recorded['archives'].items():require(info(HERE/name)==record,'archive drift '+name)
  for row in recorded['snapshot_aliases']:
   raw=gzip.decompress((HERE/row['snapshot']).read_bytes());require(len(raw)==row['original']['bytes'] and digest(raw)==row['original']['sha256'],'lossless original archive identity')
 print('PASS closed Default pair archive: SP4065/5831/41; metadata124/noresources; unknown cause')

if __name__=='__main__':main()
