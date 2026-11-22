#!/usr/bin/env python3
"""Verify closed compact evidence; no reader, model, target or source mutation."""
import gzip,hashlib,json
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
 require(full['model']['sha256']==j['model']['sha256']=='a183aa7f912ce5a7346672ab57470912b2eb8627800e31443a596360cf9ee803','exact N40model')
 require(full['geometry']['delay']==40 and full['actual_l2']['total_bytes']==16384,'actual matched geometry')
 require(v['accepted'] and strict['accepted'] and receipt['returncode']==0 and receipt['owned_group_remaining'] is False,'closed complete gates')
 require(v['bindings']['raw_FST']['sha256']==strict['bindings']['fst']['sha256']=='f5c6da026551ba5c1ca3169e6f7d9cf90385dc87a1b0932bdf1a09304d862c90','same fullFST')
 t=json.loads(gzip.decompress((R/'hp0/audit01/transactions.json.gz').read_bytes()))
 require(len(t['external_reads'])==len(t['BP_facing_reads'])==648 and len(t['external_writes'])==len(t['BP_facing_writes'])==487,'complete transaction counts')
 for kind in ['reads','writes']:
  for ext,core in zip(t['external_'+kind],t['BP_facing_'+kind]):
   for k in ('id','addr','len','size','burst','lock','cache','prot','qos','sequence','request_cycle','request_time'):require(ext[k]==core[k],'opaque request ownership')
   for k in ('first_offer','first_accept','complete'):require(core[k]-ext[k]==40,'actual response shift')
   require(len(ext['beats'])==len(core['beats']),'beat count')
   for e,c in zip(ext['beats'],core['beats']):
    require(c['cycle']-e['cycle']==40,'beat age')
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
  require(data==pub['insert']['data'],'all512 target/publication bits')
  burst=strict['lanes'][lane]['bursts'][0]
  require(not burst['aborted'] and len(burst['beats'])==8,'eight real writes')
  for b in burst['beats']:require(b['data']==qs[0]['beats'][b['word']]['data'],'actual write payload')
 require(summary['external_source_archive_members_verified']==396 and summary['root_compact_snapshots']==50,'source closure')
 print('PASS compact closed N40 hashes, complete opaque records,40-cycle age and full512 target/L1-write joins; no reader/model')
if __name__=='__main__':main()
