#!/usr/bin/env python3
"""Capture enumerated HOME-only immutable component/proposal evidence, never run it."""
import gzip
import hashlib
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
BASE=Path('/home/coyang/fpga-artifacts/context-resume')
G=BASE/'csr-snapshot-dual-writer-20261122'
P=BASE/'csr-snapshot-production-contract-20261122'
M=BASE/'csr-snapshot-production-mapping-20261122'
D=BASE/'csr-snapshot-components-durable-20261122/closed01'
GEN=['README.md','ROOT-component-reservation01.json','admission.json','admission_v2.json','driver.cpp','extraction.json','negative-admission.json','negative-receipt.json','negative_continuation.py','no-pch.mk','original-bp_be_top.sv.gz','preexecution-sentinel-failure01.json','production-write-exclusion.json','receipt.json','reference.sv','run_host.py','run_host_v2.py','software_owned_v2.py','wrapper.sv']
PROD=['README.md','ROOT-component-reservation01.json','admission.json','driver.cpp','generic-head-preservation.json','no-pch.mk','receipt.json','reference.sv','run_host.py','software_owned_v2.py','wrapper.sv']
MAP=['README.md','admission.DRAFT.json','admission.json','candidate.sv','clock.xdc','probe.tcl','reference.sv','software_owned_v2.py','worker.py','wrapper.sv']
CAP=512*1024


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def bind(p):return dict(path=str(p),**digest(Path(p).read_bytes()))


def main():
    require(not (HERE/'manifest.json').exists(),'fresh immutable packet')
    pending=[];copies=[];originals=[];extracted=[]
    for root,label,names in [(G/'preparation01','generic/preparation01',GEN),(P/'preparation01','production/preparation01',PROD),
                             (M/'preparation01','mapping/raw-unexecuted01',MAP),(M/'preparation02','mapping/consumer-unlaunchable02',MAP+['consumer-proof.json','raw-draft-preservation.json'])]:
        for name in names:
            source=root/name;raw=source.read_bytes();rel=label+'/'+name
            pending.append((rel,raw));copies.append(dict(local=rel,original=bind(source),**digest(raw)));originals.append(bind(source))
    for source,rel in [(G/'checkpoint01/summary.json','generic/checkpoint01/summary.json'),(P/'checkpoint01/summary.json','production/checkpoint01/summary.json'),
                       (G/'checkpoint01/source-and-component-receipts.tar.gz','generic/checkpoint01/source-and-component-receipts.tar.gz'),
                       (P/'checkpoint01/source-helper-proof.tar.gz','production/checkpoint01/source-helper-proof.tar.gz'),
                       (D.parent/'closure-api-import-failure01.json','durability/closure-api-import-failure01.json')]:
        raw=source.read_bytes();pending.append((rel,raw));copies.append(dict(local=rel,original=bind(source),**digest(raw)));originals.append(bind(source))
    for source,member,rel in [(G/'checkpoint01/source-and-component-receipts.tar.gz','candidate/bp_be_csr_snapshot_store.sv','tested-SV/bp_be_csr_snapshot_store.sv'),
                              (P/'checkpoint01/source-helper-proof.tar.gz','candidate/bp_be_csr_snapshot_store_production.sv','tested-SV/bp_be_csr_snapshot_store_production.sv')]:
        with tarfile.open(source,'r:gz')as archive:
            info=archive.getmember(member);require(info.isfile(),'regular tested source');raw=archive.extractfile(info).read()
        pending.append((rel,raw));extracted.append(dict(local=rel,archive=bind(source),member=member,**digest(raw)))
    manifest_path=D/'manifest.json';raw=manifest_path.read_bytes();durability=json.loads(raw)
    require(digest(raw)['sha256']=='b6cc86532ca4d6966b8b836b985ebf0d48e17661e1cabdefc9ebf95f3fc967ba','ROOT full202 durability manifest')
    packed=gzip.compress(raw,mtime=0);require(gzip.decompress(packed)==raw,'full manifest roundtrip')
    pending.append(('durability/full202-manifest.json.gz',packed));copies.append(dict(local='durability/full202-manifest.json.gz',original=bind(manifest_path),**digest(packed),decompressed=digest(raw)));originals.append(bind(manifest_path))
    external=durability['archive']['archive'];require(bind(external['path'])==external,'external full archive hash, NO archive/model/FST copy')
    # Preserve only four tiny runtime text witnesses from the durable archive.
    logs=[r for r in durability['archive']['members']if r['original']['path'].endswith('/runtime.log')]
    require(len(logs)==4,'four closed component runtime witnesses')
    with tarfile.open(external['path'],'r:gz')as archive:
        for i,row in enumerate(logs):
            raw=archive.extractfile(row['member']).read();require(digest(raw)=={k:row['original'][k]for k in ('bytes','sha256')},'runtime witness bytes')
            rel='component-logs/runtime-'+str(i)+'.log';pending.append((rel,raw));extracted.append(dict(local=rel,archive=external,member=row['member'],original=row['original'],**digest(raw)))
    used=sum(p.stat().st_size for p in HERE.rglob('*')if p.is_file())
    require(used+sum(len(raw)for _,raw in pending)+65536<=CAP,'512KiB whole packet including manifest/proof reserve')
    for rel,raw in pending:
        path=HERE/rel;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb')as stream:stream.write(raw)
        require(path.read_bytes()==raw,'copy roundtrip')
    for row in originals:require(bind(row['path'])==row,'original changed during copy')
    record=dict(schema='csr-component-and-deferred-mapping-curation-v1',scope='Standalone functional components passed; both mapping proposals unlaunchable; NO area/timing/integration/fullcore/route/FPGA/application claim',
                cap_bytes=CAP,copies=copies,extracted_members=extracted,external_full_archive=external,external_durability_manifest=bind(manifest_path),
                unchanged_originals=originals,exclusions='No rawFST, model, object, full source tree or full202 archive copied; no original helper executed; no RAM paths opened',
                source_refs=dict(generic='connoryang:experiment/csr-snapshot-dual-writer-checkpoint-20261122 @c4a0fc2c8dca303bad930bea83d36c5a53d7bad4',production='connoryang:experiment/csr-snapshot-production-checkpoint-20261122 @eab4881d46e6fd1b079dcb2d88b8bc83e3cb0e45',remote_status='ROOT reports pushed; no network operation in this curation'))
    with (HERE/'manifest.json').open('x')as stream:json.dump(record,stream,indent=2);stream.write('\n')
    require(sum(p.stat().st_size for p in HERE.rglob('*')if p.is_file())<=CAP,'total packet cap')
    print(json.dumps(dict(manifest=bind(HERE/'manifest.json'),packet_bytes=sum(p.stat().st_size for p in HERE.rglob('*')if p.is_file())),sort_keys=True))


if __name__=='__main__':main()
