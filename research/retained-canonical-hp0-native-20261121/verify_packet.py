#!/usr/bin/env python3
"""Verify compact closed records and payload joins; no reader/build/target calls."""
import gzip,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent

def require(ok,msg):
 if not ok:raise ValueError(msg)
def identity(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def main():
 m=json.loads((R/'manifest.json').read_text())
 for row in m['records']:
  p=R/row['snapshot']['path'];raw=p.read_bytes();require(identity(raw)=={k:row['snapshot'][k] for k in ('bytes','sha256')},'snapshot drift '+str(p))
  if row.get('encoding')=='gzip exact source bytes':raw=gzip.decompress(raw)
  require(identity(raw)=={k:row['original'][k] for k in ('bytes','sha256')},'original-byte binding '+str(p))
 review=json.loads((R/'independent-review.json').read_text());require(identity((R/'independent-review.json').read_bytes())['sha256']=='d098e29cf6fd0b561a4720642490378199441220eaae3585d51e2b01506ac3b7','independent closure pin')
 session=json.loads((R/'root-session.json').read_text());proof=json.loads((R/'audit01/verification.json').read_text());strict=json.loads((R/'inputs/original-strict.json').read_text());t=json.loads(gzip.decompress((R/'audit01/transactions.json.gz').read_bytes()))
 require(session['returncode']==0 and session['owned_group_remaining'] is False and proof['accepted'] and strict['accepted'],'complete closed audit')
 require(proof['bindings']['raw_FST']['sha256']==strict['bindings']['fst']['sha256']==m['external_large_artifacts']['raw_FST']['sha256'],'same raw trace')
 require(t['BP_facing_reads']==t['external_reads'] and t['BP_facing_writes']==t['external_writes'],'native opaque transport equality')
 require(len(t['BP_facing_reads'])==648 and len(t['BP_facing_writes'])==487,'whole fixture counts')
 require(proof['clock_period_FST_ticks']==50000,'actual clock period')
 for lane,wanted in [('i',109),('d',80)]:
  endpoints=proof['UCE_endpoints'][lane]['advisory_publications'];require(len(endpoints)==1,'one targetpublication');endpoint=endpoints[0];admit=endpoint['advisory']['time'];end=endpoint['time'];address=endpoint['address']
  matches=[q for q in t['BP_facing_reads'] if q['addr']==(address^0x80000000) and admit<=q['request_time']<end];require(len(matches)==1,'unique physical target/window')
  q=matches[0];value=sum(b['data']<<(64*i) for i,b in enumerate(q['beats']));publication=strict['lanes'][lane]['publications'][0];burst=strict['lanes'][lane]['bursts'][0]
  require(publication['time']==end and publication['insert']['address']==address and publication['insert']['data']==value,'all512 publication bits')
  require((end-admit)//50000==wanted and (end-admit)%50000==0,'newnative publication interval')
  require(not burst['aborted'] and not burst['errors'] and len(burst['beats'])==8,'eight real nonaborted writes')
  for beat in burst['beats']:require(beat['data']==q['beats'][beat['word']]['data'] and beat['address']==address+8*beat['word'],'all512 winning SRAM bits')
 sources=json.loads(gzip.decompress((R/'inputs/actual-source-list.json.gz').read_bytes()))['sources']
 for row in proof['bindings']['source_snapshots']:
  raw=(R/'audit01/source'/Path(row['snapshot']['path']).name).read_bytes();require(identity(raw)=={k:sources[row['compiled_path']][k] for k in ('bytes','sha256')},'actual source snapshot binding')
 print('PASS compact canonicalb912 native99/source/full512 association; no model/reader/board execution')
if __name__=='__main__':main()
