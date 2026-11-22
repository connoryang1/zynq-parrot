"""Read-only closed qualified256 observation bridge. No model/reader execution."""
import gzip
import hashlib
import json
from pathlib import Path
import tarfile

ROOT=Path('/home/coyang/fpga-artifacts/context-resume/retained256-qualification-20261122/scoped256-profile01')
FULL=ROOT.parent/'closed02/archive.json'
FULL_SHA='e9b134b8cd2a723ee0a766423242939a4b1bf73d0b06241583ab773e4fd1e7f3'
ORIGINAL='2c9d615694c0f59d9f85e6e247ba12494854378bd3b61334cf0cdaedc671e876'
SCOPED='1e9519cf83ede8d1bb7dd1d7924a98945cb274d8f2b666faf73737fb3376fe59'
ANCHORS={'proposal.json':'2b67359c906fe0f40e09a085fb84bda3fd0b97391b46d69102c5c37e235bcad5',
 'admission.json':'32067e7f49765684c8d3fc8435bcebcccabe57e307420dc6ca8d6d79cb21d634',
 'host-supervision.json':'1ce06de70dc719794ba0a7f035b5948d075f6e9ced6ab3016b5a0a6c1d3c87ae',
 'closed01/qualification01/qualification.json':'d4df1d329c0bdda8caee5a9f039066988b1c52edf98f6870e2eea94983fd5bdf',
 'closed01/build/evidence/build.json':'a26b739519790d48adafa2e52591d8cdedfcc0e3d51620df263be90ec2108ac7',
 'closed01/archive.json':'eaaaca7622cb9dc791f087cc02dc087be4e5e9c51583a7d2b9f4bc7973da5b0e',
 'ROOT-closure-review.json':'a5a19cb19e13424defbe495641b8a0075ed17b59cfe45c2033d70126f963e3d5'}
DOMAINS=('core252','observer_and_geometry','SP_strict162','actual_geometry16','capacity167')
COMPOSITE_SHA='47336fd5221941229ca1a47785dd413f13a3fc3a84428ffd0ae2e0dcad47b1a3'

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p).resolve();h=hashlib.sha256();n=0
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):n+=len(b);h.update(b)
 return dict(path=str(p),bytes=n,sha256=h.hexdigest())
def verify(row):require(bind(row['path'])==row,'changed closed file '+row['path'])
def ungzip_hash(p):
 h=hashlib.sha256();n=0
 with gzip.open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):n+=len(b);h.update(b)
 return dict(bytes=n,sha256=h.hexdigest())
def read():
 for rel,sha in ANCHORS.items():require(bind(ROOT/rel)['sha256']==sha,'closed anchor '+rel)
 require(bind(FULL)['sha256']==FULL_SHA,'full original durable closure')
 q=json.loads((ROOT/'closed01/qualification01/qualification.json').read_text())
 b=json.loads((ROOT/'closed01/build/evidence/build.json').read_text())
 p=json.loads((ROOT/'proposal.json').read_text());a=json.loads((ROOT/'closed01/archive.json').read_text())
 require(q['state']=='PASS-matched256-cold08-five-domain-literal-equivalence-strict-counter-geometry','qualified five-domain gate')
 require(q['admission']==bind(ROOT/'admission.json'),'exact admission')
 require(b['baseline_relink']['sha256']==ORIGINAL and b['binary']['sha256']==SCOPED and b['original_model']['sha256']==ORIGINAL,'untouched relink and scoped identity')
 expected=['Vbsg_nonsynth_zynq_testbench','Vbsg_nonsynth_zynq_testbench__ALL.a','Vbsg_nonsynth_zynq_testbench__Syms.cpp','Vbsg_nonsynth_zynq_testbench__Syms.d','Vbsg_nonsynth_zynq_testbench__Syms.o']
 require(b['changed_files']==expected,'Syms-only build differences')
 require(set(b['original_members'])==set(b['final_members']) and [k for k in b['original_members'] if b['original_members'][k]!=b['final_members'][k]]==['Vbsg_nonsynth_zynq_testbench__Syms.o'],'unchanged eval/archive/host objects')
 require(len(b['original_members'])==129,'all129 members')
 require(set(q['domains'])==set(DOMAINS),'exact five domains')
 framing=q['framing'];require(framing['all_section_bytes_exactly_cover_file'] and framing['complete_value_section_count']==framing['header_value_section_count']==1,'finalized complete raw trace')
 require(q['guest']['counter_values']==['1','1','1','1','8','8'] and q['guest']['returncode']==-6,'unchanged postPASS-only teardown scope')
 for key in ('strict','observer','geometry'):
  row=q[key];actual=ROOT/'closed01/qualification01'/key/'verification.json'
  require(bind(actual)['sha256']==row['sha256'] and bind(actual)['bytes']==row['bytes'],'returned '+key+' bytes')
  proof=json.loads(actual.read_text());require((proof.get('accepted') is True if key=='strict' else proof.get('state','').startswith('PASS')),'returned checker '+key)
 require(a['model']==b['binary'],'durable qualified model identity')
 verify(a['gzip']);verify(a['qualified_rawFST']);verify(a['copied_source_archive'])
 require(ungzip_hash(a['gzip']['path'])=={k:b['binary'][k] for k in ('bytes','sha256')},'lossless durable scoped model')
 return p,q,b,a

def review():
 p,q,b,a=read();rows={}
 for name in DOMAINS:
  d=q['domains'][name];r=d['reference'];c=d['clone']
  require(d['literal_bytes_equal'] is True,'literal complete domain '+name)
  for k in ('sha256','events','changes_by_index','first_tick','final_tick','timescale','clean_EOF'):require(r[k]==c[k],'domain summary '+name+' '+k)
  require(r['clean_EOF'] and r['first_tick']==0 and r['final_tick']==6209375000,'initialization through EOF '+name)
  rp=Path(r['canonical_file']['path']);cp=ROOT/'closed01/qualification01'/('clone-'+name)/'canonical.tsv.gz'
  verify(r['canonical_file']);require(bind(cp)['sha256']==c['canonical_file']['sha256'] and bind(cp)['bytes']==c['canonical_file']['bytes'],'durable clone canonical '+name)
  with gzip.open(rp,'rb') as rf,gzip.open(cp,'rb') as cf:
   h=hashlib.sha256();n=0
   while True:
    x=rf.read(1048576);y=cf.read(1048576);require(x==y,'literal byte mismatch '+name)
    if not x:break
    h.update(x);n+=len(x)
  require(h.hexdigest()==r['sha256'],'canonical digest '+name)
  rows[name]=dict(bytes=n,sha256=h.hexdigest(),events=r['events'],clean_EOF=True,first_tick=0,final_tick=r['final_tick'])
 return dict(state='PASS independent read-only matched256 clone closure',original_model=ORIGINAL,scoped_model=SCOPED,domains=rows,
  inputs=[bind(ROOT/x) for x in ANCHORS]+[bind(FULL)],fillwidth_limitation='Three fill-width constants are absent from414 scoped declarations; separately corroborate allthree=64 from closed original fulltrace before all-slot admission.',scope='Observation-only synthetic correctness; no all-slot/fit/FPGA/application/performance claim. Original full producer wrong-root failure preserved; composite is trusted, no retry.')

if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();require(not a.out.exists(),'fresh read-only review');a.out.write_text(json.dumps(review(),indent=2)+'\n');print(json.dumps(bind(a.out)))
