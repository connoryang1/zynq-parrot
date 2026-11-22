#!/usr/bin/env python3
"""Verify closed compact evidence; no reader, model, target or source mutation."""
import gzip,hashlib,json,struct
from pathlib import Path
R=Path(__file__).resolve().parent

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 b=Path(p).read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def main():
 m=json.loads((R/'manifest.json').read_text())
 for name,rec in m['files'].items():require(bind(R/name)==rec,'packet changed '+name)
 require(sum(p.stat().st_size for p in R.rglob('*') if p.is_file())<=m['cap_bytes'],'packet cap')
 provenance=json.loads((R/'provenance.json').read_text())
 for row in provenance['records']:
  s=row['snapshot'];require(bind(R/s['path'])=={k:s[k] for k in ('bytes','sha256')},'copy mismatch '+s['path'])
 full=json.loads((R/'fullcore/manifest.json').read_text());v=json.loads((R/'hp0/audit01/verification.json').read_text());j=json.loads((R/'hp0/independent-review.json').read_text());strict=json.loads((R/'hp0/inputs/original-strict.json').read_text());receipt=json.loads((R/'hp0/root-session.json').read_text());summary=json.loads((R/'summary.json').read_text())
 require(full['model']['sha256']==j['model']['sha256']=='692d6430d08f31806214384604524d0753079c2e48a0ae837d6a950a4351265e','exact N200model')
 require(full['geometry']['delay']==200 and full['actual_l2']['total_bytes']==16384,'actual matched geometry')
 require(v['accepted'] and strict['accepted'] and receipt['returncode']==0 and receipt['owned_group_remaining'] is False,'closed complete gates')
 require(v['bindings']['raw_FST']['sha256']==strict['bindings']['fst']['sha256']=='cb3863a73a8c9efec3867cddb6c81c593485c50a6b80397c895df70ed5609091','same fullFST')
 elf=gzip.decompress((R/'program/advisory-prog.riscv.gz').read_bytes())
 require(hashlib.sha256(elf).hexdigest()=='3fe096173e3a63b2656c1fadf0a058a328fb5f1ee375be652176408856f897b8','exact portable fixtureELF')
 def elf_bytes(addr):
  require(elf[:6]==b'\x7fELF\x02\x01','ELF64 little-endian')
  phoff=struct.unpack_from('<Q',elf,32)[0];entsize,count=struct.unpack_from('<HH',elf,54)
  for i in range(count):
   kind,_,off,va,_,filesz,_,_=struct.unpack_from('<IIQQQQQQ',elf,phoff+i*entsize)
   if kind==1 and va<=addr and addr+64<=va+filesz:return elf[off+addr-va:off+addr-va+64]
  raise ValueError('full64B fixture data not filebacked')
 t=json.loads(gzip.decompress((R/'hp0/audit01/transactions.json.gz').read_bytes()))
 require(len(t['external_reads'])==len(t['BP_facing_reads'])==648 and len(t['external_writes'])==len(t['BP_facing_writes'])==487,'complete transaction counts')
 for kind in ['reads','writes']:
  for ext,core in zip(t['external_'+kind],t['BP_facing_'+kind]):
   for k in ('id','addr','len','size','burst','lock','cache','prot','qos','sequence','request_cycle','request_time'):require(ext[k]==core[k],'opaque request ownership')
   for k in ('first_offer','first_accept','complete'):require(core[k]-ext[k]==200,'actual response shift')
   require(len(ext['beats'])==len(core['beats']),'beat count')
   for e,c in zip(ext['beats'],core['beats']):
    require(c['cycle']-e['cycle']==200,'beat age')
    for k in set(e)-{'time','cycle'}:require(e[k]==c[k],'opaque response field')
 require(v['R_stream']['max_occupancy']==8 and v['B_stream']['max_occupancy']==1,'observed queues')
 require(j['reads']==648 and j['writes']==487,'independent totals')
 for row in j['rows']:
  lane=row['lane'];require(row['all512_bits_match_ELF_publication_and_eight_L1_writes'],'full data oracle')
  pub=strict['lanes'][lane]['publications'][0];addr=pub['insert']['address']
  advisory=v['UCE_endpoints'][lane]['advisory_publications'][0]
  qs=[q for q in t['BP_facing_reads'] if q['addr']==(addr^0x80000000) and advisory['advisory']['time']<=q['request_time']<advisory['time']]
  require(len(qs)==1,'unique target address/advisory-window association')
  data=sum(b['data']<<(64*i) for i,b in enumerate(qs[0]['beats']))
  require(data==pub['insert']['data']==int.from_bytes(elf_bytes(addr),'little'),'all512 target/publication/ELF bits')
  burst=strict['lanes'][lane]['bursts'][0]
  require(not burst['aborted'] and len(burst['beats'])==8,'eight real writes')
  require({b['word'] for b in burst['beats']}==set(range(8)),'all eight actual words')
  for b in burst['beats']:require(b['data']==qs[0]['beats'][b['word']]['data'] and b['address']==addr+8*b['word'],'actual winning write payload/address')
 require(summary['external_source_archive_members_verified']==396 and summary['root_compact_snapshots']==50,'source closure')
 comparison=json.loads((R/'comparison-0-40-200.json').read_text());require([a['delay'] for a in comparison['arms']]==[0,40,200],'all controls preserved')
 for arm in comparison['arms']:
  d=arm['delay'];require(arm['R_stream']['minimum_age_setting']==arm['B_stream']['minimum_age_setting']==d,'actual all-R/B age')
  for row in arm['joined_targets']:
   require(row['all512_bits_match_ELF_publication_and_eight_L1_writes'],'closed all-control data joins')
   base=next(x for x in comparison['arms'][0]['joined_targets'] if x['lane']==row['lane'])
   require(row['admit_to_AR']-base['admit_to_AR']==d and row['admit_to_publication']-base['admit_to_publication']==2*d,'recorded serialized endpoint deltas')
 print('PASS compact closed N200 hashes, complete opaque records,200-cycle age and full512 target/L1-write joins; no reader/model')
if __name__=='__main__':main()
