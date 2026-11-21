#!/usr/bin/env python3
"""Verify the sealed1792 static proof by content, allowing only archive relocation."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

SEALED_SHA='abbe776d950270daa7d70be754c4107e2584716de9b86dd0fa8c8be30269d71b'
def require(ok,message):
 if not ok:raise ValueError(message)
def content(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def check(path,row):require(content(Path(path).read_bytes())=={k:row[k] for k in ('bytes','sha256')},'content binding '+str(path))
def external(row):check(row['path'],row)
def verify(directory):
 directory=Path(directory).resolve();p=directory/'verification.json';raw=p.read_bytes()
 require(hashlib.sha256(raw).hexdigest()==SEALED_SHA,'fixed sealed proof identity');v=json.loads(raw)
 # Only these three reviewed source/document files and archive containers may
 # relocate. Every external source/binary/toolchain binding retains its path.
 check(directory/'close.py',v['archive_source']);check(directory/'README.md',v['documentation'])
 for r in v['records']+v['all_external_files']:external(r)
 external(v['preparation_manifest']);external(v['dependencies']);external(v['prior_failed_review'])
 x=json.loads(Path(v['preparation_manifest']['path']).read_text());check(directory/'prepare.py',x['source'])
 require(x['state']=='PASS crosscompile/static preparation only; NO simulation/FPGA/board/runtime result','static state')
 require(x['max_lines']==1792 and x['sets']==256 and x['expected_positive_counter']==v['expected']==dict(publications=1792,accepted_hits=1792,actual_L1_write_beats=14336),'fixed capacity/static expectations')
 require(x['elf']==v['ELF'] and x['requested_roles']==v['roles'],'static ELF/role bindings')
 for r in x['inputs_and_outputs']+x['toolchain_inputs']+x['frozen_inputs']:external(r)
 external(x['original_manifest']);external(x['elf']);external(x['manifest'])
 dependencies=json.loads(Path(v['dependencies']['path']).read_text());external(dependencies['commands'])
 for r in dependencies['dependencies']+dependencies['additional_tool_inputs']:external(r)
 for role in ('d-enabled','d-off','i-enabled'):
  r=x['requested_roles'][role];external(r['nbf']);external(r['mem']);c=r['coverage']
  require(c['missing_bytes']==c['wrong_bytes']==0 and c['load_bound']['allocation_bytes']==46*1024*1024 and int(c['load_bound']['maximum_write_end_exclusive'],16)<=0x82e00000,'sealed static46MiB coverage')
 records=Counter((r['path'],r['bytes'],r['sha256']) for r in v['records'])
 aliases=Counter((r['original']['path'],r['original']['bytes'],r['original']['sha256']) for r in v['snapshot_aliases'])
 require(records==aliases,'complete snapshot coverage')
 used=set()
 for name,row in v['archives'].items():
  require(Path(name).parts==('snapshots',Path(name).name) and Path(name).suffix=='.gz','bounded archive relative path');check(directory/name,row)
 for row in v['snapshot_aliases']:
  name=row['snapshot'];require(name in v['archives'],'declared snapshot');used.add(name)
  with gzip.open(directory/name,'rb') as f:decoded=f.read(row['original']['bytes']+1)
  require(content(decoded)=={k:row['original'][k] for k in ('bytes','sha256')},'raw lossless archive identity')
 require(used==set(v['archives']),'no unbound archive blobs')
 return dict(state='PASS portable independent static/archive verification; no recompile or target run',sealed_sha256=SEALED_SHA,archive_directory=str(directory),external_records=len(v['all_external_files']),snapshots=len(v['archives']))

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--archive-dir',required=True,type=Path);args=ap.parse_args()
 print(json.dumps(verify(args.archive_dir),sort_keys=True))
