#!/usr/bin/env python3
"""Selected-FST transport for the unchanged validated normal-Dcache Extractor.
This adapter changes no model tracing or extraction semantics.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import analyze_resume_data_reuse_vcd as core


def bind(path):
 p=Path(path).resolve();h=hashlib.sha256()
 with p.open('rb') as f:
  for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def suffixes():
 paths=dict(core.WATCH)
 for n in range(2):paths['context_'+str(n)]=f'be.physical_thread_context_id_r[{n}]'
 for kind in ('data_li','mask_li','data_lo'):
  for way in range(8):
   for field in ('tag','state'):paths[f'{kind}_{way}_{field}']=core.D+f'tag_mem_{kind}[{way}].{field}'
 return paths


def consume(lines,metadata=None,emit=None):
 expected=suffixes();mapping={};widths={};names={};values={};changes={};stamp=None;extractor=None;be_edge=dc_edge=0;ended=False;timescale=None
 def group():
  nonlocal be_edge,dc_edge
  if stamp is None:return
  new=dict(values);new.update(changes)
  rising=[name for name in ('clock','cache_clock') if values.get(name)==0 and new.get(name)==1]
  if rising:
   sample=dict(values);sample['_rising_clocks']=rising
   if 'clock' in rising:extractor.commit_edge(be_edge,stamp,sample);be_edge+=1
   if 'cache_clock' in rising:extractor.step(dc_edge,stamp,sample,process_commit=False);dc_edge+=1
  values.update(changes);changes.clear()
 for line in lines:
  f=line.rstrip('\n').split('\t')
  if f[0]=='#FST':
   if len(f)!=4 or int(f[2])<=int(f[1]):raise core.EvidenceError('bad/empty FST metadata')
   timescale=int(f[3])
  elif f[0]=='#SIGNAL':
   if stamp is not None or len(f)!=5 or f[1] not in expected or f[1] in names:raise core.EvidenceError('bad/late/duplicate signal declaration')
   _,key,width,handle,name=f;width=int(width);handle=int(handle)
   if not(name==expected[key] or name.endswith('.'+expected[key])):raise core.EvidenceError('wrong selected suffix')
   mapping.setdefault(handle,[]).append(key);widths[key]=width;names[key]=name
  elif f[0]=='#END':
   if ended:raise core.EvidenceError('duplicate FST EOF')
   group();ended=True
  elif f[0].startswith('#'):raise core.EvidenceError('unexpected reader record')
  else:
   if ended or len(f)!=3 or set(names)!=set(expected) or timescale is None:raise core.EvidenceError('bad/incomplete event stream')
   if extractor is None:extractor=core.Extractor(widths,metadata,emit)
   t,handle,bits=int(f[0]),int(f[1]),f[2].lower()
   if handle not in mapping or set(bits)-set('01xz'):raise core.EvidenceError('invalid selected event')
   if stamp is not None and t<stamp:raise core.EvidenceError('time reversal')
   if stamp is not None and t!=stamp:group()
   stamp=t
   for key in mapping[handle]:
    if len(bits)!=widths[key] or key in changes:raise core.EvidenceError('bad width/repeated event at timestamp')
    changes[key]=None if set(bits)&set('xz') else int(bits,2)
 if not ended or extractor is None:raise core.EvidenceError('reader EOF missing; no accepted coverage')
 result=extractor.report();result.update(signals=names,timescale_exponent=timescale,transport='selectedFST, unchangedExtractor; pre-edge dualclocks')
 return result


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fst',type=Path,required=True);p.add_argument('--reader',type=Path,required=True);p.add_argument('--model-source-list',type=Path,required=True);p.add_argument('--metadata',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=600);a=p.parse_args()
 if not 1<=a.timeout<=1800:raise ValueError('bounded reader timeout required')
 a.output.mkdir(parents=True,exist_ok=False);before=bind(a.fst);source=bind(core.__file__);code=bind(__file__)
 if source['sha256']!='0caba4960b3cfacc2717fd2c6bcf5ab0bd42024f62051bdfc7641e0f32c80f61':raise ValueError('original extractor changed')
 model=json.loads(a.model_source_list.read_text());critical=[]
 for suffix in ('bp_be/src/v/bp_be_dcache/bp_be_dcache.sv','bp_be/src/v/bp_be_calculator/bp_be_pipe_mem.sv','bp_me/src/v/cce/bp_uce.sv'):
  b=bind(ROOT/'import/black-parrot'/suffix)
  if b['path'] not in model or any(b[k]!=model[b['path']][k] for k in ('bytes','sha256')):raise ValueError('actual compiled/source mismatch')
  critical.append(b)
 # Resolve exact paths/widths from this closed FST's own hierarchy, not guessed IDs.
 listing=subprocess.run([str(a.reader.resolve()),str(a.fst.resolve()),'--list'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
 if listing.returncode or not listing.stdout.rstrip().endswith('#END'):raise ValueError('hierarchy list failed')
 declarations=[line.split('\t') for line in listing.stdout.splitlines() if line.startswith('#VAR')]
 selected={}
 for key,suffix in suffixes().items():
  found=[f for f in declarations if f[3]==suffix or f[3].endswith('.'+suffix)]
  if len(found)!=1:raise ValueError('missing/ambiguous signal '+key)
  selected[key]=found[0][3]
 selection=a.output/'selection.tsv';selection.write_text(''.join(k+'\t'+v+'\n' for k,v in selected.items()))
 cmd=[str(a.reader.resolve()),str(a.fst.resolve()),str(selection.resolve())];metadata=json.loads(a.metadata.read_text()) if a.metadata else None
 report=None;error=None
 with gzip.open(a.output/'events.jsonl.gz','wt') as events,gzip.open(a.output/'selected-events.tsv.gz','wt') as saved,(a.output/'reader.stderr').open('w') as err:
  proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=err,text=True);timer=threading.Timer(a.timeout,proc.kill);timer.daemon=True;timer.start()
  def lines():
   for line in proc.stdout:saved.write(line);yield line
  try:
   report=consume(lines(),metadata,lambda e:events.write(json.dumps(e,separators=(',',':'))+'\n'))
   if proc.wait()!=0:raise core.EvidenceError('reader failed or timed out')
  except BaseException as e:error=repr(e);proc.kill();proc.wait()
  finally:timer.cancel()
 if bind(a.fst)!=before or bind(core.__file__)!=source or bind(__file__)!=code:raise ValueError('input/source changed during audit')
 output=dict(state='PASS-normal-cache-invariants' if report is not None and error is None else 'FAIL-no-accepted-coverage',error=error,scope='Full actual normalDcache/tag/fill invariants only. Conditional victim ledgers are internal legacy diagnostics, not additional modeled execution or speedup.',fst=before,reader=bind(a.reader),adapter=code,extractor=source,critical_sources=critical,model_source_list=bind(a.model_source_list),selection=bind(selection),metadata=bind(a.metadata) if a.metadata else None,command=cmd,report=report)
 (a.output/'analysis.json').write_text(json.dumps(output,indent=2)+'\n')
 if error:raise ValueError(error)
 print('PASS normalDcache invariants',report['stats'])

if __name__=='__main__':main()
