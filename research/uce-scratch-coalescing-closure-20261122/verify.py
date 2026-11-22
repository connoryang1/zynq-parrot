#!/usr/bin/env python3
"""Portable replay of closed logs/source/budgets; no model/compiler/tool. --external checks raw traces/models."""
import argparse,gzip,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
PINS={'attempt01':'a255512f2105c4eed2546480615914f073c7204d851481ef923a92162f928f68','baseline-attempt01':'5b88cc7ef84d7986908806b8b4e9a177c593cec66c5dbc46925234a18f46dea3','matched-attempt01':'753cebda957c71a4bbe077a7e42fc9348f122fba58029f9a1e8311bed3bac434','legacy128-attempt01':'64c3ba2851c9652c05cc4a961638f3ccb0deaa8db29b80fc5b9c58dc7bb972ce'}
def sha(b):return hashlib.sha256(b).hexdigest()
def need(v,m):
 if not v:raise ValueError(m)
def verify(root,external=False):
 d=json.loads((root/'closure.json').read_text());data={}
 for x in d['snapshots']:
  p=root/x['file'];need(str(p.resolve()).startswith(str(root.resolve())+'/'),'relative snapshot path');z=p.read_bytes();b=gzip.decompress(z);need(sha(z)==x['gzip_sha256'] and len(b)==x['plain_bytes'] and sha(b)==x['plain_sha256'],'lossless snapshot '+x['logical']);need(x['logical'] not in data,'unique logical snapshot');data[x['logical']]=b
 need(len(data)==164,'all164 snapshots')
 families={}
 for family,pin in PINS.items():
  raw=data[family+'/manifest.json'];need(sha(raw)==pin,'actual ROOT manifest '+family);v=json.loads(raw);need(v['source_before']==v['source_after'],'source end '+family)
  need(v['aggregate_stage_peak_allocated_bytes']<128*1024**2 and v['aggregate_trace_peak_bytes']<4*1024**2,'fixed aggregate stage/trace cap')
  for x in v['commands']:
   l=x['owned_receipt'];need(not l['failure'] and not l['owned_group_remaining'] and l['group_states'][-1]['members']==[],'owned cleanup '+family)
  families[family]=v
 need(all(families[k]['state'].startswith('FAIL') for k in ('attempt01','baseline-attempt01','matched-attempt01')),'all historical failures preserved');need(families['legacy128-attempt01']['state'].startswith('PASS'),'separate legacy result')
 for family in ('attempt01','baseline-attempt01'):
  text=data[family+'/I64-BedRock64/unit.log'].decode();need('cycle=1024 addr=83000360 beat=4' in text and 'got=a55a008300034000 expected=a55a008300034004' in text,'same original input-frame failure')
 mixed=data['matched-attempt01/baseline-I128-mixed/unit.log'].decode();need('phase=disabled-normal' in mixed and 'cycle=2075 beat=2' in mixed and 'data_v=0' in mixed,'mixed baseline liveness failure');need(not any('candidate-I128-mixed' in x['cwd'] for x in families['matched-attempt01']['commands']),'mixed candidate never executed')
 cases=[]
 for family,labels in [('matched-attempt01',['baseline-D64-all64','candidate-D64-all64','baseline-I64-all64','candidate-I64-all64']),('legacy128-attempt01',['baseline-I128-BedRock128','candidate-I128-BedRock128'])]:
  for label in labels:
   rows=[x for x in families[family]['commands'] if Path(x['cwd']).name==label or Path(x['cwd']).parent.name==label];need(len(rows)==5,'five completed phases '+label)
   for x in rows:
    l=x['owned_receipt'];need(not x['failure'] and (l['returncode']!=0 if x['expected_failure'] else l['returncode']==0),'expected phase result '+label);need(x['environment']['CCACHE_DISABLE']==x['environment']['SCCACHE_DISABLE']=='1' and x['environment']['OBJCACHE']=='','cache disabled')
   argv=rows[0]['argv'];width='128' if 'BedRock128' in label else '64';need('-DBP_ICACHE_FILL_WIDTH='+width in argv and '-DBP_BEDROCK_FILL_WIDTH='+width in argv and '-DBP_DCACHE_FILL_WIDTH=64' in argv,'actual width flags '+label)
   need(('-Ginstruction_p=1' in argv)==('I64' in label or 'I128' in label),'I/D role '+label)
   prefix=family+'/'+label+'/';raw=data[prefix+'unit.log'].decode();need('[UCE-SCRATCH-TURNOVER] PASS:' in raw and ('[UCE-RETAINED] PASS:' in raw if 'D64' in label else '[UCE-RETAINED-I] PASS:' in raw),'normal full512 scoreboards '+label)
   need('UCE prefetch response has no live slot' in data[prefix+'short-response.log'].decode(),'specific negative '+label);need('[UCE-SHORT-DRAIN] PASS:' in data[prefix+'short-response-drain.log'].decode(),'specific drain '+label)
   pin='5ff8627b7373bfc9ce9be5cbd315d222d6b0efdec2e887b3d976038be84af725' if label.startswith('baseline') else 'c565fce280c3559066a1ebfaf1e0385b2320df67f89a3d12ed52c7852544c688'
   need(any(x['path'].endswith('/source/bp_uce.sv') and x['sha256']==pin for x in json.loads(data[prefix+'actual-source-ingestion.json'])),'actually parsed source '+label);cases.append(label)
 need(sha(data['source/candidate-bp_uce.sv'])==d['scratch_BP_source_sha256']=='c565fce280c3559066a1ebfaf1e0385b2320df67f89a3d12ed52c7852544c688','frozen candidate')
 for key,b in data.items():
  if key.endswith('/software_owned_v2.py'):need(sha(b)=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5','qualified ownership helper')
 o=d['original_UCE'];z=(root/o['file']).read_bytes();need(sha(z)==o['gzip_sha256'] and sha(gzip.decompress(z))==o['plain_sha256']=='5ff8627b7373bfc9ce9be5cbd315d222d6b0efdec2e887b3d976038be84af725','original source')
 need(len(d['external_traces'])==24 and sum(x['bytes']for x in d['external_traces'])==1962606,'all24 raw traces bound, includes partial negative traces')
 if external:
  for x in d['external_traces']+d['external_models']:
   b=Path(x['path']).read_bytes();need(len(b)==x['bytes'] and sha(b)==x['sha256'],'external bytes '+x['path'])
 return dict(state='PASS scoped replay:4production-width cases and2separate matching128 cases; original6caseFAIL',cases=cases,snapshots=len(data),raw_traces=24,external_rehashed=external,stage_peak_bytes=63475712,trace_peak_bytes=1962606,scratch_BP=d['scratch_BP_commit'],limits='Unit RTL/source contract only; no mapped area, fullcore, physical fit or performance result. Mixed64-to128 baseline liveness remains unresolved.')
def main():
 a=argparse.ArgumentParser();a.add_argument('--root',type=Path,default=HERE);a.add_argument('--external',action='store_true');p=a.parse_args();print(json.dumps(verify(p.root,p.external),indent=2))
if __name__=='__main__':main()
