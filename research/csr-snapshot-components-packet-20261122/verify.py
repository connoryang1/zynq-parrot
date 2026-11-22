#!/usr/bin/env python3
"""Offline artifact verification only; never imports or executes copied helpers."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def verify(root):
    m=json.loads((root/'manifest.json').read_text());require(m['schema']=='csr-component-and-deferred-mapping-curation-v1','packet schema')
    source={}
    for row in m['copies']:
        raw=(root/row['local']).read_bytes();require(digest(raw)=={k:row[k]for k in ('bytes','sha256')},'exact copied artifact '+row['local'])
        original=gzip.decompress(raw)if'decompressed'in row else raw
        require(digest(original)=={k:row['original'][k]for k in ('bytes','sha256')},'lossless original bytes')
        if'decompressed'in row:require(digest(original)==row['decompressed'],'complete gzip roundtrip')
        source[row['original']['path']]=original
    for family,name in [('generic','source-and-component-receipts.tar.gz'),('production','source-helper-proof.tar.gz')]:
        archive=root/family/'checkpoint01'/name
        with tarfile.open(archive,'r:gz')as tar:
            for info in tar:
                require(info.isfile(),'small checkpoint archives contain source/receipts only')
                raw=tar.extractfile(info).read()
                target=root/family/info.name if info.name.startswith('preparation01/')else root/'tested-SV'/Path(info.name).name
                require(target.read_bytes()==raw,'exact full checkpoint archive member roundtrip '+info.name)
    durable=json.loads(gzip.decompress((root/'durability/full202-manifest.json.gz').read_bytes()))
    require(digest(gzip.decompress((root/'durability/full202-manifest.json.gz').read_bytes()))['sha256']=='b6cc86532ca4d6966b8b836b985ebf0d48e17661e1cabdefc9ebf95f3fc967ba','ROOT full202 manifest anchor')
    require(durable['files']==len(durable['inputs'])==len(durable['archive']['members'])==202 and durable['archive']['roundtrip'] is True,'complete external durability manifest')
    require(durable['archive']['archive']==m['external_full_archive'] and m['external_full_archive']['sha256']=='5b75bf2c95aabc0cd1c58d8aa0ec61d7313c936a3abe8ff4b4b30e2ae5f3a834','large archive external only')
    known={r['member']:r['original']for r in durable['archive']['members']}
    for row in m['extracted_members']:
        require(digest((root/row['local']).read_bytes())=={k:row[k]for k in ('bytes','sha256')},'exact tested source/runtime witness')
        if'original'in row:require(known[row['member']]==row['original'],'runtime witness belongs to full202 archive')
    g=json.loads((root/'generic/checkpoint01/summary.json').read_text());p=json.loads((root/'production/checkpoint01/summary.json').read_text())
    require(g['BP_commit']=='c4a0fc2c8dca303bad930bea83d36c5a53d7bad4' and g['positive']['cycles']==7234 and g['positive']['all_context_checks']==57868,'generic actual positive gate')
    require(g['positive']['owned_statuses']==g['negative']['owned_statuses']==[0,0,0],'separate generic negative succeeds by rejecting mutation')
    require(json.loads((root/'generic/preparation01/receipt.json').read_text())['state'].startswith('FAIL'),'original generic helper FAIL never promoted')
    require(json.loads((root/'generic/preparation01/negative-receipt.json').read_text())['state'].startswith('PASS composite inherited positive plus negative witness'),'separate negative composite proof')
    require(p['source_checkpoint_commit']=='eab4881d46e6fd1b079dcb2d88b8bc83e3cb0e45' and (p['positive_cycles'],p['positive_all_context_checks'],p['raw_combinations'])==(22054,176428,8192),'production actual component gate')
    require(len(p['owned_commands'])==6 and all(r==dict(returncode=0,remaining=False)for r in p['owned_commands']),'production positive/negative all owned statuses')
    require(digest((root/'tested-SV/bp_be_csr_snapshot_store.sv').read_bytes())['sha256']==g['candidate_sha256']=='1066c40eb474545079c31aa70d25b9a7899f89d6e407088eece95a1bf686fb2d','generic exact tested candidate')
    require(digest((root/'tested-SV/bp_be_csr_snapshot_store_production.sv').read_bytes())['sha256']==p['candidate_sha256']=='0ed6f85da9ca9ee47de25d99bc79d9f43710742014fa4c6f607f06d1f66a4067','production exact tested candidate')
    logs='\n'.join(path.read_text()for path in (root/'component-logs').glob('*.log'))
    for text in ('CSR_SNAPSHOT_FULL_IMAGE_PASS cycles=7234 all_context_checks=57868 width=1666 contexts=4 single_width=65','CSR_SNAPSHOT_NEGATIVE_REJECTED cycles=2',
                 'CSR_PRODUCTION_FULL_IMAGE_PASS cycles=22054 checks=176428 raw_combinations=8192 width=1666 contexts=4','CSR_PRODUCTION_NEGATIVE_REJECTED cycles=2'):
        require(logs.count(text)==1,'actual closed log witness '+text)
    exclusion=root/'generic/preparation01/production-write-exclusion.json'
    require(digest(exclusion.read_bytes())['sha256']=='22982102c56242df4afb7f54633d187d68f962c1cd09ffc1a5e0cf98cc135d42','ROOT source exclusion proof')
    for family in ('raw-unexecuted01','consumer-unlaunchable02'):
        a=json.loads((root/'mapping'/family/'admission.json').read_text())
        require(a['launchable'] is False and a['ROOT_terminal_release'] is None,'mapping remains UNLAUNCHABLE')
        require((root/'mapping'/family/'admission.json').read_bytes()==(root/'mapping'/family/'admission.DRAFT.json').read_bytes(),'draft bytes preserved')
        require((root/'mapping'/family/'candidate.sv').read_bytes()==(root/'tested-SV/bp_be_csr_snapshot_store_production.sv').read_bytes(),'mapping uses exact tested memory only')
    consumer=json.loads((root/'mapping/consumer-unlaunchable02/consumer-proof.json').read_text())
    require(consumer['producer_exclusion_proof']['sha256']==digest(exclusion.read_bytes())['sha256'] and consumer['RAM_sources_unchanged'] is True,'consumer draft source linkage')
    total=sum(path.stat().st_size for path in root.rglob('*')if path.is_file());require(total<=512*1024,'entire new packet512KiB cap')
    return dict(state='PASS local curation/roundtrips; component positive/negative only; BOTH mapping drafts UNLAUNCHABLE',generic=dict(cycles=7234,checks=57868,negative='rejected'),
                production=dict(cycles=22054,checks=176428,raw_combinations=8192,negative='rejected'),external_durability_members=202,packet_bytes=total,cap_bytes=512*1024,
                limits='No model/reader/helper/probe execution, RAM access, mapping result, area/timing, integration, fullcore, fitted FPGA or application claim.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    result=verify(HERE)
    if args.output:
        require(not args.output.exists(),'fresh local verification receipt')
        with args.output.open('x')as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,sort_keys=True))
