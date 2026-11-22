#!/usr/bin/env python3
"""FST framing/finalization evidence, distinct from recoverable reader EOF."""
import argparse
import json
from pathlib import Path
from common import bind


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

