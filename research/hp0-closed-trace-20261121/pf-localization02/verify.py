#!/usr/bin/env python3
"""Verify same-trace PF decomposition and lower-controller blocking evidence."""
import gzip, hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def bind(path):
    path=Path(path);data=path.read_bytes()
    return dict(path=str(path.resolve()),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def require(ok,message):
    if not ok:raise ValueError(message)


def main():
    pf=json.loads((HERE/'localization.json').read_text())
    gate_path=HERE.parent/'lower-gate03/gate.json'
    gates=json.loads(gate_path.read_text())
    report=dict(accepted=True,scope='same closed08/10 PF timing localization, not a target run or performance claim',
                script=bind(__file__),PF_extraction=bind(HERE/'localization.json'),lower_gate=bind(gate_path),cases={})
    (HERE/'source').mkdir(exist_ok=True)
    names={'bp_me_cache_controller.sv','bp_me_cache_slice.sv','bp_me_dram_hash_encode.sv',
           'bp_me_stream_pump_in.sv','bp_me_stream_pump_out.sv','bsg_cache_to_axi.sv',
           'bsg_cache_to_axi_rx.sv','bsg_cache_to_axi_ordering.sv','bp_axi_top.sv'}
    sources={}
    for case,record in pf['cases'].items():
        for key in ['base_proof','input_FST_archive','selection','events']:
            require(bind(record[key]['path'])==record[key],'PF input changed: '+key)
        base=json.loads(Path(record['base_proof']['path']).read_text())
        source_list=Path(base['bindings']['source_list']['path'])
        d=json.loads(gzip.open(source_list,'rt').read() if source_list.suffix=='.gz' else source_list.read_text())
        records=d.get('sources',d)
        for filename,expected in records.items():
            source=Path(filename)
            if source.name not in names:continue
            b=bind(source)
            require(all(b[k]==expected[k] for k in ['bytes','sha256']),'compiled source mismatch')
            target=HERE/'source'/source.name
            if target.exists():require(target.read_bytes()==source.read_bytes(),'cross-case source changed')
            else:target.write_bytes(source.read_bytes())
            sources[source.name]=dict(compiled_path=filename,snapshot=bind(target))
        g=gates['cases'][case]
        require(g['parameters']=={'num_cache':2,'tag_slots':2},'unexpected bridge capacity')
        for key in ['base_proof','input_archive','events','selection']:
            require(bind(g[key]['path'])==g[key],'lower-gate input changed')
        require(not record['overlapping_HP0']['AW'],'write transaction overlaps PF window')
        # Actual top translation is observed at AR handshakes, not inferred from RID0.
        require([r['BP_PA'] for r in record['HP0_translations']]==[0x8000b240,0x80001000,0x80012000], 'AR sequence/PA mapping changed')
        for r in record['HP0_translations']:
            require(r['base']==0 and r['HP0_address']==(r['BP_PA']^0x80000000),'remap changed')
        summary={}
        for lane,target,preceding in [('i',0x80001000,0x8000b250),('d',0x80012000,0x80001010)]:
            events=record['UCE_PF_events'][lane]
            admit=record['admit'][lane]
            issue=next(r['time'] for r in events if r.get('PF_FSM_issue_PA')==target)
            forward=next(r['time'] for r in events if r.get('accepted_memory_forward_PA')==target)
            replies=[r for r in events if (r.get('PF_reply_PA',0)&~63)==target]
            require(len(replies)==8 and [r['PF_reply_PA'] for r in replies]==list(range(target,target+64,8)),'incomplete PF reply')
            require(all(r['PF_reply_accepted'] and r['PF_reply_last']==int(n==7) for n,r in enumerate(replies)),'PF reply did not handshake')
            require([r['time']-replies[0]['time'] for r in replies]==[n*50000 for n in range(8)],'PF stream spacing changed')
            ar=next(r for r in record['overlapping_HP0']['AR'] if r['address']==target^0x80000000)
            publication=record['publication'][lane]
            rel=lambda time:(time-admit)/50000
            blocked=[r for r in g['intervals'] if r['fwd_addr']==preceding and r['fwd_v'] and not r['fwd_yumi']
                     and r['pkt_v'] and not r['pkt_yumi'] and not r['rr_v'] and r['tag_ready'] and not r['r_fence']]
            hold=max(blocked,key=lambda r:r['cycles'])
            delay=base['static_response_beat_minimum_age_cycles']
            require(hold['cycles']==11+delay,'expected busy-bank hold did not account for extra N')
            require(rel(issue)==2 and rel(forward)==3,'UCE defer changed')
            require((publication-replies[-1]['time'])/50000==34,'post-full publication path changed')
            summary[lane]=dict(admit=admit,relative_clock_periods=dict(PF_FSM_issue=rel(issue),
                accepted_UCE_forward=rel(forward),target_AR=rel(ar['request_time']),
                BP_first_R=rel(ar['first_offer']),BP_RLAST_complete=rel(ar['complete']),
                UCE_first_PF_reply=rel(replies[0]['time']),UCE_full_PF_reply=rel(replies[-1]['time']),
                PF_publication=rel(publication)),blocking_controller_interval=hold,
                first_reply_to_full_cycles=7,full_reply_to_publication_cycles=34)
        report['cases'][case]=dict(lanes=summary,AR_sequence=record['overlapping_HP0']['AR'],AW_or_B_overlap=False,
            actual_bridge_num_cache=2,actual_read_tag_slots=2)
    report['source_bindings']=sources
    report['conclusion']='The shared forward word-stream is held by the prior busy L2 bank; bridge read-RR is empty with tag capacity and no ordering fence. Extra N occurs before target AR and another N on its own read response. No writeback/B overlap or serialized-per-word delay.'
    report['limits']=['Source and sampled gate identify the blocked forward command; exact storage location of queued PF headers upstream is not asserted',
        'This local window does not establish a platform concurrency limit','No policy/refinement or benchmark source change; no physical/application timing result']
    (HERE/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: accepted forward+3 unchanged, busy-bank11->211, ownresponse+200, postfullpublication34 unchanged')


if __name__=='__main__':main()
