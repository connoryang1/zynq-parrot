#!/usr/bin/env python3
"""Read the complete available failed trace for progress, never acceptance."""
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
RUN = OUT.parent
AUDIT = RUN.parent/'dcache-observability/analyzer'
sys.path.insert(0,str(AUDIT))
from analyze_resume_data_reuse_vcd import header
from cache_overlap_vcd import rising_edges


def rec(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return {'path':str(Path(path).resolve()),'sha256':h.hexdigest(),'bytes':Path(path).stat().st_size}


def main():
    session=json.loads((RUN/'session.json').read_text())
    symbols={key:int(value,16)for key,value in session['program']['symbols'].items()}
    functions=[]
    for line in Path(session['program']['symbol_file']['path']).read_text().splitlines():
        match=re.fullmatch(r'([0-9a-fA-F]+) [Tt] (.+)',line)
        if match:functions.append((int(match[1],16),match[2]))
    functions.sort()
    def location(pc):
        found=[row for row in functions if row[0]<=pc]
        if not found:return None
        address,name=found[-1]
        return name+'+0x%x'%(pc-address)
    result={'scope':'Failed-run progress diagnosis only; no accepted execution/capacity result.',
            'session':rec(RUN/'session.json'),'fst':rec(RUN/'runtime/dump.fst'),
            'elf':rec(RUN/'program/benchmark.riscv'),'log':rec(RUN/'runtime/run.log'),
            'analyzer':rec(__file__),'header_source':rec(AUDIT/'analyze_resume_data_reuse_vcd.py'),
            'clock_source':rec(AUDIT/'cache_overlap_vcd.py'),'sampling':'Stable pre-BE-rising-edge retirement; global_cycle_r labels are commit-time observations, distinct from the CSR instruction read values.',
            'complete_available_trace_read':False,'host_parse_limit_seconds':180}
    counts=Counter();contexts=Counter();pcs=Counter();labels=[];last=deque(maxlen=40)
    first_global=last_global=None;reset=False;first_retired=None;errors=[];active={}
    start=time.monotonic()
    with (OUT/'converter.stderr').open('w')as stderr:
        converter=subprocess.Popen(['fst2vcd',str(RUN/'runtime/dump.fst')],stdout=subprocess.PIPE,stderr=stderr,text=True)
        try:
            selected,timescale,widths=header(converter.stdout)
            keep=('clock','reset','global_cycle','commit_v','commit_pc','commit_thread','context_0','context_1')
            selected={key:selected[key]for key in keep}
            result.update(timescale=timescale,signals={key:value[1]for key,value in selected.items()})
            phase_pcs={value:key for key,value in symbols.items()if key!='resume_data_config'}
            for edge,timestamp,value in rising_edges(converter.stdout,selected):
                if edge%65536==0 and time.monotonic()-start>180:raise TimeoutError('bounded parser time exceeded')
                if value.get('reset')==1:reset=True
                if not reset or value.get('reset')!=0:continue
                global_cycle=value.get('global_cycle')
                if global_cycle is None:raise ValueError('unknown active global counter')
                if first_global is None:first_global=global_cycle
                if last_global is not None and global_cycle!=last_global+1:errors.append({'global_discontinuity':[last_global,global_cycle]})
                last_global=global_cycle
                if value.get('commit_v')!=1:continue
                slot=value['commit_thread'];context=value['context_'+str(slot)];pc=value['commit_pc']
                row={'edge':edge,'timestamp':timestamp,'global_cycle':global_cycle,'pc':hex(pc),
                     'slot':slot,'context':context,'location':location(pc)}
                contexts[context]+=1;pcs[pc]+=1;last.append(row)
                if first_retired is None:first_retired=row
                if pc in phase_pcs:
                    kind=phase_pcs[pc];event=dict(row,label=kind);labels.append(event)
                    if kind=='resume_data_request_begin':
                        if context in active:errors.append({'nested_begin_context':context})
                        active[context]=counts['begin_ctx'+str(context)]
                        counts['begin_ctx'+str(context)]+=1
                    elif kind=='resume_data_request_end':
                        if context not in active:errors.append({'end_without_begin_context':context})
                        else:active.pop(context)
                        counts['end_ctx'+str(context)]+=1
                    else:counts[kind]+=1
            converter.stdout.close()
            result['fst2vcd_returncode']=converter.wait(timeout=10)
            result['complete_available_trace_read']=converter.returncode==0
        except BaseException as error:
            result['parse_error']=repr(error)
        finally:
            if converter.poll()is None:
                converter.terminate()
                try:converter.wait(timeout=10)
                except subprocess.TimeoutExpired:converter.kill();converter.wait()
            result['fst2vcd_returncode']=converter.returncode
    text=(RUN/'runtime/run.log').read_text()
    host_retired=re.findall(r'minstret delta:\s+(\d+)',text)
    result.update(elapsed_parse_seconds=time.monotonic()-start,reset_observed=reset,
                  first_active_global_cycle=first_global,last_active_global_cycle=last_global,
                  first_retired=first_retired,last_retired=list(last),request_boundary_counts=dict(counts),
                  phase_boundary_events=labels,commits_by_context=dict(contexts),
                  total_observed_retirements=sum(contexts.values()),
                  host_reported_retired_instructions=int(host_retired[-1])if host_retired else None,
                  most_common_pcs=[{'pc':hex(pc),'count':count,'location':location(pc)}for pc,count in pcs.most_common(20)],
                  open_request_contexts=active,diagnostic_errors=errors,
                  converter_stderr=(OUT/'converter.stderr').read_text(),
                  finalization_caveat='Converter EOF/exit0 establishes readability of the complete available FST, not successful simulator/guest shutdown. Native target timeout, BSG FAIL and GPIO final-block fatal remain a failed execution.')
    (OUT/'progress.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key]for key in ('complete_available_trace_read','fst2vcd_returncode','elapsed_parse_seconds','first_active_global_cycle','last_active_global_cycle','request_boundary_counts','total_observed_retirements','open_request_contexts','diagnostic_errors')},indent=2))


if __name__=='__main__':main()
