#!/usr/bin/env python3
"""Read-only closure of completed units; no compiler/model/vendor/board invocation."""
import gzip,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
R=Path('/home/coyang/fpga-artifacts/context-resume/retained-uce-scratch-20261122')
EXPECTED={'attempt01':'a255512f2105c4eed2546480615914f073c7204d851481ef923a92162f928f68','baseline-attempt01':'5b88cc7ef84d7986908806b8b4e9a177c593cec66c5dbc46925234a18f46dea3','matched-attempt01':'753cebda957c71a4bbe077a7e42fc9348f122fba58029f9a1e8311bed3bac434','legacy128-attempt01':'64c3ba2851c9652c05cc4a961638f3ccb0deaa8db29b80fc5b9c58dc7bb972ce'}
def sha(b):return hashlib.sha256(b).hexdigest()
def bind(p):b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=sha(b))
def main():
 out=HERE/'snapshots';out.mkdir(exist_ok=False);records=[];traces=[];models=[]
 def save(p,logical):
  b=p.read_bytes();name='%03d-%s.gz'%(len(records),p.name);z=gzip.compress(b,mtime=0);(out/name).write_bytes(z);records.append(dict(file='snapshots/'+name,logical=logical,plain_bytes=len(b),plain_sha256=sha(b),gzip_sha256=sha(z),original=str(p)))
 for family,pin in EXPECTED.items():
  root=R/family;p=root/'manifest.json';assert bind(p)['sha256']==pin;d=json.loads(p.read_text());assert d['source_before']==d['source_after']
  for row in d['artifacts']:assert bind(Path(row['path']))==row
  for p in sorted(root.rglob('*')):
   if not p.is_file():continue
   if p.suffix=='.fst':traces.append(bind(p));continue
   save(p,family+'/'+str(p.relative_to(root)))
  stage=Path(d['stage'])
  for p in sorted(stage.glob('*/obj/Vuce_retained')):models.append(bind(p))
 for family in ('preparation01','baseline-preparation01','matched-preparation01','legacy128-preparation01','failure-localization01','mixed-localization01'):
  root=R/family
  for p in sorted(root.rglob('*')):
   if p.is_file() and p.suffix!='.fst':save(p,family+'/'+str(p.relative_to(root)))
 bp=Path('/home/coyang/bp-retained-scratch-coalesced-20261122');uce=bp/'bp_me/src/v/cce/bp_uce.sv';assert bind(uce)['sha256']=='c565fce280c3559066a1ebfaf1e0385b2320df67f89a3d12ed52c7852544c688';save(uce,'source/candidate-bp_uce.sv')
 original=subprocess.check_output(['git','-C',str(bp),'show','8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c:bp_me/src/v/cce/bp_uce.sv']);q=HERE/'original-bp_uce.sv.gz';q.write_bytes(gzip.compress(original,mtime=0))
 d=dict(state='CLOSED scoped production all64 pairedPASS plus separate matching128 pairedPASS; original fixed-sixcaseFAIL preserved',snapshots=records,external_traces=traces,external_models=models,original_UCE=dict(file=q.name,plain_bytes=len(original),plain_sha256=sha(original),gzip_sha256=sha(q.read_bytes())),family_manifest_pins=EXPECTED,scratch_BP_commit='7566c67aad9b93f5546fcc5e258e405402a47850',scratch_BP_source_sha256=bind(uce)['sha256'],BP_base='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c',scratch_branch_pushed='connoryang/experiment/retained-uce-scratch-coalescing-20261122',packed_composition='ABANDONED before creation per ROOT; b12 unchanged',fullcore_or_area_qualification=False,curator_tool_runs='Only metadata/source/hash/read-only trace decoding; no new compiler/model/vendor/board')
 (HERE/'closure.json').write_text(json.dumps(d,indent=2)+'\n');print('snapshots',len(records),'traces',len(traces),'models',len(models),'compressed_bytes',sum(p.stat().st_size for p in HERE.rglob('*')if p.is_file()))
if __name__=='__main__':main()
