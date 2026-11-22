#!/usr/bin/env python3
"""Portable snapshot/chain check only. Does not import monitor recipes."""
from pathlib import Path
import gzip,hashlib,json
HERE=Path(__file__).resolve().parent
def need(v,m):
 if not v:raise ValueError(m)
def verify():
 m=json.loads((HERE/'manifest.json').read_text())
 for row in m['files']:
  raw=(HERE/row['path']).read_bytes();need(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'packet bytes '+row['path'])
 review=json.loads((HERE/'review.json').read_text())
 for row in review['source_and_proof_copies']:
  raw=(HERE/row['copy']).read_bytes();need(hashlib.sha256(raw).hexdigest()==row['copy_sha256'],'exact copy/gzip bytes')
  if row.get('encoding')=='gzip':raw=gzip.decompress(raw)
  need(len(raw)==row['source']['bytes'] and hashlib.sha256(raw).hexdigest()==row['source']['sha256'],'lossless original source/proof')
 a=json.loads((HERE/'recipe/admission.json').read_text());need(hashlib.sha256((HERE/'recipe/admission.json').read_bytes()).hexdigest()=='76bc56a430ba5da43dbb7e0ff746b4e45c1bd848fb5b1ad1242048251c0efd48','exact continuation admission')
 seen={};prior=None;history={(r['path'],r['sha256']) for r in a['history']}
 for event in a['seed_events']:
  body={k:v for k,v in event.items() if k!='event_sha256'};need(event['previous_sha256']==prior and hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()==event['event_sha256'],'append-only event hash chain')
  identity=tuple(event['identity']);need(identity not in seen and event['sid']==event['pgrp']==1113832,'exact unique worker session/group identity')
  if event['parent'] is None:need(identity==(1113832,94444185) and event['kind']=='exact-worker-root','exact original worker root')
  else:need(tuple(event['parent']) in seen and event['parent'][1]<=identity[1] and event['kind']=='child-of-currently-proved-parent','previously proved exact parent')
  need((event['evidence']['path'],event['evidence']['sha256']) in history,'immutable historical poll provenance');seen[identity]=event;prior=event['event_sha256']
 p=json.loads((HERE/'proof/successful-probe.json').read_text());need(hashlib.sha256((HERE/'proof/successful-probe.json').read_bytes()).hexdigest()=='d13ccfd4c563df1e3cf28ad005f82dedfbaf35822784091adb8d6959b22c8e57','exact closed readiness')
 need(p['violations']==[] and p['signals_sent']==p['vendor_or_launcher_calls']==0,'probe read-only/no violations');need(all(tuple(k) in seen for k in p['ownership']['owned_current']),'current ownership from actual historical chains')
 return dict(state='PASS portable frozen source/readiness/provenance',files=len(m['files']),historical_polls=len(history),proved_identities=len(seen),closed_readiness_owned=len(p['ownership']['owned_current']))
if __name__=='__main__':print(json.dumps(verify(),sort_keys=True))
