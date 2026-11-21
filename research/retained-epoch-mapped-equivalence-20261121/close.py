#!/usr/bin/env python3
"""Close the failed attempt using only local immutable receipts; no tools/remote."""
from pathlib import Path
import hashlib,gzip,json,re
C=Path(__file__).resolve().parent;P=C.parent;R=P/'run01'
def bind(p):
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def main():
 assert bind(P/'admission.json')['sha256']=='2a5f97ca46820866f9f2bfd75af02e3ef3ee2c4728d37afa706ea81503749dc7'
 a=json.loads((P/'admission.json').read_bytes())
 for x in a['inputs']:assert bind(P/x['path'])=={k:x[k] for k in ('bytes','sha256')}
 s=json.loads((R/'session.json').read_bytes());assert s['state']=='FAIL source/resource endcheck';assert s['endcheck_error']=="AssertionError('HOME3GiB plus32MiB collection reserve')"
 assert [(x['label'],x['returncode']) for x in s['commands']]==[('idle-fresh',0),('upload',0),('pipeline',1),('no-orphans',0),('closed-files',0),('collect',0)]
 for x in s['commands']:assert bind(R/(x['label']+'.log'))==x['log']
 rows=json.loads((R/'closed-files.log').read_bytes())
 for x in rows:assert bind(R/'remote'/x['name'])=={k:x[k] for k in ('bytes','sha256')}
 for x in a['inputs']:assert bind(R/'remote'/x['path'])=={k:x[k] for k in ('bytes','sha256')}
 o=json.loads((R/'remote/owner.json').read_bytes());q=json.loads((R/'remote/pipeline.json').read_bytes());assert o==s['owner'];assert o['error']=="AssertionError('fixed phase total cap')" and o['returncode']==-15 and o['owned_group_gone'] and not o['terminal_vendor_processes']
 assert [(x['label'],x.get('returncode')) for x in q['commands']]==[('synth',0),('xvlog-global',0),('xvlog-netlist',0),('xvlog-reference',0),('xelab',None)]
 assert not (R/'remote/xsim.log').exists(),'no simulation was launched'
 for key,name in [('netlist','candidate-functional.v'),('DCP','candidate-synthesized.dcp')]:assert bind(R/'remote'/name)==q['mapping']['artifacts'][key]
 assert q['mapping']['D_epoch_raw_refs']['RAM64M']==24 and q['mapping']['D_epoch_raw_refs']['RAMD64E']==96
 assert not any(n for ref,n in q['mapping']['D_epoch_raw_refs'].items() if ref.startswith(('FD','LD')))
 snapshots=[]
 files=[P/'admission.json']+[P/x['path'] for x in a['inputs']]+[p for p in R.iterdir() if p.is_file()]+[p for p in (R/'remote').iterdir() if p.is_file()]
 for p in sorted(set(files)):
  raw=p.read_bytes();rel=str(p.relative_to(P));target=C/(rel.replace('/','__')+'.gz');target.write_bytes(gzip.compress(raw,mtime=0));assert gzip.decompress(target.read_bytes())==raw;snapshots.append(dict(original=rel,raw=bind(p),gzip=dict(path=target.name,**bind(target))))
 result=dict(state='CLOSED FAIL timeout plus overconservative reserve endcheck; no mapped functional result',root_execution=dict(session=94206,actual_exit=1,basis='Root coordinator actual exit acknowledgment'),admission_sha256=bind(P/'admission.json')['sha256'],primary_failure=dict(owner=o['error'],phase='xelab native compilation, after static elaboration/dataflow',Xsim_total_budget_seconds=240,synthesis_seconds=q['commands'][0]['seconds'],owner_seconds=o['seconds'],pipeline_returncode=o['returncode']),secondary_failure=dict(raw_acquire_endcheck=s['endcheck_error'],explanation='Frozen check requires full3GiB+32MiB even after collection; no code change or raw state relabel. Independently rehashed inputs all match. Later observed free3,253,510,144B exceeds3GiB but is below3GiB+32MiB; not exact failure-time measurement.'),independent_source_input_end_hashes='PASS local and collected remote copies',cleanup=dict(owned_group_gone=True,terminal_vendor_processes=[],independent_no_orphans_exit=0,collection_exit=0),mapping=q['mapping'],actual_top_level_collected_bytes=sum(x['bytes'] for x in rows),mapped_equivalence='NOT RUN; no Xsim invocation or qualified miter counts',warnings='Xelab43-4328 lane input sensitivity warnings in tick/drive preserved unresolved; not proven timeout cause.',snapshots=snapshots,closure_files={n:bind(C/n) for n in ('close.py','ANALYSIS.md')})
 (C/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print('manifest',bind(C/'manifest.json'),'snapshots',len(snapshots))
if __name__=='__main__':main()
