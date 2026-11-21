#!/usr/bin/env python3
"""Independently inspect the fixed closed D-only packet; no FST reader/model."""
import gzip
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=Path('/home/coyang/fpga-artifacts/context-resume/retained1792-stream-canonical-20261121')
GOOD=BASE/'accepted-d-enabled-audit02'
STOP=BASE/'stopped-audit01'


def require(ok,message):
    if not ok:raise ValueError(message)


def bind(path):
    path=Path(path).resolve();data=path.read_bytes()
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def qualified_contract(bridge,local):
    origin='/home/coyang/zynq-parrot-linux-host-observer/research/retained1792-audit-continuation-20261121/continuation.py'
    expected='96e91eac0aed1085078f4a23c5360cc87ee0d31b241cca792d2e7d04b033cb00'
    rows=[row for row in bridge['sources'] if row['path']==origin]
    require(len(rows)==1 and rows[0]['sha256']==expected,'fixed producer contract source anchor')
    require(bind(origin)==rows[0],'original pinned producer contract')
    actual=bind(local)
    require(all(actual[key]==rows[0][key] for key in ('bytes','sha256')),'local contract must be byte-identical to producer')
    return Path(local)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args()
    require(not args.out.exists(),'new independent review output required')
    closure=GOOD/'root-closure.json'
    require(bind(closure)['sha256']=='e9e1cc9237cac997918255a38503bf3d4378432542966a4617469640f3ea7248','externally anchored ROOT closure')
    closed=json.loads(closure.read_text());stopped=json.loads((STOP/'root-stop.json').read_text())
    require(bind(STOP/'root-stop.json')['sha256']=='cf8cdaa0b987406a1ffaf94a3386fc33b5c562e8dc75add5d7d5af6431b87bcb','externally anchored stopped attempt')
    mapping={}
    for row in stopped['records']+closed['records']:
        require(bind(row['path'])=={k:row[k] for k in ('path','bytes','sha256')},'durable-copy hash')
        require(row['original'] not in mapping,'one copy per original input')
        mapping[row['original']]=row
    def resolve(row):
        if row['path'] in mapping:
            copied=mapping[row['path']]
            require(all(row[k]==copied[k] for k in ('bytes','sha256')),'chain original/copy identity')
            return Path(copied['path'])
        require(bind(row['path'])==row,'external source/manifest binding')
        return Path(row['path'])
    audit=GOOD/'d-enabled-audit-attempt2'
    accepted=json.loads((audit/'acceptance.json').read_text())
    require(bind(audit/'acceptance.json')['sha256']==closed['acceptance_sha256']=='82b333fb26766421d127cdd2bee6c657368444a82d247de8440d9edfed5e01bc','exact acceptance')
    require(accepted['attempt']==2 and accepted['inherited_native'] is True and accepted['role']=='d-enabled','explicit attempt2 inheritance')
    for row in accepted['files']+accepted['sources']:resolve(row)
    bridge=json.loads(resolve(accepted['preparation']).read_text())
    for row in bridge['sources']:resolve(row)
    require(accepted['native_sha256']==closed['native_sha256']=='5716c0e35d385ef38ff38ffb2a760a9b7f2f0f27b1cd5c3d1820350a3a929bae','exact inherited native')
    require(closed['audit_exit']==0 and stopped['root_audit']['exit_code']==1,'attempt1 failed, attempt2 actual0')
    full=json.loads((audit/'verification.json').read_text())
    for key,row in full['bindings'].items():
        if key!='model':resolve(row)
    require(full['bindings']['model']['sha256']=='b9f7f127121d750591513372a5d2e342046098a58984384e0f5b57b35b00b3e7','same qualified model')
    program=json.loads(resolve(full['bindings']['program']).read_text())
    # Import pinned original Validator only to calculate its static target
    # oracle; do not process events or run any executable.
    contract=qualified_contract(bridge,HERE.parent/'retained1792-audit-continuation-20261121/continuation.py')
    spec=importlib.util.spec_from_file_location('closed_d_continuation',contract)
    c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
    expected=json.loads(json.dumps(c.original.Validator(program,'d-enabled').targets))
    require(full['targets']==expected,'all1792 deterministic address/slot/full512b oracle')
    targets=set(expected)
    require(full['lane']=='d' and full['lines']==1792 and full['sets']==256,'exact D geometry')
    require(all(set(full[k])==targets for k in ('publications','hits','retained_bursts')),'every1792 distinct target published/hit/restored')
    require(full['ordinary_bursts']=={} and full['retired_instruction_pcs']=={} and full['d_protected_load_retirements']==14336,'D-only full protected-load retirement and no ordinary refill')
    begin,verify,end=(full['markers'][k] for k in ('populate_begin','verify_begin','verified'))
    require(begin<verify<end,'ordered correctness markers')
    for addr,target in expected.items():
        pub=full['publications'][addr];hit=full['hits'][addr];burst=full['retained_bursts'][addr];address=int(addr)
        require(begin<=pub['accepted']<=pub['time']<verify<=hit['lookup']<=hit['time']<=burst['time']<end,'per-address publication before checked retained use')
        require(burst['retained'] is True and burst['address']==address and burst['request']==address+24 and 0<=burst['way']<8,'retained complete critical-word3 burst')
        words=burst['words']
        require(len(words)==8 and [w['address'] for w in words]==[address+8*i for i in range(8)],'eight actual full-line write addresses')
        require([w['data'] for w in words]==target['words'] and {w['bank'] for w in words}==set(range(8)),'all512 payload bits and every real bank')
        require(all(words[i]['time']<words[i+1]['time'] for i in range(7)) and words[-1]['time']<end,'complete ordered SRAM writes before verified')
    stream=full['archive']['full_stream']
    require(stream==dict(sha256='85dd21a0f2eb41012a05b5e16f52de7003cb8eea45d4f23532e9ba3fc11768c8',bytes=320514029,lines=14479994,events=14479825,counter_events=17923,exact_end_records=1,reader_returncode=0),'complete unchanged full167 stream digest/count receipt')
    handles={};last={};count=0;ended=False
    with gzip.open(resolve(full['archive']['counter_projection']),'rt') as f:
        for line in f:
            parts=line.rstrip('\n').split('\t')
            if parts[0]=='#SIGNAL':require(parts[1] in ('obs.hits','obs.published','obs.beats') and parts[2]=='32','explicit three-counter projection');handles[parts[1]]=int(parts[3])
            elif parts[0]=='#END':require(not ended and line=='#END\n','one exact projection EOF');ended=True
            elif not parts[0].startswith('#'):
                require(not ended and int(parts[1]) in handles.values() and len(parts[2])==32 and set(parts[2])<=set('01'),'only complete counter events')
                last[int(parts[1])]=int(parts[2],2);count+=1
    values=[]
    for name in ('obs.hits','obs.published','obs.beats'):
        word=last[handles[name]];values.extend((word&65535,word>>16))
    require(ended and count==17923 and values==[0,1792,0,1792,0,14336],'independently recomputed final FST counters')
    supplemental=json.loads((audit/'counter-words.json').read_text())
    require(supplemental['values']==values,'same unchanged counter checker result')
    for name in ('reader.owned.json','counter-checker.owned.json'):
        life=json.loads((audit/name).read_text());require(life['returncode']==0 and life['failure'] is None and life['owned_group_remaining'] is False,'closed actual0/owned group')
    report=dict(state='PASS independent closed D-only simulation capacity review',root_closure=bind(closure),failed_attempt=bind(STOP/'root-stop.json'),acceptance=bind(audit/'acceptance.json'),raw_fst=full['bindings']['fst'],full_stream=stream,
        distinct_targets=1792,full_payload_bytes=1792*64,publications=1792,hits=1792,retained_full_bursts=1792,ordinary_bursts=0,actual_sram_words=14336,protected_load_retirements=14336,counter_words=values,
        markers=full['markers'],diagnostic_intervals=dict(population_and_check=['populate_begin','verified'],retained_check_only=['verify_begin','verified']),
        limits='Synthetic D-only full-slot proof; no I/off complete cohort, physical capacity/fit or application/performance claim. No FST replay; ROOT complete-validator receipt plus independently reviewed serialized all-address words/counters. Model raw executable remains ROOT-only; exact qualified model hash inherited, not rehashed here.')
    out=args.out
    with out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(dict(state=report['state'],report=bind(out)),sort_keys=True))


if __name__=='__main__':main()
