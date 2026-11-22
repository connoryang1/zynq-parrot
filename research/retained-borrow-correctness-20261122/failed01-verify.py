#!/usr/bin/env python3
"""Independent complete-byte archive review, no model or FST reader execution."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tarfile
import time

ARCHIVE=Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow-trace0-fullcore-20261122/closed01/archive.json')
SHA='4c7d0c341c1aa4d98bb2001733d14d5111685193dc0a78d68b0d8ce49634d7f8'
BASE='/run/user/1001/zp-retained-borrow-trace0-fullcore-20261122-02/'
COMPOSITE='13eeb4ac85245e5b6f2f3f52c86a880638fff8127cc60bfd03b21718aed69fcf'
MODEL='61d1d3cb15edc62901782a174f783cad2de1c2a83af3751b9b58524ab82049cd'

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

UNIT=Path('/home/coyang/fpga-artifacts/context-resume/retained-hit-payload-borrow-20261122/attempt01/manifest.json')
UNIT_SHA='8340f4dba6841135ffdfee69691154d5fa74cdbdd4b785fbd896e866f47eaec4'
TOP='3daedee66a3c94014b4a666fea037b17cc9b0943'
BP='bb575a764c200f07c6f3259a179bdc861dd7593f'
UCE='94d989246a8d2d247da8835081f2ba9385ab568e10425d0b872f376df3ea4ad4'
BACKEND='c04764548493f2a1109c36f25881c32444d0171b434e777c9e2b5fc2f631bcf2'

def verify_unit(guard):
    require(bind(UNIT)['sha256']==UNIT_SHA,'fixed closed six-unit anchor')
    q=json.loads(UNIT.read_text());require(q['state'].startswith('PASS six matched baseline/borrow'),'actual six-case completion')
    admission=Path(q['admission']['path']);require(bind(admission)==q['admission'],'unit admission binding')
    a=json.loads(admission.read_text())
    cases=['baseline-D64-all64','candidate-D64-all64','baseline-I64-all64','candidate-I64-all64','baseline-I128-BedRock128','candidate-I128-BedRock128']
    require(a['sequence']==cases and len(q['commands'])==30,'fixed six cases/five phases each')
    require(q['source_before']==q['source_after']==a['bindings'],'all frozen unit inputs identical before/after')
    require(a['candidate_sha256']==UCE and a['backend_candidate_sha256']==BACKEND,'exact borrowing pair')
    for row in a['bindings']:
        guard();require(bind(row['path'])==row,'unit frozen source input')
    for row in q['artifacts']:
        guard();require(bind(row['path'])==row,'all complete unit logs/source-ingestion/FST artifacts')
    results=[]
    for i,case in enumerate(cases):
        commands=q['commands'][i*5:(i+1)*5]
        codes=[c['owned_receipt']['returncode'] for c in commands]
        require(codes==[0,0,0,-6,0],'generate/build/normal/assert-negative/drain exact exits')
        require(commands[3]['expected_failure']=='UCE prefetch response has no live slot','qualified negative assertion')
        for c in commands:
            life=c['owned_receipt'];require(c['failure'] is None and life['failure'] is None and not life['owned_group_remaining'],'all unit groups clean')
        d=UNIT.parent/case;text=(d/'unit.log').read_text()
        for marker in ('[UCE-SCRATCH-TURNOVER] PASS:','[UCE-BORROW-LIFETIME] PASS:','full64B lines=64'):
            require(text.count(marker)==1,'normal complete stress marker '+marker)
        require('UCE prefetch response has no live slot' in (d/'short-response.log').read_text(),'negative transcript')
        require('[UCE-SHORT-DRAIN] PASS:' in (d/'short-response-drain.log').read_text(),'short-response drained without full publication')
        ingested=json.loads((d/'actual-source-ingestion.json').read_text())
        by_name={Path(r['path']).name:r for r in ingested}
        expected_uce=UCE if case.startswith('candidate') else '5ff8627b7373bfc9ce9be5cbd315d222d6b0efdec2e887b3d976038be84af725'
        expected_store=BACKEND if case.startswith('candidate') else '68d1dd0c7df7e56ffe76317f9bae5a3ca3e09d13cb44d1167c0f737acefcbea6'
        require(by_name['bp_uce.sv']['sha256']==expected_uce and by_name['bp_retained_line_store.sv']['sha256']==expected_store,'actual ingested unit RTL')
        results.append(dict(case=case,returncodes=codes,ingested_sources=len(ingested),actual_UCE_sha256=expected_uce,actual_store_sha256=expected_store,log=bind(d/'unit.log')))
    require(q['aggregate_stage_peak_allocated_bytes']<=q['stage_cap_bytes'] and q['aggregate_trace_peak_bytes']<=q['trace_cap_bytes'],'original unit bounds')
    return dict(manifest=bind(UNIT),admission=bind(admission),cases=results,artifacts_verified=len(q['artifacts']),frozen_inputs_verified=len(a['bindings']),trace_bytes=q['aggregate_trace_peak_bytes'],no_new_execution=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    require(not a.output.exists(),'fresh report');start=time.monotonic()
    def guard():require(time.monotonic()-start<180,'fixed180s closed-byte verification deadline')
    unit=verify_unit(guard)
    require(bind(ARCHIVE)['sha256']==SHA,'fixed ROOT lossless archive anchor')
    q=json.loads(ARCHIVE.read_text())
    require(q['state'].startswith('PASS complete lossless borrowing1792 trace0'),'archive completed')
    require(q['durable_bytes']==43149547 and q['durable_allocation_bytes']==96*1024**2,'exact durable bytes/original96MiB cap')
    metadata={};verified=[]
    for archive in q['archives']:
        guard();row=archive['archive'];require(bind(row['path'])==row,'stored complete archive bytes')
        if 'members' in archive:
            count=0
            with tarfile.open(row['path'],'r|gz') as tar:
                for member in tar:
                    require(count<len(archive['members']),'no extra archive member');expected=archive['members'][count]
                    require(member.name==expected['member'] and member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts,'safe exact member sequence')
                    stream=tar.extractfile(member)
                    if row['path'].endswith('metadata.tar.gz') and member.size<2*1024**2:
                        raw=stream.read();actual=(len(raw),hashlib.sha256(raw).hexdigest());metadata[expected['original']['path']]=raw
                    else:actual=digest(stream,guard)
                    require(actual==(expected['original']['bytes'],expected['original']['sha256']),'complete archive member identity');count+=1
            require(count==len(archive['members']),'all members through EOF');verified.append(dict(archive=row,members=count))
        else:
            with gzip.open(row['path'],'rb') as stream:actual=digest(stream,guard)
            require(actual==(archive['original']['bytes'],archive['original']['sha256']),'complete model/FST/ELF/NBF roundtrip')
            verified.append(dict(archive=row,original=archive['original']))
    require([r.get('members') for r in verified[:2]]==[759,58] and len(verified)==9,'all source/generated/metadata and seven singles')
    def doc(relative):return json.loads(metadata[BASE+relative])
    native=doc('full01/session.json')
    require(hashlib.sha256(metadata[BASE+'full01/session.json']).hexdigest()==COMPOSITE,'exact accepted fullcore proof')
    require(native['state'].startswith('PASS borrow-only trace0 clean fullcore') and native['model']['sha256']==MODEL,'accepted model/source qualification')
    require(native['source_tree_baseline']==TOP and native['source_bp']==BP,'exact source candidate')
    expected=[('make-preflight',0),('clean',0),('build',0),('loader',0),('integrity-run',-6),('integrity-checker',0),('advisory-run',-6),('advisory-checker',0),('strict',0),('counter',0),('parameters',0)]
    require([(c['label'],c['returncode']) for c in native['commands']]==expected,'all eleven exact fullcore phases')
    require(all(c['ownership']['failure'] is None and not c['ownership']['owned_group_remaining'] for c in native['commands']),'fullcore owned groups clean')
    compiled=doc('full01/actual-source-list.json')['sources'];archived={r['path']:r for r in q['groups']['sources']}
    for row in compiled.values():require(all(row[k]==archived[row['path']][k] for k in ('path','bytes','sha256')),'every actual compiled input archived')
    require(next(r for r in compiled.values() if r['path'].endswith('/bp_uce.sv'))['sha256']==UCE,'unit/fullcore UCE bytes joined')
    require(next(r for r in compiled.values() if r['path'].endswith('/bp_retained_line_store.sv'))['sha256']==BACKEND,'unit/fullcore backend bytes joined')
    strict=doc('full01/strict01/verification.json');counter=doc('full01/counter01/verification.json');params=doc('full01/parameters01/verification.json')['facts']['values']
    require(strict['accepted'] and len(strict['cold_function_retirement'])==16,'complete cold-code retirement proof')
    for lane in ('i','d'):
        facts=strict['lanes'][lane];require(len(facts['publications'])==len(facts['hits'])==len(facts['bursts'])==1 and len(facts['bursts'][0]['beats'])==8,'full512b/eight actual writes per lane')
    require(counter['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'independent GP0 firsttouch counts')
    expected_params={'num_threads_p':2,'num_contexts_p':4,'icache_sets_p':64,'icache_assoc_p':8,'icache_block_width_p':512,'dcache_sets_p':64,'dcache_assoc_p':8,'dcache_block_width_p':512,'l2_banks_p':2,'l2_sets_p':64,'l2_assoc_p':2,'l2_block_width_p':512,'retained_store.storage.i_lines_p':1792,'retained_store.storage.d_lines_p':1792,'retained_store.storage.sets_p':256,'retained_store.storage.epoch_width_p':8,'core_minimal.cache_miss_trace_p':0}
    require(params==expected_params,'exact seventeen geometry/profile facts')
    for role in ('integrity','advisory'):
        require(doc('full01/'+role+'/verification.json')['state'].startswith('PASS'),'complete native verification')
        require(doc('full01/'+role+'/process.json')['returncode']==-6,'actual postPASS finalizer return retained')
        text=metadata[BASE+'full01/'+role+'/run.log'].decode();require('[BSG-PASS]' in text and 'BSG-INFO:    CORE PASS' in text and 'BSG-INFO:    BSG PASS' in text,'whole native terminal before known finalizer')
    setup=Path('/home/coyang/zynq-parrot-linux-host-observer/research/borrow-fpga-source-preparation-20261122/actual02')
    receipt=bind(setup/'session.json');require(receipt['sha256']=='2a9b752d696e7b85d1ccbcc51f37b685a8c4e3212206c15c2b3e0763653f077a','actual private FPGA source readiness')
    source=json.loads((setup/'session.json').read_text());bridge=json.loads(Path(source['consumed_source_bridge']['path']).read_text())
    require(bind(source['consumed_source_bridge']['path'])==source['consumed_source_bridge'] and len(bridge)==len(compiled)==396,'complete relocation bridge')
    for r in bridge:require(all(r[k]==compiled[r['native']][k] for k in ('bytes','sha256')),'relocated source bytes equal native proof')
    report=dict(state='PASS independent closed borrowing unit/fullcore/archive byte review',reviewer=bind(__file__),unit=unit,archive=bind(ARCHIVE),verified_archives=verified,source_TOP=TOP,source_BP=BP,source_gitlinks=native['source_repositories'],model=native['model'],actual_compiled_sources=len(compiled),fullcore_phases=expected,actual_parameters=params,firsttouch_counts=counter['firsttouch_counts'],cold_instructions_retired=16,FPGA_source_setup=receipt,normalized_source_bridge=source['consumed_source_bridge'],elapsed_seconds=time.monotonic()-start,limits='No target/model/reader execution or semantic FST reanalysis. Accepted source-bound unit and firsttouch proofs inherited with complete byte integrity. No all1792-slot borrowing proof, fit/route/physical/application or performance claim.')
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(a.output)

if __name__=='__main__':main()

