#!/usr/bin/env python3
"""Read and archive only closed bank evidence; never import or launch tools."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE=Path(__file__).resolve().parent
BASE=Path('/home/coyang/fpga-artifacts/context-resume/uce-prefetch-bank-inference-20261121')
PREP=BASE/'xsim-only-adapter03/preparation01'
RUN=BASE/'xsim-only-adapter03/acquisition-v1/run01'
REMOTE=RUN/'remote'
COMPILED=REMOTE/'preparation01'
XSIM=COMPILED/'xsim-cycle-miter01'
ORIGINAL=BASE/'acquisition-v2/run01/remote/preparation01'
MARKER='UCE_PREFETCH_NETLIST_MITER_PASS full512=1 slots=4 banks=8 checked_edges=428 same_slot_writes=96 no_write_edges=108'

def require(ok,message):
 if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def info(path):
 raw=path.read_bytes();return dict(bytes=len(raw),sha256=sha(raw))
def bind(path):return dict(path=str(path.resolve()),**info(path))
def check(path,row):require(info(path)=={k:row[k] for k in ('bytes','sha256')},'binding '+str(path))

def inspect():
 files=set();large={}
 mapped=json.loads((XSIM/'session.json').read_text());owner=json.loads((REMOTE/'session.json').read_text());outer=json.loads((RUN/'session.json').read_text())
 require(info(XSIM/'session.json')['sha256']=='dcb275975da690f80b009e54afd3a08e59d7c6b144a64ce7d5a43e26542c89b2','exact mapped PASS')
 require(info(REMOTE/'session.json')['sha256']=='b0d279f182b97bf11ffe649901d00ca10e7d3abaee7424b84648de5c715af0b8','exact terminal owner')
 require(outer['state'].startswith('PASS Xsim-only') and outer['source_endcheck']=='PASS'
  and [x['returncode'] for x in outer['commands']]==[0]*5,'five outer commands0')
 require(owner['state'].startswith('PASS Xsim-only') and owner['worker_returncode']==0
  and owner['source_endcheck']=='PASS' and owner['owned_remaining']=={} and owner['global_tool_processes']==[],'terminal cleanup/source proof')
 require(mapped['state'].startswith('PASS actual primitive-mapped') and [x['returncode'] for x in mapped['commands']]==[0]*5,'five actual simulator commands0')
 files.update((RUN/'session.json',REMOTE/'session.json',XSIM/'session.json',REMOTE/'launch-admission.json'))
 for row in owner['outputs']:check(REMOTE/row['path'],row)
 for row in outer['commands']:
  output=RUN/row['stdout']['path'];check(output,row['stdout'])
  if row['label']=='collect':large['collection_transport_archive']=bind(output)
  else:files.add(output)
  err=RUN/(row['label']+'.stderr.log');check(err,row['stderr']);files.add(err)
 for row in mapped['commands']:
  rel=Path(row['log']['path']).relative_to(Path(outer['remote']));p=REMOTE/rel;check(p,row['log']);files.add(p)
 for row in mapped['inputs']['inputs']:
  p=COMPILED/row['path'];check(p,row);check(PREP/row['path'],row)
  if p.suffix=='.dcp':
   with zipfile.ZipFile(p) as z:require(z.testzip() is None,'DCP ZIP identity')
   large[row['path']]=bind(p)
  else:files.update((p,PREP/row['path']))
 files.update((PREP/'host-contract-proof.json',PREP/'timescale-check.log',PREP/'verify.log'))
 source=gzip.decompress((BASE/'preparation01/bp_uce.sv.gz').read_bytes());proof=json.loads((BASE/'preparation01/source-proof.json').read_text())
 require(sha(source)==proof['source']['sha256'] and sha(b''.join(source.splitlines(keepends=True)[963:975]))==proof['loop_sha256'],'exact source/loop extraction')
 block=(BASE/'preparation01/block.sv').read_bytes();dist=(BASE/'preparation01/distributed.sv').read_bytes()
 require(dist.replace(b'ram_style = "distributed"',b'ram_style = "block"')==block,'attribute-only candidate')
 require((PREP/'block.sv').read_bytes()==block and (PREP/'reference-timed.sv').read_bytes()==b'`timescale 1ps/1ps\n'+block,'reference timescale prefix only')
 files.update(BASE/'preparation01'/n for n in ('source-proof.json','extracted-loop.sv','block.sv','distributed.sv','bp_uce.sv.gz','bp_unicore_lite.sv.gz','bp_common_pkg.sv.gz'))
 adapter=(PREP/'adapters.sv').read_text();old_adapter=(BASE/'xsim-only-adapter01/preparation01/adapters.sv').read_text()
 require(adapter=='`timescale 1ps/1ps\n'+old_adapter and adapter==(BASE/'xsim-only-adapter02/preparation01/adapters.sv').read_text(),'wire adapter timescale-only progression')
 require(not re.search(r'\b(?:always|initial|assign|force)\b',adapter),'no behavioral adapter logic')
 miter=(PREP/'miter.sv').read_text();original_miter=(PREP/'original-miter.sv').read_text()
 require(miter.replace('uce_prefetch_fill_block_adapter block_dut','uce_prefetch_fill_block block_dut').replace('uce_prefetch_fill_distributed_adapter distributed_dut','uce_prefetch_fill_distributed distributed_dut')==original_miter,'unchanged stimulus/expected model')
 require(not (BASE/'xsim-only-adapter02/acquisition-v1/run01').exists(),'adapter02 remains unexecuted in frozen evidence')
 resources={};ports={}
 for kind,tuple_expected in [('block',[11,11,0,0,0,8,0,0]),('distributed',[363,11,352,0,512,0,0,0])]:
  for name in ('functional.v','primitives.tsv','utilization.rpt','synthesized.dcp'):
   require(info(COMPILED/kind/name)==info(ORIGINAL/kind/name),'immutable original v2 netlist/artifact '+kind+'/'+name)
  table=(COMPILED/kind/'utilization.rpt').read_text();row=re.search(r'^\| uce_prefetch_fill_probe\s*\|\s*\(top\)\s*\|([^\n]+)\|$',table,re.M)
  require(row is not None and [int(x.strip()) for x in row[1].split('|')]==tuple_expected,'actual vendor resources '+kind)
  resources[kind]=mapped['mapping'][kind]['resources'];require(resources[kind]['LUT']==tuple_expected[0] and resources[kind]['LUTRAM']==tuple_expected[2],'mapped/report equality')
  raw=(COMPILED/kind/'functional.v').read_text();start=raw.index('module uce_prefetch_fill_'+kind+'\n');end=raw.index('\n  wire ',start)
  declarations=re.findall(r'^\s*(input|output)\s*(?:\[(\d+):(\d+)\])?\s*(\\[^\s]+|[A-Za-z_]\w*)\s*;',raw[start:end],re.M)
  actual={n:(d,int(hi)-int(lo)+1 if hi else 1) for d,hi,lo,n in declarations}
  expected={'clk_i':('input',1),'prefetch_response_yumi':('input',1),'prefetch_response_slot':('input',2),'fsm_rev_data_li':('input',64),'prefetch_install_slot_r':('input',2)}
  hooks={n:n for n in expected}
  for n,count,width,direction in [('prefetch_fill_count_r',4,3,'input'),('prefetch_install_line_r',8,64,'output')]:
   for i in range(count):expected['\\'+n+'['+str(i)+']']=(direction,width);hooks['\\'+n+'['+str(i)+']']=n+'['+str(i)+']'
  module=adapter.split('module uce_prefetch_fill_'+kind+'_adapter\n')[1].split('endmodule')[0]
  connected=re.findall(r'\.\s*(\\[^\s]+|\w+)\s*\(([^)]+)\)',module)
  require(actual==expected and len(connected)==17 and dict(connected)==hooks,'all17 exact flattened names/widths/slices '+kind)
  ports[kind]=dict(ports=17,input_bits=sum(w for d,w in actual.values() if d=='input'),output_bits=sum(w for d,w in actual.values() if d=='output'))
  rows=[r.split('\t') for r in (COMPILED/kind/'primitives.tsv').read_text().splitlines()];counts=Counter(r[1] for r in rows)
  require(counts==mapped['mapping'][kind]['primitives_by_REF_NAME'],'actual primitive census '+kind)
 for item in json.loads((PREP/'timescale-proof.json').read_text())['compiled_source_files']:
  p=Path(item['file']['path']);check(p,item['file']);text=p.read_text()
  for match in re.finditer(r'(?m)^\s*module\s+(\S+)',text):require(re.search(r'(?m)^\s*`timescale\s+',text[:match.start()]),'explicit timescale '+str(p))
 xlog=(XSIM/'xsim.log').read_text();require(xlog.count(MARKER)==1 and 'Time resolution is 1 ps' in xlog and '$finish called at time : 23177 ns' in xlog,'actual coverage/normal finish')
 require('-d' in mapped['commands'][1]['argv'] and 'GLBL' in mapped['commands'][1]['argv'] and mapped['commands'][3]['argv'][2:8]==['unisims_ver','-L','unimacro_ver','-L','secureip','work.uce_prefetch_miter'],'actual vendor netlists/libraries')
 for failure in ('original-failure','adapter01-failure'):
  log=(PREP/failure/'xelab.log').read_text();s=json.loads((PREP/failure/'xsim-session.json').read_text())
  require([r['returncode'] for r in s['commands']]==[0,0,0,1] and not any(r['label']=='xsim' for r in s['commands']),'pre-stimulus failure '+failure)
  require(('10-3180' if failure=='original-failure' else '43-4099') in log,'specific failed elaboration cause')
 files.update((BASE/'acquisition-v2/run01/remote/vivado.log',BASE/'acquisition-v2/run01/remote/vivado.jou',ORIGINAL/'synthesize.tcl'))
 return dict(state='PASS independent closed mapped-bank source/inference/cycle/cleanup review only',resources=resources,ports=ports,
  checked_edges=428,same_slot_old_data_writes=96,no_write_edges=108,full_output_bits=512,
  actual_mapped_session=bind(XSIM/'session.json'),actual_owner_session=bind(REMOTE/'session.json'),
  records=[bind(p) for p in sorted(files)],external_large_artifacts=large,
  limitations='Directed functional cell cycle result; no exhaustive/SDF/physical timing/UCE integration/all16tiles/wholeCPU fit/application forecast.',
  active_Default_or_packing_outputs_read=False,reviewer_remote_operations=0,reviewer_tool_runs=0,
  documentation=info(HERE/'README.md'),closer=info(Path(__file__)))

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--archive',action='store_true');args=ap.parse_args();value=inspect();path=HERE/'verification.json'
 if args.archive:
  require(not path.exists(),'fresh bank archive required');(HERE/'snapshots').mkdir();blobs={};aliases=[]
  for record in value['records']:
   raw=Path(record['path']).read_bytes();name='snapshots/'+record['sha256']+'.gz'
   if name not in blobs:
    target=HERE/name;target.write_bytes(gzip.compress(raw,mtime=0));require(gzip.decompress(target.read_bytes())==raw,'lossless archive');blobs[name]=info(target)
   aliases.append(dict(original=record,snapshot=name))
  require(inspect()==value,'closed bank evidence changed');value.update(archives=blobs,snapshot_aliases=aliases);path.write_text(json.dumps(value,indent=2)+'\n')
 else:
  recorded=json.loads(path.read_text())
  for key,item in value.items():require(recorded[key]==item,'bank proof drift '+key)
  for name,item in recorded['archives'].items():require(info(HERE/name)==item,'gzip hash')
  for row in recorded['snapshot_aliases']:
   raw=gzip.decompress((HERE/row['snapshot']).read_bytes());require(len(raw)==row['original']['bytes'] and sha(raw)==row['original']['sha256'],'exact raw round trip')
 print('PASS mapped bank archive: actual428x512/96OLD/108nowrites; no wholeFPGA forecast')

if __name__=='__main__':main()
