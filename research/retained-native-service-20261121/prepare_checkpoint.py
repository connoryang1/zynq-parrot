#!/usr/bin/env python3
"""Prepare an explicit compact whitelist; retain every excluded raw file in place."""
import gzip
import json
from pathlib import Path
from hp0_closed_pair import HERE,ROOT,bind,verify


def main():
    out=HERE/'checkpoint-manifest.json'
    if out.exists():raise ValueError('preserve prior compact manifest')
    closure=HERE/'closed-inputs.json';value=json.loads(closure.read_text())
    if value['state']!='CLOSED-READONLY-native-service-audits-PASS':raise ValueError('closed audits required')
    for row in value['source_and_tests'].values():verify(row)
    excluded=[];included=[]
    raw_names={'selected-events.tsv.gz','transactions.json.gz','misses.jsonl.gz',
               'references.jsonl.gz','time-counter.json.gz'}
    for p in sorted(HERE.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts:continue
        (excluded if p.name in raw_names else included).append(bind(p))
    report=dict(state='PASS-compact-closed-service-whitelist',closed_proof=bind(closure),
                included=included,external_raw_retained_unchanged=excluded,
                external_raw_bytes=sum(r['bytes'] for r in excluded),
                tracked_bytes=sum(r['bytes'] for r in included),
                source=bind(__file__),scope='Metadata, exact sources, tests and compact counterpart/offer ledgers only. Excluded raw files remain durable at hash-bound paths; no deletion or lossy substitution.')
    out.write_text(json.dumps(report,indent=2)+'\n')
    whitelist=[str(Path(r['path']).relative_to(ROOT)) for r in included]+[str(out.relative_to(ROOT))]
    (HERE/'checkpoint-whitelist.json').write_text(json.dumps(whitelist,indent=2)+'\n')
    print(json.dumps(dict(files=len(whitelist)+1,tracked_bytes=report['tracked_bytes'],external_raw_bytes=report['external_raw_bytes'],manifest=bind(out)),indent=2))


if __name__=='__main__':main()
