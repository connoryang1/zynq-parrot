#!/usr/bin/env python3
"""Independent lossless archive/closed-proof review; no FST event reader."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tarfile
import time

ARCHIVE=Path('/home/coyang/fpga-artifacts/context-resume/retained256-qualification-20261122/closed02/archive.json')
SHA='e9b134b8cd2a723ee0a766423242939a4b1bf73d0b06241583ab773e4fd1e7f3'
BASE='/run/user/1001/zp-retained256-fullcore-20261122-02/full01/'
MODEL='2c9d615694c0f59d9f85e6e247ba12494854378bd3b61334cf0cdaedc671e876'


def require(ok,message):
    if not ok:raise ValueError(message)


def hashed(stream,guard):
    h=hashlib.sha256();size=0
    for block in iter(lambda:stream.read(1048576),b''):guard();h.update(block);size+=len(block)
    return size,h.hexdigest()


def binding(path):
    path=Path(path)
    with path.open('rb') as stream:size,sha=hashed(stream,lambda:None)
    return dict(path=str(path.resolve()),bytes=size,sha256=sha)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    require(not a.output.exists(),'fresh independent report')
    start=time.monotonic()
    def guard():require(time.monotonic()-start<180,'fixed180s closed-file verification deadline')
    require(binding(ARCHIVE)['sha256']==SHA,'externally pinned actual ROOT archive')
    q=json.loads(ARCHIVE.read_text())
    require(q['state'].startswith('PASS lossless durable matched256 composite archive') and q['durable_bytes']<128*1024**2,'actual archive closure/storage')
    require(q['model']['sha256']==MODEL,'same executed model')
    verified=[];metadata={};source_bytes={}
    for archive in q['archives']:
        guard();row=archive['archive'];require(binding(row['path'])==row,'archive stored-byte binding')
        if 'members' in archive:
            rows=archive['members'];count=0
            with tarfile.open(row['path'],'r|gz') as tar:
                for member in tar:
                    guard();require(count<len(rows),'unexpected tar member');expected=rows[count]
                    require(member.name==expected['member'] and member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts,'safe exact member list')
                    stream=tar.extractfile(member)
                    if member.size<=2*1024**2 and (expected['original']['path'].endswith('.json') or expected['original']['path'].endswith('Makefile.design')):
                        raw=stream.read();require((len(raw),hashlib.sha256(raw).hexdigest())==(expected['original']['bytes'],expected['original']['sha256']),'member bytes')
                        if row['path'].endswith('metadata.tar.gz'):metadata[expected['original']['path']]=raw
                        else:source_bytes[expected['original']['path']]=raw
                    else:require(hashed(stream,guard)==(expected['original']['bytes'],expected['original']['sha256']),'complete archive member bytes')
                    count+=1
            require(count==len(rows),'all archive members')
            verified.append(dict(archive=row,members=count))
        else:
            with gzip.open(row['path'],'rb') as stream:actual=hashed(stream,guard)
            require(actual==(archive['original']['bytes'],archive['original']['sha256']),'full model/FST/program decompression identity')
            verified.append(dict(archive=row,original=archive['original']))
    require([x.get('members') for x in verified[:2]]==[610,52],'full sources/generated closure and metadata')
    def document(suffix):return json.loads(metadata[BASE+suffix])
    native=document('session.json');composite=document('postprocess02/session.json')
    require(native['state']=='FAIL preserved, no accepted result' and 'strict fullpayload' in native['error'],'original tool-root FAIL preserved')
    first=json.loads(metadata['/run/user/1001/zp-retained256-fullcore-20261122-01/full01/session.json'])
    require(first['state']=='FAIL preserved, no accepted result' and 'owned descendants' in first['error'],'first guard FAIL preserved')
    require(composite['state'].startswith('PASS matched256 composite') and composite['inherited_native_attempt']['sha256']==hashlib.sha256(metadata[BASE+'session.json']).hexdigest(),'separate successful composite binds failed producer')
    require(native['source_tree_baseline']=='596e4677fdcbbf59706be254384f778861f0cc36' and native['source_bp']=='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c','matched256 source pins')
    require(native['geometry']==dict(i_lines=256,d_lines=256,sets=256,line_bytes=64,observe=1,delay=0,resident=2,logical=4,l2_bytes=16384,aclk_mhz=20),'matched ordinary geometry/config')
    compiled=document('actual-source-list.json')['sources'];require(len(compiled)==396,'all396 compiled inputs')
    archived={r['path']:r for r in q['groups']['sources']}
    for row in compiled.values():require(all(archived[row['path']][k]==row[k] for k in ('path','bytes','sha256')),'compiled source in exact archive')
    strict=document('advisory-strict02/verification.json');counter=document('advisory-counter02/verification.json');params=document('actual-parameters02/verification.json')
    require(strict['accepted'] and len(strict['cold_function_retirement'])==16,'all16 cold instructions retired')
    for lane in ('i','d'):
        facts=strict['lanes'][lane]
        require(len(facts['publications'])==len(facts['hits'])==len(facts['bursts'])==1 and len(facts['bursts'][0]['beats'])==8,'real publication/hit/eight-write strict proof')
    require(counter['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'independent counter clock/GP0 corroboration')
    values=params['facts']['values'];require(len(values)==16 and values['retained_store.storage.i_lines_p']==values['retained_store.storage.d_lines_p']==256 and values['l2_banks_p']==2,'all16 actual parameter proof')
    for name in ('integrity','advisory'):
        require(document(name+'/verification.json')['state'].startswith('PASS'),'actual complete native/checker proof')
    script=source_bytes['/home/coyang/zp-retained256-source-20261122/testing/rtl/retained-advisory-trace/validate.py'] if '/home/coyang/zp-retained256-source-20261122/testing/rtl/retained-advisory-trace/validate.py' in source_bytes else None
    # Tool bytes are verified via every-member streaming hashes above; their
    # actual tracked root and literal source checks remain unchanged.
    validator=archived['/home/coyang/zp-retained256-source-20261122/testing/rtl/retained-advisory-trace/validate.py']
    require(validator['sha256']=='53eaca9a63bb31efa5571b6eb12279e1779339d4d3821f50488e7846f19d5d21','exact byte-identical validator under actual source root')
    report=dict(state='PASS independent full-byte durable matched256 composite review',archive=binding(ARCHIVE),reviewer=binding(__file__),verified_archives=verified,
        geometry=native['geometry'],model=q['model'],compiled_source_count=396,source_members=610,metadata_members=52,
        cold_instructions_retired=16,firsttouch_counts=counter['firsttouch_counts'],actual_parameters=values,
        failure_history=['ROOT17565 guard failure; actual zombie cause unconfirmed','ROOT90386 validator tool-root failure before reader; original remains FAIL','ROOT49687 archival guard-overhead stop; partial archive preserved'],
        limits='Synthetic matched256 integrity/first-touch I+D full64B restoration only. All256-slot, observation-clone, FPGA fit/use and complete application cost not established. No archival speedup ratio.',elapsed_seconds=time.monotonic()-start)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(a.output)


if __name__=='__main__':main()
