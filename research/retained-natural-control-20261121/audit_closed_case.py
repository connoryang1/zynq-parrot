#!/usr/bin/env python3
"""Completion admission for the unchanged selected-FST normal-D audit.
Never invokes a target; rejects running/failed arms and unfinalized capped files.
"""
import argparse
import collections
import gzip
import json
from pathlib import Path
import subprocess
import sys
from prepare import bind, HERE, ROOT
from protocol import parse
from run_cohort_v3 import MODEL_SHA, ELF_SHA, CAP


def verify(record):
    if bind(record['path']) != record:
        raise ValueError('closed input changed: '+record['path'])


def admission(cohort, mode, text, guest, metadata):
    if cohort['state'] not in ('COMPLETE-both-arms-awaiting-full-trace-audit-no-performance-inference',
                               'STOPPED-failure-preserved-no-retry'):
        raise ValueError('cohort still active or not an admitted terminal state')
    if cohort['model']['sha256'] != MODEL_SHA or cohort['elf']['sha256'] != ELF_SHA:
        raise ValueError('wrong exact model/program')
    rows = [r for r in cohort['runs'] if r['mode'] == mode]
    if mode not in (0,15) or len(rows) != 1:
        raise ValueError('wrong/duplicate case')
    row = rows[0]
    if row['state'] != 'COMPLETE-checks-PASS-awaiting-full-trace-audit':
        raise ValueError('failed/partial arm has no accepted access audit')
    if not 0 < row['trace']['bytes'] < CAP:
        raise ValueError('empty/at-limit trace')
    if parse(text, mode, row['returncode']) != guest:
        raise ValueError('stored guest observations do not match complete transcript')
    expected = json.loads((HERE/'admission-v3.json').read_text())['dcache_metadata_template']
    for name in ('begin_pc','end_pc','warmup_requests','timed_requests',
                 'expected_target_loads_by_context','expected_total_by_context'):
        if metadata[name] != expected[name]:
            raise ValueError('changed independent request expectation: '+name)
    regions = [dict(context=v['context'],base=hex(v['base']),bytes=v['bytes']) for v in guest['regions']]
    if metadata['regions'] != regions:
        raise ValueError('metadata regions differ from actual checked allocations')
    for name in ('whole_begin','whole_end'):
        if metadata[name+'_cycle'] != guest['phases'][name]:
            raise ValueError('metadata WHOLE bounds differ from checked transcript')
    return row


def summarize(events, phases):
    windows = {'program':None,'whole':(phases['whole_begin'],phases['whole_end']),
               'timed_ring':(phases['timed_begin'],phases['timed_end'])}
    result = {k:collections.Counter() for k in windows}
    previous = None
    for line in events:
        event = json.loads(line)
        cycle = event['global_cycle']
        if previous is not None and cycle < previous:
            raise ValueError('event cycle reversal')
        previous = cycle
        for window,bounds in windows.items():
            # CSR values are sampled in the retired label instruction. Both
            # lane's D edges use that same global register; half-open bounds.
            if bounds is not None and not bounds[0] <= cycle < bounds[1]:
                continue
            counts = result[window]
            counts[event['event']] += 1
            if event['event'] == 'reference':
                counts['reference_'+event['operation']] += 1
                counts['reference_'+event['outcome']] += 1
                if event['target']:
                    counts['target_reference'] += 1
                    counts['target_'+event['operation']] += 1
                    counts['target_'+event['outcome']] += 1
    return {k:dict(v) for k,v in result.items()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort',type=Path,required=True)
    p.add_argument('--mode',type=int,choices=(0,15),required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    before=bind(a.cohort)
    cohort=json.loads(a.cohort.read_text())
    row=next(r for r in cohort['runs'] if r['mode']==a.mode)
    for record in cohort['frozen_inputs'].values():verify(record)
    for name in ('trace','log','guest','trace_metadata'):verify(row[name])
    for record in row['linked_libraries']:verify(record)
    guest=json.loads(Path(row['guest']['path']).read_text())
    metadata=json.loads(Path(row['trace_metadata']['path']).read_text())
    admission(cohort,a.mode,Path(row['log']['path']).read_text(),guest,metadata)
    a.output.mkdir(parents=True,exist_ok=False)
    cmd=[sys.executable,str(HERE/'dcache-adapter/fst_adapter.py'),
         '--fst',row['trace']['path'],'--reader',str(ROOT/'research/retained-system-geometry-20261121/reader/fst_events'),
         '--model-source-list',str(ROOT/'research/retained-system-geometry-20261121/full-system1280-native0-03/actual-source-list.json'),
         '--metadata',row['trace_metadata']['path'],'--output',str(a.output/'normal-dcache'),'--timeout','600']
    with (a.output/'audit.log').open('w') as log:
        r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=780)
    report=json.loads((a.output/'normal-dcache/analysis.json').read_text())
    if r.returncode or report['state']!='PASS-normal-cache-invariants':
        raise ValueError('closed normal-cache audit failed; preserve output')
    with gzip.open(a.output/'normal-dcache/events.jsonl.gz','rt') as f:
        counts=summarize(f,guest['phases'])
    if bind(a.cohort)!=before:
        raise ValueError('cohort mutated during closed audit')
    for name in ('trace','log','guest','trace_metadata'):verify(row[name])
    summary=dict(state='PASS-complete-normal-D-audit',scope='Actual complete normal Dcache accesses, tag/permission hits and refill invariants. Counts are clipped half-open by actual checked CSR bounds. Conditional victim ledgers from the legacy extractor are not interpreted.',
                 mode=a.mode,cohort=before,closed_trace=row['trace'],guest=row['guest'],metadata=row['trace_metadata'],
                 normal_dcache_report=bind(a.output/'normal-dcache/analysis.json'),source=bind(__file__),
                 maintained_checker=bind(ROOT/'testing/check_run.py'),protocol=bind(HERE/'protocol.py'),
                 command=cmd,counts=counts,
                 limits=['No load-data/tag-payload bit comparison by this auditor; independent guest request/checksum and complete execution checks are separate.',
                         'Normal Dcache only. Retained lookup/publication/mutation/clear telemetry requires its separate audit.',
                         'No calibrated latency, FPGA/Linux projection, or prefetch benefit claim.'])
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(state=summary['state'],mode=a.mode,counts=counts),indent=2))


if __name__=='__main__':main()
