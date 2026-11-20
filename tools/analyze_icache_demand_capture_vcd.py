#!/usr/bin/env python3
"""Check live demand-copy engagement and equal-capacity I-buffer consumption.

Input is a closed full-core FST converted to VCD on stdin. Architectural CSR
read PCs mark a commit-bounded diagnostic window, not a cycle benchmark.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from cache_overlap_vcd import rising_edges

CACHE = '.fe.icache.'
WATCH = {
    'clock': '.be.clk_i', 'reset': '.be.reset_i',
    'commit_pc': '.be.calculator.commit_pkt_cast_o.pc',
    'commit_v': '.be.calculator.commit_pkt_cast_o.instret',
    'enabled': CACHE+'replay_buffer_demand_capture_p',
    'capture_input': CACHE+'demand_capture_input',
    'capture_active': CACHE+'demand_capture_active_r',
    'buffer_write': CACHE+'replay_buffer_write',
    'buffer_write_demand': CACHE+'replay_buffer_pkt_demand_r',
    'buffer_write_addr': CACHE+'replay_buffer_pkt_r.addr',
    'buffer_write_slot': CACHE+'replay_buffer_write_slot',
    'buffer_hit': CACHE+'replay_buffer_hit_tv',
    'cache_hit': CACHE+'cache_hit_v_tv',
    'hit_v': CACHE+'hit_v_o', 'hit_yumi': CACHE+'yumi_i',
    'fetch_addr': CACHE+'paddr_tv_r',
    'alloc': CACHE+'replay_buffer_alloc_r',
    'data_addr': CACHE+'data_mem_pkt_cast_i.addr',
    'data_opcode': CACHE+'data_mem_pkt_cast_i.opcode',
    'data_fill': CACHE+'data_mem_pkt_cast_i.fill_index',
    'data_v': CACHE+'data_mem_pkt_v_i',
    'data_yumi': CACHE+'data_mem_pkt_yumi_o',
    'req_yumi': CACHE+'cache_req_yumi_i',
    'cached_req': CACHE+'cached_req',
    'req_addr': CACHE+'cache_req_cast_o.addr',
    'abort': CACHE+'miss_abort_i', 'abort_inflight': CACHE+'abort_inflight',
}


def read_header(stream):
    scopes=[]; found={}; widths={}; timescale=[]; in_timescale=False
    for line in stream:
        words=line.split()
        if '$timescale' in line: in_timescale=True
        if in_timescale:
            timescale += [x for x in words if x not in ('$timescale','$end')]
            if '$end' in line: in_timescale=False
        if words[:1]==['$scope']: scopes.append(words[2])
        elif words[:1]==['$upscope']: scopes.pop()
        elif words[:1]==['$var']:
            full='.'.join(scopes+[words[4]])
            labels=[key for key,suffix in WATCH.items() if full.endswith(suffix)]
            for field,label in (('replay_buffer_beat_v_r','beat'),('replay_buffer_addr_r','addr')):
                match=re.search(re.escape(CACHE+field)+r'\[(\d+)\]$',full)
                if match: labels.append(label+match.group(1))
            for label in labels:
                found.setdefault(label,[]).append((words[3],full))
                widths[label]=int(words[2])
        elif words[:1]==['$enddefinitions']: break
    required=set(WATCH)|{'beat'+str(i) for i in range(32)}|{'addr'+str(i) for i in range(32)}
    for key in required:
        if len(found.get(key,[]))!=1:
            raise ValueError('missing/ambiguous '+key+': '+repr(found.get(key)))
    return {key:matches[0] for key,matches in found.items()},widths,''.join(timescale)


def analyze(stream, begin_pc=0x8000040c, end_pc=0x80000414,
            prefix_begin=0x80001000,prefix_end=0x80001200):
    selected,widths,timescale=read_header(stream)
    full_mask=(1<<widths['beat0'])-1
    stats=Counter(); timed=Counter(); published=Counter(); captured=Counter()
    prefix_events=[]; timed_active=False; boundaries=[]; pending_line=None
    last_complete={}; begin_complete=None; max_complete=0
    side_lines=Counter(); timed_side_lines=Counter(); timed_cache_lines=Counter()
    mismatches=[]; feature_values=set(); final_complete={}
    for cycle,timestamp,v in rising_edges(stream,selected):
        if v.get('reset')!=0: continue
        feature_values.add(v.get('enabled'))
        alloc=v.get('alloc') or 0
        complete={i:v.get('addr'+str(i))<<6 for i in range(32)
                  if (alloc>>i)&1 and v.get('beat'+str(i))==full_mask}
        max_complete=max(max_complete,len(complete)); final_complete=complete
        for slot,addr in complete.items():
            if last_complete.get(slot)!=addr:
                published[addr]+=1; stats['completion_epochs']+=1
                if timed_active: timed['completion_epochs']+=1
                if prefix_begin<=addr<prefix_end:
                    prefix_events.append({'event':'complete','cycle':cycle,'line':hex(addr),'slot':slot,
                                          'timed':timed_active})
        last_complete=complete
        if v.get('commit_v')==1 and v.get('commit_pc')==begin_pc:
            if timed_active: raise ValueError('overlapping timing boundaries')
            timed_active=True
            begin_complete=[hex(a) for a in complete.values() if prefix_begin<=a<prefix_end]
            boundaries.append({'kind':'begin','cycle':cycle,'timestamp':timestamp,'pc':hex(begin_pc)})
        if v.get('commit_v')==1 and v.get('commit_pc')==end_pc:
            if not timed_active: raise ValueError('timing end without begin')
            timed_active=False
            boundaries.append({'kind':'end','cycle':cycle,'timestamp':timestamp,'pc':hex(end_pc)})
        def count(key):
            stats[key]+=1
            if timed_active: timed[key]+=1
        if v.get('req_yumi')==1 and v.get('cached_req')==1:
            pending_line=v['req_addr']&~63; count('accepted_cached_misses')
        if v.get('capture_input')==1:
            count('accepted_capture_beats')
            addr=v['data_addr']&~63; captured[addr]+=1
            if v.get('data_v')!=1 or v.get('data_yumi')!=1 or v.get('data_opcode')!=0:
                mismatches.append({'cycle':cycle,'reason':'capture without accepted ordinary data write'})
            if pending_line!=addr:
                mismatches.append({'cycle':cycle,'reason':'physical line differs from accepted cached miss',
                                   'request_line':None if pending_line is None else hex(pending_line),
                                   'data_line':hex(addr)})
            if prefix_begin<=addr<prefix_end:
                prefix_events.append({'event':'capture','cycle':cycle,'line':hex(addr),
                                      'mask':v['data_fill'],'timed':timed_active})
        if v.get('buffer_write')==1 and v.get('buffer_write_demand')==1:
            count('registered_capture_writes')
        if v.get('buffer_hit')==1:
            count('side_hit_eligible_cycles')
            if v.get('cache_hit')!=0:
                mismatches.append({'cycle':cycle,'reason':'side hit overlaps ordinary cache hit'})
        if v.get('hit_v')==1 and v.get('hit_yumi')==1:
            addr=v['fetch_addr']&~63
            if v.get('buffer_hit')==1:
                count('consumed_side_fetches'); side_lines[addr]+=1
                if timed_active: timed_side_lines[addr]+=1
            elif v.get('cache_hit')==1:
                count('consumed_cache_fetches')
                if timed_active: timed_cache_lines[addr]+=1
            if timed_active and prefix_begin<=v['fetch_addr']<prefix_end:
                count('timed_prefix_consumed_fetches')
                if v.get('buffer_hit')==1: count('timed_prefix_side_fetches')
                if v.get('cache_hit')==1: count('timed_prefix_cache_fetches')
    if len(boundaries)!=2 or timed_active: raise ValueError('need exactly one closed CSR-commit window')
    return {'scope':'feature engagement / consumption, not speedup',
            'sampling':'stable values before actual BE rising edges',
            'window':'commit of source global-cycle CSR reads; diagnostic boundary only',
            'timescale':timescale,'capture_parameter_observed':sorted(feature_values),
            'fill_beats_per_line':widths['beat0'],'stats':dict(stats),'timed_stats':dict(timed),
            'timed_boundaries':boundaries,'timed_commit_window_cycles':boundaries[1]['cycle']-boundaries[0]['cycle'],
            'max_complete_entries':max_complete,'prefix_complete_at_begin':sorted(begin_complete),
            'distinct_captured_lines':len(captured),'distinct_completed_lines':len(published),
            'captured_beats_by_line':{hex(k):n for k,n in sorted(captured.items())},
            'completed_epochs_by_line':{hex(k):n for k,n in sorted(published.items())},
            'consumed_side_fetches_by_line':{hex(k):n for k,n in sorted(side_lines.items())},
            'timed_side_fetches_by_line':{hex(k):n for k,n in sorted(timed_side_lines.items())},
            'timed_cache_fetches_by_line':{hex(k):n for k,n in sorted(timed_cache_lines.items())},
            'final_complete_lines':{str(k):hex(a) for k,a in final_complete.items()},
            'prefix_events':prefix_events,'provenance_issues':mismatches,
            'signals':{key:value[1] for key,value in selected.items()}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=analyze(sys.stdin)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('capture_parameter_observed','fill_beats_per_line','stats',
                    'timed_stats','timed_commit_window_cycles','max_complete_entries',
                    'prefix_complete_at_begin','provenance_issues')},indent=2))

if __name__=='__main__': main()
