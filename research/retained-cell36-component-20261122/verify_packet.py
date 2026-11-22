#!/usr/bin/env python3
"""Portable compact component proof inspection; never executes tools/models."""
import argparse,hashlib,importlib.util,json,re,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parent

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 raw=Path(p).read_bytes();return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--external-archive',type=Path);args=ap.parse_args()
 m=json.loads((R/'manifest.json').read_text())
 for rel,rec in m['files'].items():require(bind(R/rel)==rec,'packet changed '+rel)
 require(sum(p.stat().st_size for p in R.rglob('*') if p.is_file())<=m['cap_bytes'],'compact cap')
 p=json.loads((R/'provenance.json').read_text());lookup={}
 for rec in p['records']:
  s=rec['snapshot'];q=R/s['path'];require(bind(q)=={k:s[k] for k in ('bytes','sha256')},'exact snapshot '+s['path']);lookup[rec['original']['path']]=q
 summary=json.loads((R/'summary.json').read_text());require(summary['derived_component_correctness'] is True and summary['original_operational_budget_compliance'] is False,'do not promote original operational FAIL')
 require(bind(R/'candidate-b12caa67.sv')['sha256']=='2f7b8985c180f2f32673a5e6dbe531599f88776ccdf65db085d07da3e5dd9b39','exact tested source')
 root=R/'evidence';ro=root/'readonly-closure01';a=json.loads((ro/'admission.json').read_text());c=json.loads((ro/'completion.json').read_text())
 require(c['derived_component_correctness'] is True and c['original_operational_budget_compliance'] is False,'separate derived closure')
 require(c['commands'][0]['owned_receipt']['returncode']==0 and c['commands'][0]['owned_receipt']['owned_group_remaining'] is False,'read-only reader complete')
 require((ro/'last-hierarchy.tsv').read_text().endswith('#END\n'),'missing final metadata EOF')
 original=json.loads((root/'attempt02/host-supervision02.json').read_text());require(original['state'].startswith('FAIL preserved') and len(original['commands'])==35 and len(original['runs'])==11,'original failure intact')
 runtime=[x for x in original['commands'] if '/obj/Vretained_cell36_wrapper' in x['argv'][0]]
 require(len(runtime)==12 and all(x['returncode']==0 and x['owned_group_remaining'] is False for x in runtime),'all12 native command returns')
 require(original['commands'][-1]['failure']=="ValueError('128MiB stage /64MiB aggregate family trace cap')",'exact postrun budget failure')
 copied=json.loads((ro/'compact-inputs/manifest.json').read_text());by_original={x['original']['path']:lookup[x['snapshot']['path']] for x in copied['files']}
 require(len(summary['rows'])==12 and sum(x['FST']['bytes'] for x in summary['rows'])==68366449,'complete twelve traces')
 for row in a['inputs']['rows']:
  text=by_original[row['log']['path']].read_text()
  for marker in ['RETAINED_METADATA_MITER_PASS ','RETAINED_METADATA_HAZARDS_PASS ','RETAINED_PACKED_COLLECTOR_HAZARDS_PASS ','RETAINED_TEST_EXIT_CLEAN']:require(text.count(marker)==1,'full runtime markers')
  params=next(x for x in summary['rows'] if x['case']==row['case'] and x['clock']==row['mode'])
  for lane,n in [(0,params['I_lines']),(1,params['D_lines'])]:require(text.count('RETAINED_CAPACITY_CHECK lane='+str(lane)+' lines='+str(n)+' full64B=1')==1,'actual complete capacity')
 sys.path.insert(0,str(root/'attempt02/helper'));spec=importlib.util.spec_from_file_location('archived_component',root/'attempt02/helper/run_host.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
 require(f.unchanged_controller((root/'attempt02/helper/baseline-8df.sv.txt').read_bytes(),(R/'candidate-b12caa67.sv').read_bytes()),'unchanged controller byte proof')
 if args.external_archive:
  durable=json.loads((R/'durable-external-manifest.json').read_text());require(bind(args.external_archive)=={k:durable['archive'][k] for k in ('bytes','sha256')},'external archive')
  expected={x['member']:x['original'] for x in durable['members']};count=0
  with tarfile.open(args.external_archive,'r:gz') as tf:
   for member in tf:
    require(member.isfile() and member.name in expected,'archive member identity');raw=tf.extractfile(member).read();want=expected[member.name];require(len(raw)==want['bytes'] and hashlib.sha256(raw).hexdigest()==want['sha256'],'lossless member '+member.name);count+=1
  require(count==len(expected)==293,'all durable293 members')
 print('PASS portable component records/12full-runtime markers/byte-controller proof; original budgetFAIL preserved; no reader/model')
if __name__=='__main__':main()
