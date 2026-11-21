#!/usr/bin/env python3
"""Derive observed predecessor/target read timing from closed SP1280 records only."""
import gzip
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=Path('/home/coyang/fpga-artifacts/context-resume/retained-sp-latency-preparation-20261121/acquisition-session01')

def bind(path):
 p=Path(path);raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def check(record):
 got=bind(record['path']);assert all(got[k]==record[k] for k in ('bytes','sha256')),record['path']

def derive():
 prior=json.loads((HERE/'path-timing.json').read_text());rows=[];bindings=[]
 assert [r['delay'] for r in prior['rows']]==[0,40,200],'exact three matched controls required'
 for old in prior['rows']:
  delay=old['delay'];vpath=BASE/(f'N{delay}-advisory-HP0')/'verification.json';check(old['HP0_proof']);assert old['HP0_proof']['path']==str(vpath)
  v=json.loads(vpath.read_text());assert v['accepted'] and v['clock_period_FST_ticks']==50000
  tx=v['bindings']['transactions'];strict=v['bindings']['independent_run_proof'];check(tx);check(strict)
  x=json.loads(gzip.decompress(Path(tx['path']).read_bytes()));s=json.loads(Path(strict['path']).read_text());assert s['accepted'];bindings.extend([bind(vpath),tx,strict])
  clock=v['clock_period_FST_ticks'];reads=x['BP_facing_reads']
  assert len(reads)==v['BP_facing']['AR_transactions']==648
  for lane in ('i','d'):
   publications=v['UCE_endpoints'][lane]['advisory_publications'];assert len(publications)==1;e=publications[0];admit=e['advisory']['time'];end=e['time']
   # The compiled top XORs the BP DRAM base then adds dram_base_li. The
   # fixture's zero-base association is independently checked by all512 data bits.
   hits=[(i,q) for i,q in enumerate(reads) if q['addr']==(e['address']^0x80000000) and admit<=q['request_time']<end];assert len(hits)==1
   index,q=hits[0];assert index>0;previous=reads[index-1];assert q['sequence']==previous['sequence']+1
   pub=s['lanes'][lane]['publications'];assert len(pub)==1 and pub[0]['time']==end and pub[0]['insert']['address']==e['address']
   assert sum(b['data']<<(64*i) for i,b in enumerate(q['beats']))==pub[0]['insert']['data']
   for read in (previous,q):
    beats=read['beats'];assert len(beats)==8 and read['len']==7 and read['size']==3
    assert [b['time']-read['request_time'] for b in beats]==[(delay+1+i)*clock for i in range(8)]
    assert all(b['resp']==0 and b['last']==int(i==7) for i,b in enumerate(beats))
   def half(t):
    assert (t-admit)*2%clock==0;return (t-admit)*2//clock
   prevfull=previous['beats'][-1]['time'];full=q['beats'][-1]['time'];gap=q['request_time']-prevfull;assert gap==13*clock
   # Include a write already outstanding at the beginning of the pair.
   assert not [w for w in x['BP_facing_writes'] if w['request_time']<=full and w['request_time']+(w['complete']-w['request_cycle'])*clock>=previous['request_time']]
   post=end-full;assert post*2==clock*(112 if lane=='i' else 111)
   assert end-admit==clock*((101 if lane=='i' else 76)+2*delay)
   rows.append(dict(delay=delay,lane=lane,publication_address=hex(e['address']),predecessor_address=hex(previous['addr']),target_address=hex(q['addr']),predecessor_sequence=previous['sequence'],target_sequence=q['sequence'],predecessor_AR_halfcycles=half(previous['request_time']),predecessor_full_R_halfcycles=half(prevfull),target_AR_halfcycles=half(q['request_time']),target_first_R_halfcycles=half(q['beats'][0]['time']),target_full_R_halfcycles=half(full),publication_halfcycles=half(end),predecessor_full_to_target_AR_cycles=13,post_target_full_to_publication_halfcycles=post*2//clock,target_full512_payload_matches_publication=True))
 assert len(rows)==6 and len({(r['delay'],r['lane']) for r in rows})==6
 return dict(state='PASS six observed predecessor/target burst pairs and full512 payload associations; no new execution',source_timing=bind(HERE/'path-timing.json'),bindings=bindings,AXI_clock_FST_ticks=50000,rows=rows,scope='Closed SP1280 cold08 simulation only. Exact observed serialization and endpoint arithmetic, not a causal arbiter/resource diagnosis or architecture concurrency limit. D predecessor AR is8.5cycles before admission and its N0 full response0.5cycle before admission; two response-age contributions are not two complete post-admission transactions. No new1792/FPGA/application result. All relative times use halfcycles because I/D admissions have different phases.')

if __name__=='__main__':
 result=derive();dest=HERE/'serialized-read-pairs.json'
 if dest.exists():assert json.loads(dest.read_text())==result,'preserve changed proof'
 else:dest.write_text(json.dumps(result,indent=2)+'\n')
 print('PASS six predecessor/target pairs, exact full512 payload and endpoint timing')
