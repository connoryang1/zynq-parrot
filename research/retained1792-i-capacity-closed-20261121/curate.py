#!/usr/bin/env python3
"""Lossless small-source/semantic proof archive; raw FST/model/ELF/NBF stay external."""
from pathlib import Path
import gzip,hashlib,io,json,tarfile
HERE=Path(__file__).resolve().parent
BASE=Path('/home/coyang/fpga-artifacts/context-resume/retained1792-stream-canonical-20261121')

def binding(path):
 b=Path(path).read_bytes();return dict(path=str(path),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def main():
 archive=HERE/'closed-inputs.tar.gz';index=HERE/'archive-index.json'
 if archive.exists() or index.exists():raise RuntimeError('never overwrite closed curation')
 paths={}
 def add(p,role):
  p=Path(p).resolve()
  if p.name.endswith(('.fst','.riscv','.nbf','.elf')) or p.name=='Vbsg_nonsynth_zynq_testbench':raise ValueError('bulk artifact excluded')
  paths.setdefault(str(p),[]).append(role)
 good=BASE/'accepted-i-enabled-audit01';native=BASE/'i-enabled-native01'
 for p,role in ((good,'accepted'),(native,'native')):
  add(p/'root-closure.json',role)
  for row in json.loads((p/'root-closure.json').read_text())['records']:
   if not row['path'].endswith(('.fst','.riscv','.nbf')):add(row['path'],role)
 accepted=json.loads((good/'i-enabled-audit/acceptance.json').read_text())
 for row in accepted['sources']:add(row['path'],'frozen-producer-source')
 bridge=json.loads((good/'audit-continuation.json').read_text())
 for row in bridge['sources']:add(row['path'],'continuation-source')
 stopped=BASE/'stopped-audit01';add(stopped/'root-stop.json','prior-failure');add(stopped/'preparation.json','original-admission');add(stopped/'runtime-sources.json','runtime-snapshot')
 prep=json.loads((stopped/'preparation.json').read_text())
 for key in ('model_approval','canonical_fullcore','observation_qualification','compiled_sources','model_stamp','host_admission'):add(prep[key]['path'],'model-source-chain')
 program_path=prep['program']['path'];add(program_path,'fixed-fixture-manifest');program=json.loads(Path(program_path).read_text())
 for row in program['sources']:add(row['path'],'fixture-source')
 report=json.loads((HERE/'review.json').read_text())
 for row in report['critical_sources']:add(row['path'],'compiled-critical-source')
 for relative in ('accepted-d-enabled-audit02/d-enabled-audit-attempt2/acceptance.json','accepted-d-off-audit01/d-off-audit/acceptance.json'):add(BASE/relative,'fixed-prior-acceptance')
 members=[]
 with archive.open('xb') as target,gzip.GzipFile(fileobj=target,mode='wb',mtime=0,filename='') as packed,tarfile.open(fileobj=packed,mode='w|') as tar:
  for n,(origin,roles) in enumerate(sorted(paths.items())):
   p=Path(origin);raw=p.read_bytes();name='inputs/%03d-%s'%(n,p.name)
   info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(raw))
   members.append(dict(member=name,path=origin,roles=sorted(set(roles)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
 with tarfile.open(archive,'r:gz') as tar:
  assert tar.getnames()==[row['member'] for row in members]
  for row in members:
   raw=tar.extractfile(row['member']).read();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
 doc=dict(state='PASS exact lossless roundtrip all explicit members',archive=dict(path=archive.name,bytes=archive.stat().st_size,sha256=binding(archive)['sha256']),members=members,excluded='Raw FST/model/ELF/NBF external exact bindings in native/root/semantic closures; no reader/model/tool launched')
 index.write_text(json.dumps(doc,indent=2)+'\n');print(json.dumps(dict(members=len(members),archive_bytes=archive.stat().st_size,index=binding(index)),sort_keys=True))
if __name__=='__main__':main()
