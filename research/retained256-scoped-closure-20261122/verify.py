#!/usr/bin/env python3
"""Portable closed proof byte verification; never runs model/reader."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def verify(root):
 root=Path(root);m=json.loads((root/'manifest.json').read_text())
 for row in m['files']:
  p=root/row['path'];b=p.read_bytes();require(len(b)==row['bytes'] and sha(b)==row['sha256'],'local proof bytes '+row['path'])
  if 'lossless_original' in row:
   data=gzip.decompress(b);r=row['lossless_original'];require(len(data)==r['bytes'] and sha(data)==r['sha256'],'lossless source proof '+row['path'])
 report=json.loads((root/'review.json').read_text())
 require(report['state']=='PASS independent read-only matched256 clone closure','closed independent review')
 require(report['original_model']=='2c9d615694c0f59d9f85e6e247ba12494854378bd3b61334cf0cdaedc671e876' and report['scoped_model']=='1e9519cf83ede8d1bb7dd1d7924a98945cb274d8f2b666faf73737fb3376fe59','exact model identities')
 require(set(report['domains'])=={'core252','observer_and_geometry','SP_strict162','actual_geometry16','capacity167'},'five complete domains')
 require(all(r['clean_EOF'] and r['first_tick']==0 and r['final_tick']==6209375000 and r['bytes']>0 and r['events']>0 for r in report['domains'].values()),'full initialization-to-EOF coverage')
 return dict(state='PASS portable compact proof bytes/closed identities',files=len(m['files']),scope='Only metadata curation; full canonical/raw/model archives remain externally bound. No new event extraction or target execution.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);a=p.parse_args();print(json.dumps(verify(a.root),sort_keys=True))
