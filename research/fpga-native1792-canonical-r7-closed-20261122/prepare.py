#!/usr/bin/env python3
"""One read-only curation of closed R7; does not query tools or modify external evidence."""
import gzip,hashlib,json,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
UP=Path('/home/coyang/fpga-artifacts/context-resume/native1792-canonical-r7-preparation-20261121/closed-terminal01')
OLD=Path('/home/coyang/fpga-artifacts/context-resume/native1792-dense-r5b-monitor-20261121/closed-terminal01')
TOP='eb7d390134a0025331a2366a979a774263b146d5';BP='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c'
def sha(b):return hashlib.sha256(b).hexdigest()
def binding(p):b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=sha(b))
def main():
 raw=(UP/'manifest.json').read_bytes();assert sha(raw)=='e6d59ed8fc1a3a634b5b55038bddc65aa3749d7bd437cc7dad58dd691e02b4b6';d=json.loads(raw);assert len(d['copies'])==20
 dest=HERE/'r7';dest.mkdir(exist_ok=False);shutil.copyfile(UP/'manifest.json',dest/'upstream-manifest.json');inputs=[]
 for row in d['copies']:
  p=Path(row['snapshot']['path']);b=p.read_bytes();plain=gzip.decompress(b)
  assert len(b)==row['snapshot']['bytes'] and sha(b)==row['snapshot']['sha256']
  assert len(plain)==row['original']['bytes'] and sha(plain)==row['original']['sha256']
  if p.name.endswith('.sv.gz'):assert b'pragma protect' not in plain
  shutil.copyfile(p,dest/p.name);inputs.append(dict(file='r7/'+p.name,compressed_sha256=sha(b),plain_bytes=len(plain),plain_sha256=sha(plain)))
 dcps=[]
 for row in d['checkpoints']:
  p=Path(row['snapshot']['path']);assert binding(p)==row['snapshot'];dcps.append(dict(kind=row['kind'],**binding(p),copied_into_git=False))
 # Exact own/open source objects; no third-party encrypted payloads or DCPs copied.
 src=HERE/'source';src.mkdir();objects=[]
 specs=[('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122',TOP,'cosim/black-parrot-example/v/bp_common_pkg.sv'),('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122',TOP,'cosim/black-parrot-example/v/top_zynq.sv'),('/home/coyang/bp-retained-canonical-epochs-20261121',BP,'bp_common/src/include/bp_common_aviary_cfg_pkgdef.svh')]
 for repo,rev,p in specs:
  b=subprocess.check_output(['git','-C',repo,'show',rev+':'+p]);q=src/Path(p).name;q.write_bytes(b);objects.append(dict(file='source/'+q.name,repository_commit=rev,repository_path=p,bytes=len(b),sha256=sha(b)))
 # Only closed same-stage reports from r5b, not its query or any pending R7 query.
 before=HERE/'r5b';before.mkdir();old=[]
 for n in ('012-runme.log.gz','018-black_parrot_bd_1_wrapper_utilization_synth.rpt.gz'):
  p=OLD/n;plain=gzip.decompress(p.read_bytes());shutil.copyfile(p,before/n);old.append(dict(file='r5b/'+n,compressed_sha256=sha(p.read_bytes()),plain_bytes=len(plain),plain_sha256=sha(plain),original=str(p)))
 evidence=dict(state='CLOSED detailedplacement FAIL; no route/bit/accepted FPGA capacity',upstream_manifest_sha256=sha(raw),upstream_manifest_file='r7/upstream-manifest.json',upstream_manifest_original=str(UP/'manifest.json'),inputs=inputs,external_checkpoints_verified=dcps,source_objects=objects,r5b_inputs=old,top=TOP,bp=BP,unchanged_payload_lines_each=1792,payload_total_bytes=229376,limits='No DCP/raw model/third-party encrypted source copied; no vendor query/tool/board. Original external closure unchanged. Pending read-optimized-hierarchy01 excluded.')
 (HERE/'bindings.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(dict(bindings_sha256=sha((HERE/'bindings.json').read_bytes()),gz_roundtrips=20,external_DCPs_verified=2)))
if __name__=='__main__':main()
