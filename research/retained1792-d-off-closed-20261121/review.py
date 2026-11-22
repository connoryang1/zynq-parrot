#!/usr/bin/env python3
"""Review the fixed closed D-off packet and paired synthetic marker endpoints."""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
previous=HERE.parent/'retained1792-d-capacity-closed-20261121/review.py'
spec=importlib.util.spec_from_file_location('d_on_closed_review',previous)
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
require,bind=old.require,old.bind
require(bind(previous)['sha256']=='a0500a37cb4fadfa0905c003c99f04340878a92fe7806af4e9bf6e0784e42360','pinned portable prior review bytes')
BASE=old.BASE;GOOD=BASE/'accepted-d-off-audit01';NATIVE=BASE/'d-off-native01'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    require(not args.out.exists(),'new independent review output')
    closures=[(GOOD/'root-closure.json','cdb44adad482a632b5b4fb5ef33d27adbcd39b739504bb4d49fa1eac7fd84f9d'),
        (NATIVE/'root-closure.json','feb4f768c4744c08887b0df81227e6ab30b9c4819f73d089a9dc8c68f922b698'),
        (old.GOOD/'root-closure.json','e9e1cc9237cac997918255a38503bf3d4378432542966a4617469640f3ea7248'),
        (old.STOP/'root-stop.json','cf8cdaa0b987406a1ffaf94a3386fc33b5c562e8dc75add5d7d5af6431b87bcb')]
    mapping={}
    for path,sha in closures:
        require(bind(path)['sha256']==sha,'externally anchored closed packet')
        for row in json.loads(path.read_text())['records']:
            require(bind(row['path'])=={k:row[k] for k in ('path','bytes','sha256')},'exact closed durable bytes')
            if row['original'] in mapping:require(all(row[k]==mapping[row['original']][k] for k in ('bytes','sha256')),'duplicate copy same original bytes')
            mapping[row['original']]=row
    def resolve(row):
        if row['path'] in mapping:
            actual=mapping[row['path']];require(all(row[k]==actual[k] for k in ('bytes','sha256')),'exact original/durable link');return Path(actual['path'])
        require(bind(row['path'])==row,'external source/program drift');return Path(row['path'])
    audit=GOOD/'d-off-audit';accepted=json.loads((audit/'acceptance.json').read_text())
    require(bind(audit/'acceptance.json')['sha256']=='b3836100e588c699b4ecc7be92983637aadd4b90c332480e11b7bd53a7ef6309','actual accepted audit')
    require(accepted['role']=='d-off' and accepted['attempt']==1 and accepted['inherited_native'] is False,'new D-off audit identity')
    for row in accepted['files']+accepted['sources']:resolve(row)
    bridge=json.loads(resolve(accepted['preparation']).read_text())
    for row in bridge['sources']:resolve(row)
    full=json.loads((audit/'verification.json').read_text());on=json.loads((old.GOOD/'d-enabled-audit-attempt2/verification.json').read_text())
    for key,row in full['bindings'].items():
        if key!='model':resolve(row)
    require(full['bindings']['model']==on['bindings']['model'],'exact same qualified model, not raw binary rehash')
    for key in ('program','reader','preparation'):require(full['bindings'][key]==on['bindings'][key],'same software/reader/continuation')
    require(full['bindings']['selection']['sha256']==on['bindings']['selection']['sha256'],'same full167 selection bytes')
    require(accepted['native_sha256']==full['bindings']['run']['sha256']=='bc4d2677fd71464b1a0f852df99360d971315aa0f7a0d18803f6a78349930c6a','exact new negative native anchor')
    admission=json.loads(resolve(full['bindings']['admission']).read_text())
    require(admission['preparation']==accepted['preparation'] and admission['model']==full['bindings']['model'],'native continuation/model chain')
    for row in json.loads(resolve(admission['runtime_sources']).read_text()):resolve(row)
    contract=old.qualified_contract(bridge,HERE.parent/'retained1792-audit-continuation-20261121/continuation.py')
    spec=importlib.util.spec_from_file_location('d_off_contract',contract);c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
    program=json.loads(resolve(full['bindings']['program']).read_text())
    expected=json.loads(json.dumps(c.original.Validator(program,'d-off').targets))
    require(full['targets']==expected==on['targets'],'all1792 same deterministic full64B target oracles')
    require(full['publications']==full['hits']==full['retained_bursts']=={} and set(full['ordinary_bursts'])==set(expected),'negative zero retained events; all1792 ordinary target fills')
    require(full['lane']=='d' and full['lines']==1792 and full['sets']==256 and full['d_protected_load_retirements']==14336,'actual D geometry/protected load retirements')
    begin,verify,end=(full['markers'][k] for k in ('populate_begin','verify_begin','verified'))
    require(begin<verify<end,'all ordered retired markers')
    for addr,target in expected.items():
        burst=full['ordinary_bursts'][addr];require(burst['address']==int(addr) and set(burst['words'])==set(map(str,range(8))),'all8 words of each ordinary fill')
        words=[burst['words'][str(i)] for i in range(8)]
        require([w['address'] for w in words]==[int(addr)+8*i for i in range(8)] and [w['data'] for w in words]==target['words'],'every address/all512data bits')
        require({w['bank'] for w in words}==set(range(8)) and all(verify<=w['time']<end for w in words),'every actual bank written in protected checking interval')
        require(all(words[i]['time']<words[i+1]['time'] for i in range(7)),'ordered complete actual SRAM writes')
    stream=full['archive']['full_stream']
    require(stream==dict(sha256='794cd45deea2c58e0c5990857c648287a61ce1bfa881773ecff737e1e0ac891a',bytes=279338025,lines=13039139,events=13038970,counter_events=3,exact_end_records=1,reader_returncode=0),'complete full167 stream digest/count/EOF/reader0')
    handles={};values={};count=0;ended=False
    with gzip.open(resolve(full['archive']['counter_projection']),'rt') as f:
        for line in f:
            parts=line.rstrip('\n').split('\t')
            if parts[0]=='#SIGNAL':require(parts[2]=='32' and parts[1] in ('obs.hits','obs.published','obs.beats'),'only three declared observer counters');handles[parts[1]]=int(parts[3])
            elif parts[0]=='#END':require(not ended and line=='#END\n','one exact projection EOF');ended=True
            elif not parts[0].startswith('#'):
                require(not ended and int(parts[1]) in handles.values() and parts[2]=='0'*32,'negative counter event zero');values[int(parts[1])]=0;count+=1
    require(ended and count==3 and len(handles)==len(values)==3,'exact3zero counter events plusEOF')
    counter=json.loads((audit/'counter-words.json').read_text());require(counter['values']==[0]*6,'same six actual GP0/FST zeros')
    adapter_path=resolve(counter['audit']);adapter=json.loads(adapter_path.read_text())
    require(adapter==dict(schema='counter-projection-input-only-v1',full_audit=next(row for row in accepted['files'] if row['path'].endswith('/d-off-audit/verification.json')),bindings=dict(events=full['archive']['counter_projection'],run=full['bindings']['run'])),'exact projection-adapter/full167 proof chain')
    require(counter['run']==full['bindings']['run'] and counter['events']==full['archive']['counter_projection'] and counter['state']=='PASS final FST counter words equal actual GP0 reads','actual counter-checker provenance')
    resolve(counter['auditor'])
    run=json.loads(resolve(full['bindings']['run']).read_text());require(run['counters']==[0]*6 and run['primary_use_gate_rejected'] is True,'negative primary retained-use rejection')
    for name in ('reader.owned.json','counter-checker.owned.json'):
        life=json.loads((audit/name).read_text());require(life['returncode']==0 and life['failure'] is None and life['owned_group_remaining'] is False,'actual0/no owned process remains')
    intervals={}
    for role,proof in [('d-enabled',on),('d-off',full)]:
        markers=proof['markers'];intervals[role]=dict(markers=markers,population_and_check_ps=markers['verified']-markers['populate_begin'],target_check_only_ps=markers['verified']-markers['verify_begin'])
    result=dict(state='PASS independent D-off ordinary-payload negative control review',closures=[bind(p) for p,s in closures],acceptance=bind(audit/'acceptance.json'),full_stream=stream,raw_fst=full['bindings']['fst'],distinct_ordinary_targets=1792,actual_sram_words=14336,protected_load_retirements=14336,retained_publications=0,retained_hits=0,retained_bursts=0,counter_words=[0]*6,
        paired_d_synthetic_intervals=intervals,
        limits='Both intervals reported for both closed D cases, no subset selection. Synthetic correctness timings exclude mode setup/reset/drain/report and are not application/complete-COST performance. I capacity/fullcohort/FPGA/fit pending. Full-validator receipt plus serialized all-address review; no FST/model/native replay. Qualified model hash inherited, not raw executable rehashed.')
    with args.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(state=result['state'],report=bind(args.out)),sort_keys=True))


if __name__=='__main__':main()
