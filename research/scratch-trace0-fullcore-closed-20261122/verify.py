#!/usr/bin/env python3
"""Independent complete-byte archive review, no model or FST reader execution."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tarfile
import time

ARCHIVE=Path('/home/coyang/fpga-artifacts/context-resume/retained-scratch-trace0-fullcore-20261122/closed01/archive.json')
SHA='0fcbdb18912bc043ac814c8484e55bee30c5b330809143031656237490d8bba8'
BASE='/run/user/1001/zp-retained-scratch-trace0-fullcore-20261122-02/'
COMPOSITE='8e5ce91dacd7315e377aa5e1cb761fe8534ba80f0551802a1a545e6f091adedf'
MODEL='3f3e8b766f19746cb434e99200c0bde49853e4c0cc27aeec7a0dbacec7f6b2df'

def require(ok,message):
    if not ok:raise ValueError(message)

def digest(stream,guard):
    h=hashlib.sha256();size=0
    for block in iter(lambda:stream.read(1048576),b''):guard();h.update(block);size+=len(block)
    return size,h.hexdigest()

def bind(path):
    path=Path(path)
    with path.open('rb') as stream:n,h=digest(stream,lambda:None)
    return dict(path=str(path.resolve()),bytes=n,sha256=h)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    require(not a.output.exists(),'fresh report')
    start=time.monotonic()
    def guard():require(time.monotonic()-start<180,'fixed180s closed-file verification deadline')
    require(bind(ARCHIVE)['sha256']==SHA,'actual ROOT durable archive anchor')
    q=json.loads(ARCHIVE.read_text());require(q['state'].startswith('PASS lossless durable scratch-only1792 trace0'),'actual archival completion')
    require(q['durable_bytes']<=128*1024**2 and q['model']['sha256']==MODEL,'archive allocation and actual model')
    metadata={};verified=[]
    for archive in q['archives']:
        guard();row=archive['archive'];require(bind(row['path'])==row,'stored archive bytes')
        if 'members' in archive:
            count=0
            with tarfile.open(row['path'],'r|gz') as tar:
                for member in tar:
                    require(count<len(archive['members']),'no extra member');expected=archive['members'][count]
                    require(member.name==expected['member'] and member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts,'safe exact member sequence')
                    stream=tar.extractfile(member)
                    if row['path'].endswith('metadata.tar.gz') and member.size<2*1024**2 and expected['original']['path'].endswith('.json'):
                        raw=stream.read();actual=(len(raw),hashlib.sha256(raw).hexdigest());metadata[expected['original']['path']]=raw
                    else:actual=digest(stream,guard)
                    require(actual==(expected['original']['bytes'],expected['original']['sha256']),'complete member roundtrip identity');count+=1
            require(count==len(archive['members']),'all archive members')
            verified.append(dict(archive=row,members=count))
        else:
            with gzip.open(row['path'],'rb') as stream:actual=digest(stream,guard)
            require(actual==(archive['original']['bytes'],archive['original']['sha256']),'complete model/FST/ELF/NBF roundtrip identity')
            verified.append(dict(archive=row,original=archive['original']))
    require([r.get('members') for r in verified[:2]]==[584,48],'complete source/generated and metadata archives')
    def doc(relative):return json.loads(metadata[BASE+relative])
    original=doc('full01/session.json');native=doc('first-native01/session.json')
    require(original['state']=='FAIL preserved, no accepted result' and original['error']=="KeyError('model')",'original persisted-model failure remains FAIL')
    require([x['label'] for x in original['commands']]==['make-preflight','clean','build'],'build-only original, no prior native')
    require(hashlib.sha256(metadata[BASE+'first-native01/session.json']).hexdigest()==COMPOSITE,'exact accepted first-native composite')
    require(native['state'].startswith('PASS scratch-only1792 trace0 composite first-native') and native['model']==original['model'] and native['model']['sha256']==MODEL,'same built model and separate acceptance')
    require(native['source_tree_baseline']=='4dadebbfdddfe958eff432b7f87280cfb9b5d991' and native['source_bp']=='7566c67aad9b93f5546fcc5e258e405402a47850','exact source candidate')
    compiled=doc('full01/actual-source-list.json')['sources'];archived={r['path']:r for r in q['groups']['sources']}
    for row in compiled.values():require(all(row[k]==archived[row['path']][k] for k in ('path','bytes','sha256')),'all actual consumed bytes archived')
    strict=doc('first-native01/strict01/verification.json');counter=doc('first-native01/counter01/verification.json');parameters=doc('first-native01/parameters01/verification.json')['facts']['values']
    require(strict['accepted'] and len(strict['cold_function_retirement'])==16,'strict complete cold-code retirement')
    for lane in ('i','d'):
        facts=strict['lanes'][lane];require(len(facts['publications'])==len(facts['hits'])==len(facts['bursts'])==1 and len(facts['bursts'][0]['beats'])==8,'publication/hit/eight real normal-L1 SRAM write proof')
    require(counter['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'independent actual event clocks and GP0 counts')
    expected={'num_threads_p':2,'num_contexts_p':4,'icache_sets_p':64,'icache_assoc_p':8,'icache_block_width_p':512,'dcache_sets_p':64,'dcache_assoc_p':8,'dcache_block_width_p':512,
        'l2_banks_p':2,'l2_sets_p':64,'l2_assoc_p':2,'l2_block_width_p':512,'retained_store.storage.i_lines_p':1792,'retained_store.storage.d_lines_p':1792,
        'retained_store.storage.sets_p':256,'retained_store.storage.epoch_width_p':8,'core_minimal.cache_miss_trace_p':0}
    require(parameters==expected,'all16 geometry plus actual trace0')
    for role in ('integrity','advisory'):require(doc('first-native01/'+role+'/verification.json')['state'].startswith('PASS'),'complete checked native execution')
    report=dict(state='PASS independent full-byte scratch-only1792 trace0 composite archive review',archive=bind(ARCHIVE),reviewer=bind(__file__),verified_archives=verified,
        model=native['model'],source_TOP=native['source_tree_baseline'],source_BP=native['source_bp'],actual_compiled_source_count=len(compiled),actual_parameters=parameters,
        firsttouch_counts=counter['firsttouch_counts'],cold_instructions_retired=16,original_failure_state_preserved=True,
        limits='Synthetic fullcore source qualification/first-touch restoration only. Selected capacity/whole-device area/route/physical/all1792-slot/new application outcomes not established; no performance or archive speedup claim.',elapsed_seconds=time.monotonic()-start)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(a.output)

if __name__=='__main__':main()
