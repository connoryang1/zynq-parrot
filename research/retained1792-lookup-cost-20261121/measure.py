#!/usr/bin/env python3
"""Read accepted all-slot JSON only; no FST/model/board execution."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

def bind(path):
    path=Path(path).resolve();data=path.read_bytes()
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path);args=parser.parse_args()
    if args.out.exists():raise ValueError('fresh output required')
    base=Path('/home/coyang/fpga-artifacts/context-resume/retained1792-stream-canonical-20261121/accepted-d-enabled-audit02')
    closure=base/'root-closure.json'
    assert bind(closure)['sha256']=='e9e1cc9237cac997918255a38503bf3d4378432542966a4617469640f3ea7248'
    proof=base/'d-enabled-audit-attempt2/verification.json';record=next(x for x in json.loads(closure.read_text())['records'] if x['path']==str(proof))
    assert bind(proof)=={k:record[k] for k in ('path','bytes','sha256')}
    period=50000
    clock=Path('/home/coyang/fpga-artifacts/context-resume/retained-canonical-hp0-native-20261121/independent-review.json')
    assert bind(clock)['sha256']=='d098e29cf6fd0b561a4720642490378199441220eaae3585d51e2b01506ac3b7'
    assert json.loads(clock.read_text())['clock_FST_ticks']==period
    proof_data=json.loads(proof.read_text());targets=proof_data['targets'];hits=proof_data['hits'];bursts=proof_data['retained_bursts']
    assert len(targets)==1792 and set(targets)==set(hits)==set(bursts)
    assert {x['slot'] for x in targets.values()}==set(range(1792))
    rows=[]
    for address,target in targets.items():
        hit=hits[address];burst=bursts[address];first=min(x['time'] for x in burst['words']);last=max(x['time'] for x in burst['words'])
        assert hit['lookup']<hit['time']<=first<=last and len(burst['words'])==8
        rows.append(dict(slot=target['slot'],tag_row=target['slot']//256,lookup_to_response=(hit['time']-hit['lookup'])/period,response_to_first_write=(first-hit['time'])/period,response_to_full_write=(last-hit['time'])/period,lookup_to_full_write=(last-hit['lookup'])/period))
    def summarize(subset):
        return dict(count=len(subset),**{key:dict(min=min(values),median=statistics.median(values),max=max(values)) for key in ('lookup_to_response','response_to_first_write','response_to_full_write','lookup_to_full_write') for values in [[row[key] for row in subset]]})
    result=dict(state='PASS descriptive all1792 D-line service costs; simulation only',inputs=[bind(closure),bind(proof),bind(clock)],core_period_FST_ticks=period,all_slots=summarize(rows),by_tag_row=[dict(tag_row=i,**summarize([row for row in rows if row['tag_row']==i])) for i in range(7)],limits='Accepted backend lookup to accepted full512-bit response includes protocol waits; actual winning L1 SRAM writes are separate. Tag row follows proven retained slot/256. These are synthetic correctness diagnostics, not CPU load-ready timing, trigger-complete execution, physical timing or application benefit.')
    args.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['all_slots']))

if __name__=='__main__':main()
