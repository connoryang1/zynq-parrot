#!/usr/bin/env python3
"""Archive/reverify static1792 fixtures without recompiling or target execution."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
OUT=Path('/home/coyang/fpga-artifacts/context-resume/retained-capacity1792-fixtures-20261121/preparation01')
def require(ok,message):
 if not ok:raise ValueError(message)
def bind(p):
 p=Path(p).resolve();raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def check(r):require(bind(r['path'])==r,'bound file changed '+r['path'])
def inspect():
 p=OUT/'preparation-manifest.json';x=json.loads(p.read_text());require(x['state'].startswith('PASS crosscompile/static preparation only'),'static PASS only')
 require(x['source']==bind(HERE/'prepare.py'),'reviewed preparation source')
 for r in x['inputs_and_outputs']+x['toolchain_inputs']+x['frozen_inputs']:check(r)
 require(x['max_lines']==1792 and x['sets']==256 and x['expected_positive_counter']==dict(publications=1792,accepted_hits=1792,actual_L1_write_beats=14336),'fixed mechanical expansion')
 require(sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())<=32*1024**2,'external32MiB output cap')
 deps=json.loads((OUT/'dependency-proof.json').read_text())
 for r in deps['dependencies']+deps['additional_tool_inputs']:check(r)
 check(deps['commands']);files={p,OUT/'dependency-proof.json',OUT/'dependency-command-receipts.json'}
 files.update(r['path'] for r in x['inputs_and_outputs'] if '/build01/' not in r['path'])
 build=OUT/'build01';files.update(build/n for n in ('manifest.json','retained_capacity_test.elf','capacity_targets.inc','symbols.txt','disassembly.txt','compile.log'))
 for role in ('d-enabled','d-off','i-enabled'):
  r=x['requested_roles'][role];check(r['nbf']);require(r['coverage']['missing_bytes']==r['coverage']['wrong_bytes']==0,'independent full file/zero coverage');files.add(r['nbf']['path'])
  require(int(r['coverage']['load_bound']['maximum_write_end_exclusive'],16)<=0x82e00000,'tail-aware46MiB NBF bounds')
 files.update(r['path'] for r in deps['dependencies'])
 files.update(r['path'] for r in x['toolchain_inputs'] if Path(r['path']).suffix in ('.specs','.ld','.o'))
 return dict(state='CLOSED static1792 fixture collateral; no runtime/candidate/fit approval',preparation_manifest=bind(p),dependencies=bind(OUT/'dependency-proof.json'),
  records=[bind(p) for p in sorted(map(Path,files))],all_external_files=[bind(p) for p in sorted(OUT.rglob('*')) if p.is_file()],
  expected=x['expected_positive_counter'],ELF=x['elf'],roles=x['requested_roles'],limits=x['limits'],
  prior_failed_review=bind(OUT/'failed-review01.json'),archive_source=bind(__file__),documentation=bind(HERE/'README.md'))

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--archive',action='store_true');args=ap.parse_args();x=inspect();target=HERE/'verification.json'
 if args.archive:
  require(not target.exists(),'fresh archive only');require(shutil.disk_usage(HERE).free>=3*1024**3+32*1024**2,'3GiB reserve')
  blobs={};aliases=[];(HERE/'snapshots').mkdir()
  for r in x['records']:
   raw=Path(r['path']).read_bytes();n='snapshots/'+r['sha256']+'.gz'
   if n not in blobs:
    p=HERE/n;p.write_bytes(gzip.compress(raw,mtime=0));require(gzip.decompress(p.read_bytes())==raw,'lossless snapshot');blobs[n]=bind(p)
   aliases.append(dict(original=r,snapshot=n))
  require(inspect()==x,'external inputs changed');x.update(archives=blobs,snapshot_aliases=aliases);target.write_text(json.dumps(x,indent=2)+'\n')
 else:
  before=json.loads(target.read_text())
  for k,v in x.items():require(before[k]==v,'static proof drift '+k)
  for n,r in before['archives'].items():check(dict(r,path=str((HERE/n).resolve())))
  for row in before['snapshot_aliases']:
   raw=gzip.decompress((HERE/row['snapshot']).read_bytes());r=row['original'];require(len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'],'raw archive identity')
 print('PASS static1792 ELF/three NBF/source/CRT/toolchain/layout/46MiB/archive proof; runtime pending')
