#!/usr/bin/env python3
"""Local lossless timeout closure only; no remote/vendor operation."""
from pathlib import Path
import json,hashlib,gzip
C=Path(__file__).resolve().parent;P=C.parent;R=P/'run01'
def bind(p):
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def main():
 assert bind(P/'admission.json')['sha256']=='952d95ad5368f466c0fa9de20a9390c63f01ee9b6ee6db443ed0f72bc95a7078';a=json.loads((P/'admission.json').read_bytes());s=json.loads((R/'session.json').read_bytes());q=json.loads((R/'remote/pipeline.json').read_bytes());o=json.loads((R/'remote/owner.json').read_bytes())
 assert s['state']=='FAIL preserve closed/partial mapped evidence' and s['source_endcheck']=='PASS';assert [(x['label'],x['returncode']) for x in s['commands']]==[('idle-fresh',0),('upload',0),('pipeline',1),('no-orphans',0),('closed-files',0),('collect',0)]
 for x in s['commands']:assert bind(R/(x['label']+'.log'))==x['log']
 for x in a['inputs']:
  expected={k:x[k] for k in ('bytes','sha256')};assert bind(Path(x['source']))==expected and bind(R/'remote'/x['path'])==expected
 rows=json.loads((R/'closed-files.log').read_bytes())
 for x in rows:assert bind(R/'remote'/x['name'])=={k:x[k] for k in ('bytes','sha256')}
 assert o==s['owner'] and o['error']=="AssertionError('fixed Xelab600s cap')" and o['owned_group_gone'] and not o['terminal_vendor_processes']
 assert [(x['label'],x.get('returncode')) for x in q['commands']]==[('xvlog-global',0),('xvlog-netlist',0),('xvlog-reference',0),('xelab',None)]
 assert not (R/'remote/xsim.log').exists() and q['synthesis_invocations']==0
 assert bind(R/'remote/candidate-functional.v')['sha256']=='e06ac16adec7d02b4cfb227902c563d985bb2554bdcbf86b1555571d8e63b35e';assert bind(R/'remote/candidate-synthesized.dcp')['sha256']=='ab718a9843d8cb3f6849f2febc5b1d5f52d05c4fea94d48f25d89b0d00969c6d'
 files={'admission.json':P/'admission.json'}
 for x in a['inputs']:files['input/'+x['path']]=Path(x['source'])
 for base,label in [(R,'local'),(R/'remote','remote')]:
  for p in base.iterdir():
   if p.is_file():files[label+'/'+p.name]=p
 snaps=[]
 for name,p in sorted(files.items()):
  b=p.read_bytes();dest=C/(name.replace('/','__')+'.gz');dest.write_bytes(gzip.compress(b,mtime=0));assert gzip.decompress(dest.read_bytes())==b;snaps.append(dict(original=str(p),logical=name,raw=bind(p),gzip=dict(path=dest.name,**bind(dest))))
 result=dict(state='CLOSED FAIL Xelab600s timeout; no mapped functional result',root_execution=dict(session=50894,exit_code=1,basis='Root actual exit acknowledgment'),admission_sha256=bind(P/'admission.json')['sha256'],primary_failure=o['error'],owner_seconds=o['seconds'],acquisition_seconds=s['seconds'],synthesis_invocations=0,Xsim_invocations=0,qualified_miter_counts='NONE: simulation never started',source_endcheck='PASS all local+collected remote inputs and e06/ab718 immutable',cleanup=dict(owned_group_gone=True,terminal_vendor_processes=[],independent_no_orphans_exit=0,collection_exit=0),actual_top_level_bytes=sum(x['bytes'] for x in rows),scope='No hardware mismatch demonstrated. Fullbackend mapped functional equivalence remains open; no repeated fullbackend Xelab attempt authorized. Earlier actual mapping/component/fullcore results remain separate.',warnings='Original43-4328 tick/drive sensitivity warnings preserved without causal claim or waiver.',snapshots=snaps,closure_files={n:bind(C/n) for n in ['close.py','ANALYSIS.md']});(C/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print('manifest',bind(C/'manifest.json'),'snapshots',len(snaps))
if __name__=='__main__':main()
