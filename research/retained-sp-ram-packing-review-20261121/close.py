#!/usr/bin/env python3
"""Read only the closed five-geometry RAM packing batch; never launch tools."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE=Path(__file__).resolve().parent
BASE=Path('/home/coyang/fpga-artifacts/context-resume/retained-sp-ram-packing-20261121/preparation01')
RUN=BASE/'run01'
REMOTE=RUN/'remote'
EXPECTED={1280:(149,6,40,2,37),1536:(147,4,46,4,44),1792:(278,6,54,4,52),1856:(287,8,58,4,56),1920:(285,8,58,4,56)}

def require(ok,message):
 if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def info(p):
 raw=p.read_bytes();return dict(bytes=len(raw),sha256=sha(raw))
def bind(p):return dict(path=str(p.resolve()),**info(p))
def check(p,row):require(info(p)=={k:row[k] for k in ('bytes','sha256')},'binding '+str(p))

def inspect():
 s=json.loads((RUN/'session.json').read_text());admission=json.loads((BASE/'admission.json').read_text())
 require(s['state']=='PASS five RAM-only mappings; no additive wholeCPU/fit/capacity proof' and s['source_endcheck']=='PASS','closed batch PASS')
 require(s['admission_sha256']==info(BASE/'admission.json')['sha256']=='7dbe7f7462d1df2d41ad52a5b9c01d4252e7d691ba67b802b64734c700710f3c','fixed admission')
 require([r['label'] for r in s['commands']]==['admission','upload','synthesis','no-orphans','closed-file-list','collect'] and all(r['returncode']==0 for r in s['commands']),'all six commands0')
 require('timeout --kill-after=15s 600s' in s['commands'][2]['argv'][-1] and s['commands'][2]['timeout_seconds']==640,'fixed whole-batch budget')
 require('pgrep' in s['commands'][3]['argv'][-1] and s['physical_operations']==0,'terminal no-orphans/physical scope')
 files={RUN/'session.json',BASE/'admission.json',BASE/'root-decision.json',BASE/'local-plan.json',BASE/'host-preparation-proof.json',BASE/'extract.log'};large={}
 for r in admission['inputs']:check(BASE/r['path'],r);files.add(BASE/r['path'])
 for r in s['commands']:
  p=RUN/(r['label']+'.log');check(p,r['log']);files.add(p)
 require(json.loads((RUN/'closed-file-list.log').read_text())==s['closed_top_level_artifacts'],'actual closed collection list')
 for r in s['closed_top_level_artifacts']:
  p=REMOTE/r['name'];check(p,r)
  if p.suffix=='.dcp':
   with zipfile.ZipFile(p) as z:require(z.testzip() is None,'DCP ZIP integrity')
   large[p.name]=bind(p)
  else:files.add(p)
 for n in ('ram_probe.sv','probe.tcl'):require((BASE/n).read_bytes()==(REMOTE/n).read_bytes(),'actual input unchanged '+n)
 proof=json.loads((BASE/'source-proof.json').read_text());parts=[]
 for r in proof['sources']:
  p=BASE/(r['revision'][:8]+'-source.sv.gz');raw=gzip.decompress(p.read_bytes());require(len(raw)==r['bytes'] and sha(raw)==r['sha256'],'exact original source '+r['revision'])
  text=raw.decode();ps=text.index('  localparam int set_width_lp');pe=text.index('  logic [1:0] tag_v',ps)
  a=text.index('  for (genvar lane = 0; lane < 2; lane++) begin : lane_fsm');b=text.index('    localparam int ways_lp',a)
  pair=(text[ps:pe],text[a:b]);parts.append(pair)
  for name,fragment in zip(('parameters','storage'),pair):require(fragment==(BASE/('extracted-'+name+'.sv')).read_text() and sha(fragment.encode())==r[('parameter' if name=='parameters' else 'storage')+'_sha256'],'exact source slice '+name)
 require(parts[0]==parts[1] and proof['sources']==admission['source'],'same RAM fragments in both frozen revisions')
 probe=(REMOTE/'ram_probe.sv').read_text();require(info(REMOTE/'ram_probe.sv')['sha256']=='d71e61f52e2df22884e1fbbdd2830f4c0ed8a928e7578ae94d10b8fe57324d56' and parts[0][0] in probe and probe.endswith(parts[0][1]+'  end\nendmodule\n'),'exact composed RAM-only wrapper')
 tcl=(REMOTE/'probe.tcl').read_text();require(info(REMOTE/'probe.tcl')['sha256']=='6b6a30ce5ea92aa445fc6e4b2448ea0a087c17758e3206c64cab264199c1e132','fixed Tcl')
 require(tcl.index('synth_design ')<tcl.index('create_clock ') and '-directive Default -global_retiming on -control_set_opt_threshold 1' in tcl and 'foreach lines {1280 1536 1792 1856 1920}' in tcl,'mapping-only clocks after synthesis')
 require('ACTUAL_TOOL_VERSION 2024.2' in (REMOTE/'vivado.log').read_text() and 'ACTUAL_MAX_THREADS 8' in (REMOTE/'vivado.log').read_text(),'actual version/threads')
 cases={}
 for n,(lut,ff,b36,b18,payload) in EXPECTED.items():
  p=REMOTE/('lines%d-utilization.rpt'%n);table=p.read_text();m=re.search(r'^\| retained_private_ram_probe\s*\|\s*\(top\)\s*\|([^\n]+)\|$',table,re.M)
  require(m is not None and [int(x.strip()) for x in m[1].split('|')]==[lut,lut,0,0,ff,b36,b18,0],'actual vendor report '+str(n))
  ports=[r.split('\t') for r in (REMOTE/('lines%d-primitives.tsv'%n)).read_text().splitlines()[1:]];counts=Counter();clocks=Counter()
  for row in ports:
   require(len(row)==13,'exact primitive row schema');name,ref=row[:2];match=re.match(r'lane_fsm\[([01])\]\.(payload|tag)_mem_reg',name);require(match is not None,'owned array primitive')
   lane,kind=match.groups();require(row[2]=='TDP' and row[7]=='READ_FIRST' and row[9:11]==['0','0'],'mapped read-first primitive settings')
   require(row[11]=='lane'+lane and row[12]=='' and row[5:7]==['0','0'],'single active owning clock, no other lane port')
   counts['lane'+lane+'/'+kind+'/'+ref]+=1;clocks[row[11]]+=1
  allrows=[r.split('\t') for r in (REMOTE/('lines%d-all-primitives.tsv'%n)).read_text().splitlines()];census=Counter(r[1] for r in allrows)
  require(census['RAMB36E1']==b36 and census['RAMB18E1']==b18 and sum(v for k,v in census.items() if re.fullmatch('LUT[1-6]',k))==lut and census['FDRE']==ff,'independent full primitive census')
  require({a:b for a,b in allrows if b.startswith('RAMB')}=={r[0]:r[1] for r in ports},'every RAM primitive has clock record')
  tiles=lambda kind:sum(v*(1 if k.endswith('RAMB36E1') else .5) for k,v in counts.items() if '/'+kind+'/' in k)
  actual=s['cases'][str(n)]
  require(dict(counts)==actual['primitive_counts'] and ports==actual['primitive_port_rows'] and tiles('payload')==payload and tiles('tag')==4 and actual['total_tiles']==payload+4 and actual['configured_full_payload_bytes_per_lane']==n*64,'recomputed packing/ownership matches receipt')
  check(p,actual['report']);check(REMOTE/('lines%d-synthesized.dcp'%n),actual['DCP']);check(REMOTE/('lines%d-all-primitives.tsv'%n),actual['all_primitive_census'])
  cases[str(n)]=dict(payload_bytes_per_lane=n*64,payload_tiles=payload,tag_tiles=4,total_tiles=payload+4,logic_LUT=lut,FF=ff,primitive_counts=dict(counts),owning_clock_counts=dict(clocks),full_primitive_census=dict(census))
 return dict(state='PASS independent closed RAM-only packing review',cases=cases,records=[bind(p) for p in sorted(files)],external_DCPs=large,
  batch_session=bind(RUN/'session.json'),source_fragments=proof['sources'],native_batch_seconds=600,SSH_seconds=640,
  limitation='Default RAM-only mapping; clocks created AFTER synthesis: not production retiming/timing, full-core correctness, additive whole-device fit or application benefit evidence.',
  subsequent_1792_active_preparation_read=False,reviewer_remote_operations=0,reviewer_tool_runs=0,reviewer_board_actions=0,
  closer=info(Path(__file__)),documentation=info(HERE/'README.md'))

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--archive',action='store_true');args=ap.parse_args();v=inspect();p=HERE/'verification.json'
 if args.archive:
  require(not p.exists(),'fresh archive required');(HERE/'snapshots').mkdir();blobs={};aliases=[]
  for r in v['records']:
   raw=Path(r['path']).read_bytes();name='snapshots/'+r['sha256']+'.gz'
   if name not in blobs:
    target=HERE/name;target.write_bytes(gzip.compress(raw,mtime=0));require(gzip.decompress(target.read_bytes())==raw,'lossless compression');blobs[name]=info(target)
   aliases.append(dict(original=r,snapshot=name))
  require(inspect()==v,'original evidence changed');v.update(archives=blobs,snapshot_aliases=aliases);p.write_text(json.dumps(v,indent=2)+'\n')
 else:
  recorded=json.loads(p.read_text())
  for k,x in v.items():require(recorded[k]==x,'evidence drift '+k)
  for n,r in recorded['archives'].items():require(info(HERE/n)==r,'archive drift')
  for a in recorded['snapshot_aliases']:
   raw=gzip.decompress((HERE/a['snapshot']).read_bytes());require(len(raw)==a['original']['bytes'] and sha(raw)==a['original']['sha256'],'raw roundtrip')
 print('PASS closed five-geometry RAM packing:41/48/56/60/60 tiles; clocks after synthesis; no whole-fit claim')

if __name__=='__main__':main()
