#!/usr/bin/env python3
"""Match final actual FST counter words to GP0 reads without rereading the FST."""
import argparse
import gzip
import json
from pathlib import Path

from build import bind,require


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--audit',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path);a=parser.parse_args();require(not a.out.exists(),'new supplemental proof required')
    path=a.audit/'verification.json';proof=json.loads(path.read_text());events=proof['bindings']['events'];run_binding=proof['bindings']['run']
    require(bind(events['path'])==events and bind(run_binding['path'])==run_binding,'closed stream/run bindings')
    run=json.loads(Path(run_binding['path']).read_text());handles={};values={};ended=False
    with gzip.open(events['path'],'rt') as stream:
        for line in stream:
            parts=line.rstrip('\n').split('\t')
            if parts[0]=='#SIGNAL' and parts[1] in ('obs.hits','obs.published','obs.beats'):
                require(parts[1] not in handles and parts[2]=='32','counter declaration')
                handles[parts[1]]=int(parts[3])
            elif parts[0]=='#END':require(not ended,'one EOF');ended=True
            elif not parts[0].startswith('#'):
                require(not ended,'no postEOF events')
                handle=int(parts[1])
                if handle in handles.values():
                    require(set(parts[2])<=set('01') and len(parts[2])==32,'known final counter word');values[handle]=int(parts[2],2)
    require(ended and len(handles)==3,'complete counter stream')
    actual=[]
    for key in ('obs.hits','obs.published','obs.beats'):
        require(handles[key] in values,'counter word present');word=values[handles[key]];actual.extend((word&65535,word>>16))
    require(actual==run['counters'],'actual FST counter words match exact GP0 read values')
    a.out.write_text(json.dumps(dict(state='PASS final FST counter words equal actual GP0 reads',values=actual,
        audit=bind(path),run=run_binding,events=events,auditor=bind(__file__)),indent=2)+'\n');print(a.out)


if __name__=='__main__':main()
