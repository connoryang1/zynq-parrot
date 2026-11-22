#!/usr/bin/env python3
"""Portable compact-packet byte verification; no external inputs or subprocesses."""
import hashlib,json,tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
def verify():
 m=json.loads((HERE/'manifest.json').read_text())
 for row in m['files']:
  raw=(HERE/row['path']).read_bytes()
  if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('packet byte mismatch '+row['path'])
 rows={x['member']:x for x in json.loads((HERE/'proof-members.json').read_text())};seen=set()
 with tarfile.open(HERE/'proofs.tar.gz','r|gz') as tar:
  for info in tar:
   if info.name not in rows or info.name in seen or not info.isfile():raise ValueError('compact member inventory')
   raw=tar.extractfile(info).read();row=rows[info.name]
   if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('compact member bytes')
   seen.add(info.name)
 if seen!=set(rows):raise ValueError('missing compact member')
 return dict(state='PASS portable packet and all compact members',files=len(m['files']),proof_members=len(seen))
if __name__=='__main__':print(json.dumps(verify(),sort_keys=True))
