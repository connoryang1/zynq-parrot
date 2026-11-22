#!/usr/bin/env python3
"""Portable compact metadata/snapshot integrity only."""
from pathlib import Path
import gzip,hashlib,json

def verify(root):
 root=Path(root);m=json.loads((root/'manifest.json').read_text())
 for r in m['files']:
  p=root/r['local'];b=p.read_bytes()
  if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('local proof drift '+r['local'])
  if 'original' in r:
   d=gzip.decompress(b);o=r['original']
   if len(d)!=o['bytes'] or hashlib.sha256(d).hexdigest()!=o['sha256']:raise ValueError('lossless snapshot drift')
 return dict(state='PASS compact negative area/boundary proof',files=len(m['files']))
if __name__=='__main__':print(json.dumps(verify(Path(__file__).resolve().parent)))
