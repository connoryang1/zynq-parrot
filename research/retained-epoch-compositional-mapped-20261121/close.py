#!/usr/bin/env python3
"""Local compact closure; no tool/vendor/remote execution."""
from pathlib import Path
import json,hashlib,gzip,re
C=Path(__file__).resolve().parent;P=C.parent;R=P/'run01';BASE=P.parent;OLD=BASE/'preparation01';E=Path('/home/coyang/fpga-artifacts/context-resume/retained-epoch-mapped-extraction-20261121/preparation01')
def bind(p):
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def main():
 assert bind(P/'admission.json')['sha256']=='d802735bae2ac2b9bc9adb20cfe1dd2198afd7377c041a8e6489116019f45b9b';a=json.loads((P/'admission.json').read_bytes());s=json.loads((R/'session.json').read_bytes());o=json.loads((R/'remote/owner.json').read_bytes());q=json.loads((R/'remote/pipeline.json').read_bytes())
 assert s['state'].startswith('PASS') and s['source_endcheck']=='PASS' and o==s['owner'] and o['state'].startswith('PASS') and o['owned_group_gone'] and not o['terminal_vendor_processes']
 assert [(x['label'],x['returncode']) for x in s['commands']]==[('idle-fresh',0),('upload',0),('pipeline',0),('no-orphans',0),('closed-files',0),('collect',0)]
 for x in s['commands']:assert bind(R/(x['label']+'.log'))==x['log']
 assert [x['label'] for x in q['commands']]==['xvlog-global','xvlog-netlist','xvlog-reference','xelab','xsim'] and all(x['returncode']==0 for x in q['commands'])
 marker='EPOCH_CANONICAL_MAPPED_PASS cells=256x8 async_ports=2 unique=256 allones=256 clears=512 rmw=65280 wrap=1 reset_block=2';log=(R/'remote/xsim.log').read_text();assert log.count(marker)==1 and 'EPOCH_CANONICAL_MAPPED_COUNTS checks=132361' in log and 'Fatal:' not in log;assert '10-8884' not in (R/'remote/xvlog-reference.log').read_text()
 for x in a['inputs']:assert bind(Path(x['source']))=={k:x[k] for k in ('bytes','sha256')} and bind(R/'remote'/x['path'])=={k:x[k] for k in ('bytes','sha256')}
 rows=json.loads((R/'closed-files.log').read_bytes())
 for x in rows:assert bind(R/'remote'/x['name'])=={k:x[k] for k in ('bytes','sha256')}
 leaf=(R/'remote/bp_retained_epoch_ram.sv').read_bytes();whole=(R/'remote/candidate-final.sv').read_bytes();assert hashlib.sha256(leaf).hexdigest()=='a7673ffc8151b005fcfbfeb4a9e020098e0a2d409b2b79c0bebb2ebe9e0d8720' and hashlib.sha256(whole).hexdigest()=='68d1dd0c7df7e56ffe76317f9bae5a3ca3e09d13cb44d1167c0f737acefcbea6' and whole.count(leaf)==1
 assert (P/'miter.sv').read_bytes()==(OLD/'miter.sv').read_bytes().replace(b'#10000000000;',b"#(64'd10000000000);",1)
 for n in ['pipeline.py','owner.py','reference.sv','run.tcl','README.md']:assert (P/n).read_bytes()==(OLD/n).read_bytes()
 assert bind(OLD/'closed01/manifest.json')['sha256']=='52efb4ccf9ddad2a8832c71506ac9aada881adcd8146965126c6f6e32fe686c4';assert bind(E/'extraction.json')['sha256']=='6dfa362d85af68ba83f9fc939427a27777231937afd92c2ec75e868e7d7b2c9b'
 files={'admission.json':P/'admission.json'}
 for x in a['inputs']:files['input/'+x['path']]=Path(x['source'])
 for folder,label in [(R,'local'),(R/'remote','remote')]:
  for p in folder.iterdir():
   if p.is_file():files[label+'/'+p.name]=p
 for n in ['manifest.json','close.py']:files['prior-failure/'+n]=OLD/'closed01'/n
 for n in ['session.json','remote/owner.json','remote/pipeline.json','remote/xsim.log','remote/xvlog-reference.log']:files['prior-failure/'+n]=OLD/'run01'/n
 files['prior-failure/miter.sv']=OLD/'miter.sv'
 for n in ['extract.py','extraction.json','module-raw.v','mapped-epoch-extracted.v']:files['fullcontext-extraction/'+n]=E/n
 snaps=[]
 for name,p in sorted(files.items()):
  raw=p.read_bytes();target=C/(name.replace('/','__')+'.gz');target.write_bytes(gzip.compress(raw,mtime=0));assert gzip.decompress(target.read_bytes())==raw;snaps.append(dict(original=str(p),logical=name,raw=bind(p),gzip=dict(path=target.name,**bind(target))))
 result=dict(state='PASS closed actual isolated changed-memory compositional proof',root_execution=dict(session=31639,exit_code=0,basis='Root actual exit acknowledgment'),admission_sha256=bind(P/'admission.json')['sha256'],coverage=dict(cells='256x8',asynchronous_ports=2,unique_cells=256,allones_cells=256,clear_writes=512,RMW=65280,wrap=1,reset_blocks=2,qualified_checks=132361),owner_seconds=o['seconds'],actual_tool_exits=[dict(label=x['label'],returncode=x['returncode'],seconds=x['seconds']) for x in q['commands']],source_endcheck='PASS local+collected all inputs',cleanup=dict(owned_group_gone=True,vendor_remaining=[],independent_no_orphans_exit=0,collection_exit=0),leaf_exact_in_production=dict(source_leaf_sha256=hashlib.sha256(leaf).hexdigest(),production_sha256=hashlib.sha256(whole).hexdigest(),byte_offset=whole.index(leaf),BP_commit='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c'),mapping=q['mapping'],prior_failure='52efb4cc: unsized watchdog overflow explicitly corrected; no coverage/budget extension',fullcontext_limit='199ports, exact module primitive-complete but not original memory API; fullbackend mapped equivalence remains open',scope='Compositional changed-memory function only. Fullbackend RAM mapping, RTLcomponent/fullcore separate. No resynthesis/query/route/board/performance result.',snapshots=snaps,closure_files={n:bind(C/n) for n in ['close.py','README.md']});(C/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print('manifest',bind(C/'manifest.json'),'snapshots',len(snaps))
if __name__=='__main__':main()
