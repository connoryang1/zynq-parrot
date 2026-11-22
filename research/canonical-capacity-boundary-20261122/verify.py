#!/usr/bin/env python3
"""Portable lossless closed evidence check; no vendor/model/reader."""
from pathlib import Path
import json,gzip,hashlib

def verify(root):
 root=Path(root);m=json.loads((root/'manifest.json').read_text())
 for row in m['files']:
  b=(root/row['local']).read_bytes()
  if len(b)!=row['bytes'] or hashlib.sha256(b).hexdigest()!=row['sha256']:raise ValueError('local evidence drift '+row['local'])
  if 'original' in row:
   d=gzip.decompress(b);r=row['original']
   if len(d)!=r['bytes'] or hashlib.sha256(d).hexdigest()!=r['sha256']:raise ValueError('lossless snapshot drift')
 return dict(state='PASS compact closed boundary evidence',files=len(m['files']))
if __name__=='__main__':print(json.dumps(verify(Path(__file__).resolve().parent)))
