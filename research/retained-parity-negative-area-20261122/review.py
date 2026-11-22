#!/usr/bin/env python3
"""Read-only final parity mapping and existing capacity-boundary evidence."""
import collections,csv,gzip,hashlib,json,re
from pathlib import Path
PARITY=Path('/home/coyang/fpga-artifacts/context-resume/retained-cell36-parity-banks-mapping-20261122/preparation01')
RAM=Path('/home/coyang/fpga-artifacts/context-resume/retained-sp-ram-packing-20261121/preparation01')

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p);h=hashlib.sha256();n=0
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b);n+=len(b)
 return dict(path=str(p),bytes=n,sha256=h.hexdigest())
def review():
 session=json.loads((PARITY/'run01/session.json').read_text());a=json.loads((PARITY/'admission.json').read_text())
 require(session['state']=='PASS matched2 production mapping acquisitions; no fit or mapped-function claim' and session['ownership_final']['linux_claim_state']=='RELEASED' and not session['ownership_final']['owned_group_remaining'],'closed mapping/ownership')
 require(bind(PARITY/'admission.json')==session['admission'],'actual admission')
 for row in a['sources']:
  actual=bind(PARITY/row['name']);require(all(actual[k]==row[k] for k in ('bytes','sha256')),'source drift')
 require(bind(PARITY/'backend-parity.sv')['sha256']=='54d35b687bd8c67e20f0a5af254c7b4b9b0e43e170937e6cf2877bcc05213a4e','actual b295 bytes')
 require(a['component_gate']['sha256']=='2940a063098f20728c7dc0cebfe7dae6003ba2b6c2d66e41372f4e5abdd2c05e','actual component gate');require(bind(a['component_gate']['path'])==a['component_gate'],'component receipt bytes')
 arms={};raw=[]
 for arm in session['arms']:
  require(arm['owned_receipt']['returncode']==0 and arm['owned_receipt']['failure'] is None and not arm['owned_receipt']['owned_group_remaining'] and not arm['prelaunch_global_idle']['vendor_processes'],'actual0/idle/cleanup')
  for r in arm['artifacts']:require(bind(r['path'])==r,'artifact hash')
  folder=PARITY/'run01'/arm['arm'];text=(folder/'utilization.rpt').read_text();m=re.search(r'^\| retained_production_controls\s*\|\s*\(top\)\s*\|([^\n]+)\|$',text,re.M)
  require(m is not None,'actual top utilization');values=[int(x.strip()) for x in m[1].split('|')];d=dict(zip(['LUT','logic_LUT','LUTRAM','SRL','FF','RAMB36','RAMB18','DSP'],values));d['BRAM36_tiles']=d['RAMB36']+d['RAMB18']/2
  require(d==arm['analysis']['resources'],'independent utilization parse')
  ports=list(csv.DictReader((folder/'block-ports.tsv').open(),delimiter='\t'));groups=collections.Counter('/'.join(r[k] for k in ('REF_NAME','READ_WIDTH_A','READ_WIDTH_B','WRITE_MODE_A','WRITE_MODE_B')) for r in ports)
  require(len(ports)==d['RAMB36']+d['RAMB18'],'physical BRAM inventory')
  arms[arm['arm']]=dict(resources=d,seconds=arm['owned_receipt']['elapsed_s'],actual_port_groups=dict(groups))
  raw += [bind(folder/x) for x in ('functional.v','synthesized.dcp')]
 require(arms['baseline1792']['resources']['LUT']==1142 and arms['parity1792']['resources']['LUT']==1591 and arms['parity1792']['resources']['FF']==2221 and arms['parity1792']['resources']['BRAM36_tiles']==56,'actual negative area result')
 # Canonical RAM fragments are unchanged relative to the old RAM-only batch.
 source=(PARITY/'backend-baseline.sv').read_text();params=source[source.index('  localparam int set_width_lp'):source.index('  logic [1:0] tag_v')];start=source.index('  for (genvar lane = 0; lane < 2; lane++) begin : lane_fsm');storage=source[start:source.index('    localparam int ways_lp',start)]
 require(params==(RAM/'extracted-parameters.sv').read_text() and storage==(RAM/'extracted-storage.sv').read_text(),'exact current canonical RAM-only bridge')
 oldsession=json.loads((RAM/'run01/session.json').read_text());require(oldsession['state']=='PASS five RAM-only mappings; no additive wholeCPU/fit/capacity proof','closed old source slice mapping')
 for row in oldsession['closed_top_level_artifacts']:
  actual=bind(RAM/'run01/remote'/row['name']);require(all(actual[k]==row[k] for k in ('bytes','sha256')),'historical sealed RAM artifact '+row['name'])
 mapping={}
 for n in (1792,1856,1920):
  folder=RAM/'run01/remote';p=folder/f'lines{n}-primitives.tsv';rows=list(csv.DictReader(p.open(),delimiter='\t'));per={}
  for lane in (0,1):
   for kind in ('payload_mem','tag_mem'):
    picked=[r for r in rows if f'lane_fsm[{lane}].{kind}' in r['cell']]
    per[str(lane)+':'+kind]=dict(collections.Counter('/'.join(r[k] for k in ('primitive','read_a','read_b')) for r in picked))
  primitive=collections.Counter(r['primitive'] for r in rows);mapping[str(n)]=dict(tiles=primitive['RAMB36E1']+primitive['RAMB18E1']/2,parts=per,ports=bind(p),report=bind(folder/f'lines{n}-utilization.rpt'),checkpoint=bind(folder/f'lines{n}-synthesized.dcp'))
 geometry={}
 for n in (1792,1793,1800,1824,1856):
  geometry[str(n)]=dict(payload_words=n*8,tag_bits=29,local_tag_addr_bits=(n-1).bit_length(),local_payload_addr_bits=(n*8-1).bit_length(),global_tag_addr_bits=(2*n-1).bit_length(),global_payload_addr_bits=(2*n*8-1).bit_length(),ways=(n+255)//256,RR_bits=(((n+255)//256)-1).bit_length(),total_full64B_payload_bytes=2*n*64,mapped_in_existing_artifacts=n in (1792,1856))
 return dict(state='PASS read-only negative parity area/current RAM boundary review',admission=bind(PARITY/'admission.json'),session=bind(PARITY/'run01/session.json'),settings=a['settings'],arms=arms,raw_artifacts=raw,
  boundary=dict(ram_source_bridge=dict(parameters_sha256=hashlib.sha256(params.encode()).hexdigest(),storage_sha256=hashlib.sha256(storage.encode()).hexdigest()),old_RAM_only_settings=bind(RAM/'probe.tcl'),old_source_proof=bind(RAM/'source-proof.json'),old_session=bind(RAM/'run01/session.json'),observed_mappings=mapping,source_geometry=geometry,conclusion='1793/1800/1824 are UNMEASURED; no address/tag/RR width cliff at1792, but ways7->8 and a partial final way.1856 adds two36-bit RAMB36 payload cells PERlane while tag mapping is unchanged. Cannot locate exact tail-allocation threshold or prove<=58tiles from these reports. No source/layout change or new mapping was run.'),
  scope='Standalone source/resource evidence, not whole device fit/route/FPGA/application performance. Parity1792 has+449LUT/+10FF and no RAM benefit versus matched baseline and is not selected.')
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(review(),indent=2)+'\n');print(json.dumps(bind(a.out)))
