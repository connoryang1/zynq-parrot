#!/usr/bin/env python3
"""Independent closed mapped packet/source validation; no vendor or execution."""
import argparse,collections,csv,gzip,hashlib,json,re
from pathlib import Path
R=Path('/home/coyang/fpga-artifacts/linux-cell36-mapping-20261122-02')
S=R/'run01'

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p);h=hashlib.sha256();n=0
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b);n+=len(b)
 return dict(path=str(p),bytes=n,sha256=h.hexdigest())
def external_review():
 s=json.loads((S/'session.json').read_text());a=json.loads((R/'admission.json').read_text())
 require(bind(R/'admission.json')['sha256']=='1935abc72c04550516590e6a10563771b3fc0291ee3ad65da1e45e320a31a02f','actual reviewed acquisition admission')
 require(s['admission']==bind(R/'admission.json') and s['source_endcheck']=='PASS','source identity/complete endcheck')
 require(s['state']=='PASS all3 production mapping acquisitions; no fit or mapped-function claim','closed all3 acquisitions')
 require(s['ownership_final']['linux_claim_state']=='RELEASED' and not s['ownership_final']['owned_group_remaining'],'released own process groups')
 require(not s['foreign_inventory_events'] and s['no_board_operations'],'perVM conflict/board state')
 for row in a['sources']:
  actual=bind(R/row['name']);require(all(actual[k]==row[k] for k in ('bytes','sha256')),'consumed source '+row['name'])
 require(bind(R/'backend-baseline.sv')['sha256']=='68d1dd0c7df7e56ffe76317f9bae5a3ca3e09d13cb44d1167c0f737acefcbea6' and bind(R/'backend-packed.sv')['sha256']=='2f7b8985c180f2f32673a5e6dbe531599f88776ccdf65db085d07da3e5dd9b39','exact8df/b12 source bytes')
 settings=a['settings'];require(settings['I_invalidate']==0 and settings['D_invalidate']=='variable' and settings['all_other_client_ports']=='live' and settings['clock_period_ns']==50 and settings['global_retiming']=='on','actual production option scope')
 arms={};resources_names=['LUT','logic_LUT','LUTRAM','SRL','FF','RAMB36','RAMB18','DSP'];raws=[]
 for arm in s['arms']:
  name=arm['arm'];p=S/name;life=arm['owned_receipt']
  require(life['returncode']==0 and life['failure'] is None and not life['owned_group_remaining'] and not arm['prelaunch_global_idle']['vendor_processes'],'actual command0/idle/owned cleanup')
  for row in arm['artifacts']:require(bind(row['path'])==row,'mapped artifact drift '+row['path'])
  t=(p/'utilization.rpt').read_text();m=re.search(r'^\| retained_production_controls\s*\|\s*\(top\)\s*\|([^\n]+)\|$',t,re.M);require(m is not None,'top actual report row')
  vals=[int(x.strip()) for x in m[1].split('|')];require(len(vals)==8,'resource columns')
  d=dict(zip(resources_names,vals));d['BRAM36_tiles']=d['RAMB36']+d['RAMB18']/2
  require(d==arm['analysis']['resources'],'independent actual report totals')
  ports=list(csv.DictReader((p/'block-ports.tsv').open(),delimiter='\t'))
  require(len(ports)==d['RAMB36']+d['RAMB18'],'physical BRAM inventory')
  port_types=collections.Counter('/'.join(x[k] for k in ('REF_NAME','READ_WIDTH_A','READ_WIDTH_B','WRITE_MODE_A','WRITE_MODE_B')) for x in ports)
  require(not (p/'blackboxes.txt').read_text().strip(),'no blackbox')
  clocks=(p/'clocks.tsv').read_text();require('50.000' in clocks or '\t50\t' in clocks,'clock period report')
  primitives=list(csv.DictReader((p/'primitives.tsv').open(),delimiter='\t'))
  dsp=[x['name'] for x in primitives if x['IS_PRIMITIVE']=='1' and x['REF_NAME']=='DSP48E1']
  require(len(dsp)==d['DSP'],'actual DSP primitive count')
  arms[name]=dict(resources=d,native_seconds=life['elapsed_s'],BRAM_port_groups=dict(port_types),DSP_names=dsp,metadata=arm['analysis']['metadata_raw_named_refs'])
  raws += [bind(p/x) for x in ('functional.v','synthesized.dcp')]
 require(set(arms)=={'baseline1792','packed1792','packed1911'},'exact fixed arms')
 require(arms['baseline1792']['resources']['LUT']==1142 and arms['packed1792']['resources']['LUT']==2617 and arms['packed1911']['resources']['LUT']==2256,'negative actual results')
 v=(S/'packed1792/functional.v').read_text();start=v.index('  DSP48E1 #(');end=v.index('endmodule',start);block=v[start:end]
 require('.USE_MULT("MULTIPLY")' in block and "p_4_in,1'b0" in block,'actual DSP input shape')
 return dict(state='PASS independently verified mapped acquisition/source/report bytes',settings=settings,arms=arms,session=bind(S/'session.json'),admission=bind(R/'admission.json'),raw_artifacts=raws,
  diagnosis='The single DSP A uses word/control p_4_in shifted1 and constantB36. Wide variable72-bit slicing/indexing is evidenced; no proof the DSP implements line*15. Deep two-RW-port RAM output mux is also present but exact area savings are unmeasured.',
  limitation='Standalone constrained synthesis only. Macro/subcell counts and raw name groups overlap. No mapped functional, whole-chip fit/routing or application result; old functional and operational-budget statuses preserved.')

def portable(root):
 m=json.loads((root/'manifest.json').read_text())
 for row in m['files']:
  p=root/row['local'];b=p.read_bytes();require(len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],'local proof '+row['local'])
  if 'original' in row:
   raw=gzip.decompress(b);require(len(raw)==row['original']['bytes'] and hashlib.sha256(raw).hexdigest()==row['original']['sha256'],'lossless snapshot '+row['local'])
 return dict(state='PASS portable closed mapping curation',files=len(m['files']))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--external',action='store_true');p.add_argument('--out',type=Path);a=p.parse_args();r=external_review() if a.external else portable(Path(__file__).resolve().parent)
 if a.out:a.out.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r if not a.out else bind(a.out),sort_keys=True))
