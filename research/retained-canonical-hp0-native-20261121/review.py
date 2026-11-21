#!/usr/bin/env python3
"""Independent recorded-payload joins; no reader/build/target execution."""
import gzip,hashlib,importlib.util,json,struct
from pathlib import Path
R=Path(__file__).resolve().parent

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def main():
 a=json.loads((R/'admission.DRAFT.json').read_text());session=json.loads((R/'root-session.json').read_text());v=json.loads((R/'audit01/verification.json').read_text());t=json.loads(gzip.decompress((R/'audit01/transactions.json.gz').read_bytes()));s=json.loads((R/'inputs/original-strict.json').read_text())
 require(session['returncode']==0 and session['owned_group_remaining'] is False and v['accepted'] is True and s['accepted'] is True,'closed native audit/checker/root teardown')
 require(session['admission']==bind(R/'admission.DRAFT.json') and a['model']['sha256']=='b912913adc5fa98a0675bd323e7b37da7cbaecdabbb787ca3f466edcc4851de9','new canonicalmodel/admission')
 for field in ['fst','source_list','strict_proof','log','process']:require(bind(a[field]['path'])==a[field],'input drift '+field)
 for field in ['transactions','selected_events','selection']:
  rec=v['bindings'][field];require(bind(rec['path'])==rec,'audit data drift')
 require(v['bindings']['raw_FST']['sha256']==a['fst']['sha256']==s['bindings']['fst']['sha256'],'same originalfullFST')
 require(t['BP_facing_reads']==t['external_reads'] and t['BP_facing_writes']==t['external_writes'],'native full opaque streams')
 clock=v['clock_period_FST_ticks'];require(clock==50000,'actual modelclock')
 reads=t['BP_facing_reads'];writes=t['BP_facing_writes'];require(len(reads)==648 and len(writes)==487,'complete counts')
 for q in reads:
  require(q['len']==7 and q['size']==3 and len(q['beats'])==8 and q['first_offer']-q['request_cycle']==q['first_accept']-q['request_cycle']==1 and q['complete']-q['request_cycle']==8,'full64B first/full endpoints')
  require(all(q['beats'][j+1]['cycle']-q['beats'][j]['cycle']==1 for j in range(7)),'sustained beatspacing')
 spec=importlib.util.spec_from_file_location('maintained_strict','/home/coyang/zynq-parrot-linux-capacity/testing/rtl/retained-advisory-trace/validate.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 fixture=json.loads(Path(s['bindings']['fixture_manifest']['path']).read_text());elf=Path(fixture['elf']['path']);require(bind(elf)==fixture['elf'],'fixtureELF')
 rows=[]
 for lane in ['i','d']:
  pubs=v['UCE_endpoints'][lane]['advisory_publications'];require(len(pubs)==1,'one matching PFtarget');pub=pubs[0];admit=pub['advisory']['time'];end=pub['time'];address=pub['address']
  matches=[(idx,q) for idx,q in enumerate(reads) if q['addr']==(address^0x80000000) and admit<=q['request_time']<end];require(len(matches)==1,'unique address/window association');idx,q=matches[0]
  strict=s['lanes'][lane];require(len(strict['publications'])==len(strict['bursts'])==1,'strict publication/burst count');sp=strict['publications'][0];burst=strict['bursts'][0]
  words=[b['data'] for b in q['beats']];value=sum(w<<(64*i) for i,w in enumerate(words))
  require(sp['time']==end and sp['insert']['address']==address and sp['insert']['data']==value,'all512 HP0/publication bits')
  expected=struct.unpack('<8Q',module.elf_bytes(elf,address,64));require(tuple(words)==expected,'64 filebacked ELF bytes')
  require(not burst['aborted'] and not burst['errors'] and len(burst['beats'])==8 and {b['word'] for b in burst['beats']}==set(range(8)),'eight actual nonaborted SRAM writes')
  for b in burst['beats']:require(b['address']==address+8*b['word'] and b['data']==words[b['word']],'full SRAMwinning payload')
  req=[r for r in t['UCE'][lane] if r['address']==burst['request_address'] and r['first_accept']==burst['start'] and r['complete']==burst['end']];require(len(req)==1,'exact later demandACK association');req=req[0]
  def cycles(time):return (time-admit)/clock
  prev=reads[idx-1];prev_end=prev['beats'][-1]['time']
  for w in writes:
   wend=w['request_time']+(w['complete']-w['request_cycle'])*clock
   require(wend<prev['request_time'] or w['request_time']>q['beats'][-1]['time'],'no write overlaps observed pair')
  rows.append(dict(lane=lane,address=hex(address),advisory_kind=pub['advisory']['kind'],admit_to_AR=cycles(q['request_time']),admit_to_firstR=cycles(q['beats'][0]['time']),admit_to_fullR=cycles(q['beats'][-1]['time']),admit_to_publication=cycles(end),fullR_to_publication=(end-q['beats'][-1]['time'])/clock,predecessor_full_to_target_AR=(q['request_time']-prev_end)/clock,all512_bits_match_ELF_publication_and_eight_L1_writes=True,demand_to_firstACK=(req['first_accept']-req['request_time'])/clock,demand_to_fullACK=(req['complete']-req['request_time'])/clock,lookup_to_hit=(burst['hit']['time']-burst['hit']['lookup']['time'])/clock,critical_word=(burst['request_address']>>3)&7,critical_word_write_cycles=(next(b['time'] for b in burst['beats'] if b['word']==((burst['request_address']>>3)&7))-req['request_time'])/clock))
 result=dict(state='PASS independent canonicalb912 nativeHP0/full512target/ELF/L1-write association',model=a['model'],rows=rows,clock_FST_ticks=clock,reads=len(reads),writes=len(writes),bindings=[bind(R/'root-session.json'),bind(R/'audit01/verification.json'),bind(R/'audit01/transactions.json.gz'),bind(R/'inputs/original-strict.json'),bind(elf),bind(__file__)],scope='Newb912 native only; request/source joins use unique address+window+all512bits, not RID0 alone. ACK/critical word write is not CPUload/fetch readiness. No latency sensitivity/application/FPGA/architectureconcurrency claim.')
 out=R/'independent-review.json';require(not out.exists(),'preserve prior review');out.write_text(json.dumps(result,indent=2)+'\n');print(result['state']);print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
