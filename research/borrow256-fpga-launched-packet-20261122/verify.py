#!/usr/bin/env python3
"""Offline packet verification only: never imports helpers or opens referenced RAM."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
JOB='20261122T084853Z-1008854d3'
TOP='1008854d30e5d923c86c3232fc22af039467d552';BP='bb575a764c200f07c6f3259a179bdc861dd7593f'


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def verify(root):
    manifest=json.loads((root/'manifest.json').read_text());stored={}
    require(manifest['schema']=='borrow256-running-CAD-curation-v1' and manifest['job']==JOB,'exact snapshot scope/job')
    for row in manifest['copy_files']:
        raw=(root/row['local']).read_bytes();require(digest(raw)=={k:row[k]for k in ('bytes','sha256')},'local exact source/snapshot '+row['local'])
        require(digest(raw)=={k:row['original'][k]for k in ('bytes','sha256')},'original/copy bytes')
        if 'decompressed'in row:require(digest(gzip.decompress(raw))==row['decompressed'],'full snapshot gzip roundtrip')
        stored[row['original']['path']]=raw
    archive=manifest['proof_archive'];raw=(root/archive['local']).read_bytes()
    require(digest(raw)=={k:archive[k]for k in ('bytes','sha256')},'immutable archive bytes')
    expected={r['member']:r for r in archive['members']};found=set();payloads={}
    import lzma
    unpacked=lzma.decompress(raw);require(digest(unpacked)==archive['uncompressed_tar'],'lossless complete tar roundtrip')
    with tarfile.open(fileobj=io.BytesIO(unpacked),mode='r:')as tar:
        for info in tar:
            require(info.isfile() and info.name in expected and info.name not in found,'exact declared archive members, no extraction')
            row=expected[info.name];data=tar.extractfile(info).read();require(digest(data)=={k:row[k]for k in ('bytes','sha256')},'full member bytes '+info.name)
            require(digest(data)=={k:row['original'][k]for k in ('bytes','sha256')},'original/member bytes')
            found.add(info.name);payloads[info.name]=data;stored[row['original']['path']]=data
    require(found==set(expected),'no omitted immutable proof')
    def read(name):return json.loads(payloads['proofs/'+name])
    source=read('actual01/session.json');old=read('unexecuted-adapter01-preserved.json');admission=read('adapter02/admission01.json')
    anchors={'actual01/session.json':'6e8c18085ac85767a7d5442c63edec76153ef9e1866855233527e502b52e88fb',
             'adapter02/ROOT-preflight01.json':'258ce62d72211fa50b865b527a86a2be41d95f044e42a2b1284c53cb294b8245',
             'adapter02/ROOT-launch01.json':'3baafd6268e355a324f621de50908723ccd5ead6546603d1bee05a0d703cf192',
             'adapter02/admission01.json':'8ad1456667045e9214f7928026d9b182cad5eb8262c1f282d4f70a168bcf75f2',
             'adapter02/ROOT-release01.json':'e5f29d22733b8c5ff0f0132c2ecb2df8ff9c20cb6a06e5fe911b8534bef9aaf2'}
    for name,sha in anchors.items():require(digest(payloads['proofs/'+name])['sha256']==sha,'actual ROOT anchor '+name)
    require(source['state']=='PASS private-clone exact FPGA source/readiness/static Make dryrun; no CAD launch' and source['elapsed_seconds']==30.425947754993103 and len(source['repositories'])==9,'actual source/readiness only')
    require(source['TOP']==TOP and source['BP']==BP and all(r['native_common_config_unchanged']for r in source['repositories']),'exact private sources and preserved native configs')
    require(old['prepare_packet_executed'] is False and old['admission_generated'] is False and old['launcher_or_vendor_executed'] is False,'adapter01 never launched')
    for row in old['files']:require(digest(stored[row['path']])=={k:row[k]for k in ('bytes','sha256')},'unexecuted helper bytes retained')
    require(admission['top']==TOP and admission['bp']==BP,'admitted source')
    expected_defines=dict(BP_RETAINED_BUFFER=1,BP_RETAINED_I_LINES=256,BP_RETAINED_D_LINES=256,BP_RETAINED_SETS=256,BP_RETAINED_OBSERVE=1,BP_AXI_RESPONSE_DELAY=0,BP_CACHE_MISS_TRACE=0)
    require(admission['configuration']['expected_defines']==expected_defines,'all seven exact hardware parameters')
    for row in admission['bindings']:
        if row['path']in stored:require(digest(stored[row['path']])=={k:row[k]for k in ('bytes','sha256')},'actual admission/source proof binding')
    require(read('adapter02/ROOT-preflight01.json')['returncode']==0 and read('adapter02/ROOT-launch01.json')['returncode']==0,'actual ROOT preflight/launcher exit0')
    require(read('adapter02/ROOT-launch01.json')['admission_sha256']==anchors['adapter02/admission01.json'],'launch actual admission')
    require(read('adapter02/ROOT-release01.json')['state']=='ROOT ADMITTED local clean CAD' and read('adapter02/ROOT-release01.json')['holds_released'] is True,'actual ROOT release')
    identity=read('adapter02/run-'+JOB+'/monitor-identity.json');require(identity['job']==JOB and identity['admission']['sha256']==anchors['adapter02/admission01.json'],'monitor actual admission')
    for name in ('poll-001.json.gz','poll-005.json.gz'):
        p=json.loads(gzip.decompress((root/'running-snapshots'/name).read_bytes()))
        require(p['job']==JOB and p['status']=='RUNNING' and p['worker']['pid']==1194135 and p['worker']['startticks']==95314382,'RUNNING-only exact worker snapshot')
        require(p['identity_violations']==[],'snapshot identity checks')
        if name=='poll-005.json.gz':require(p['feature_state']=='PASS actual seven defines/three contexts/20MHz-8MHz/source','actual feature-only pass')
    total=sum(p.stat().st_size for p in root.rglob('*')if p.is_file());require(total<=1024**2,'whole new Git packet1MiB cap')
    return dict(state='PASS immutable launch/readiness packet; RUNNING snapshots only, no fitted/route/bit/board result',job=JOB,anchors=anchors,archive_members=len(found),exact_copy_files=len(manifest['copy_files']),packet_bytes=total,cap_bytes=1024**2,
                limitations='Referenced full trees/DCPs/RAM files/live status/ledger not read. This verifies local bytes and immutable launch/feature chain, not terminal acceptance.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    result=verify(HERE)
    if args.output:
        require(not args.output.exists(),'fresh verification receipt only')
        with args.output.open('x')as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,sort_keys=True))
