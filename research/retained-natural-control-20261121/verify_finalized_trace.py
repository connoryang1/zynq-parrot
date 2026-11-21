#!/usr/bin/env python3
"""FST framing/finalization evidence, distinct from recoverable reader EOF."""
import argparse
import json
from pathlib import Path
from prepare import bind


def framing(path):
    size=path.stat().st_size;pos=0;sections=[]
    with path.open('rb') as f:
        header=f.read(74)
        if len(header)!=74 or header[0]!=0:raise ValueError('missing FST header')
        start,end=int.from_bytes(header[9:17],'big'),int.from_bytes(header[17:25],'big')
        count=int.from_bytes(header[65:73],'big')
        if end<=start or not count:raise ValueError('unfinalized/empty FST header')
        while pos<size:
            f.seek(pos);b=f.read(25)
            if len(b)<9:raise ValueError('trailing partial section')
            kind,length=b[0],int.from_bytes(b[1:9],'big')
            if kind==255 or length<8 or pos+1+length>size:raise ValueError('torn/incomplete FST section')
            row=dict(offset=pos,kind=kind,bytes=length+1)
            if kind in (1,5,8):
                if len(b)<25 or length<24:raise ValueError('short value-change section')
                row.update(begin_tick=int.from_bytes(b[9:17],'big'),end_tick=int.from_bytes(b[17:25],'big'))
                if row['end_tick']<row['begin_tick']:raise ValueError('reversed section time')
            sections.append(row);pos+=1+length
    vc=[r for r in sections if r['kind'] in (1,5,8)]
    if not vc or len(vc)!=count or vc[-1]['end_tick']!=end:raise ValueError('header/complete-section count or final time mismatch')
    if vc[0]['begin_tick']!=start:raise ValueError('first section/header start mismatch')
    for a,b in zip(vc,vc[1:]):
        if a['end_tick']!=b['begin_tick']:raise ValueError('value-section time discontinuity')
    return dict(header_start_tick=start,header_end_tick=end,header_value_section_count=count,
                complete_value_section_count=len(vc),all_section_bytes_exactly_cover_file=pos==size,
                final_value_section=vc[-1],sections=sections)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    before=bind(a.cohort);cohort=json.loads(a.cohort.read_text())
    if cohort['state']!='COMPLETE-both-arms-awaiting-full-trace-audit-no-performance-inference':raise ValueError('closed complete cohort required')
    results={}
    for row in cohort['runs']:
        if row['state']!='COMPLETE-checks-PASS-awaiting-full-trace-audit':raise ValueError('complete arm required')
        trace=row['trace'];path=Path(trace['path'])
        if bind(path)!=trace:raise ValueError('closed trace changed')
        results[str(row['mode'])]=dict(trace=trace,framing=framing(path))
        if bind(path)!=trace:raise ValueError('closed trace mutated')
    if bind(a.cohort)!=before:raise ValueError('closed cohort mutated')
    if a.output.exists():raise ValueError('preserve existing proof')
    a.output.write_text(json.dumps(dict(state='PASS-finalized-FST-framing',scope='Nonzero final header time, exact finalized value-section count/time continuity and full section framing; separate from complete guest/access/cache proofs. A recoverable EOF alone would not satisfy these checks.',cohort=before,source=bind(__file__),results=results),indent=2)+'\n')
    print('PASS finalized FST framing for both closed arms')


if __name__=='__main__':main()
