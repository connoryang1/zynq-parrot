#!/usr/bin/env python3
"""Replay corrupted known-closed64D bytes through the unchanged full validator."""
import argparse
import gzip
import hashlib
import io
import itertools
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

import archive_stream as a


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--qualified',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--source-dir',type=Path,required=True)
    p.add_argument('--budget-root',type=Path,required=True)
    args=p.parse_args()
    a.check_chain(args.qualified)
    audit,chosen,sources=a.load_auditor(args.source_dir,64)
    old=json.loads((args.audit/'verification.json').read_text())
    original=json.loads(Path(old['bindings']['program']['path']).read_text())
    run=json.loads(Path(old['bindings']['run']['path']).read_text())
    args.out.mkdir(exist_ok=False)
    start=time.monotonic();guard=lambda:a.resource_guard(args.budget_root,start,600)
    def interrupted(signum,frame):raise RuntimeError('negative fixture fixed deadline/interruption')
    for sig in (signal.SIGALRM,signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupted)
    signal.alarm(600)
    cases=[]
    try:
        handle=None
        with gzip.open(old['bindings']['events']['path'],'rb') as stream:
            for raw in stream:
                f=raw.decode('ascii').rstrip('\n').split('\t')
                if f[:2]==['#SIGNAL','d.id']:
                    handle=int(f[3]);break
        a.require(handle is not None,'actual D full512-bit insert payload selected')
        mutations=[0]
        def corrupted(stream):
            for raw in stream:
                f=raw.decode('ascii').rstrip('\n').split('\t')
                if len(f)==3 and not f[0].startswith('#') and int(f[1])==handle and set(f[2])<=set('01'):
                    f[2]=f[2][:-1]+('0' if f[2][-1]=='1' else '1')
                    raw=('\t'.join(f)+'\n').encode('ascii');mutations[0]+=1
                yield raw
        with gzip.open(old['bindings']['events']['path'],'rb') as stream, gzip.open(args.out/'failed-noncounter-projection.gz','wb') as saved:
            traced=a.FullStream(corrupted(stream),saved,guard)
            validator=chosen.Validator(original,run['role'])
            try:
                for t,clocks,values in audit.edges(traced,audit.selection()):validator.sample(t,clocks,values)
                validator.finish()
                raise AssertionError('corrupt full payload was accepted')
            except ValueError as error:
                a.require('full512-bit publication payload' in str(error),'actual full payload assertion must reject: '+str(error))
                cases.append(dict(case='actual noncounter512b insert data bit',rejected=str(error),
                    mutations=mutations[0],consumed_bytes=traced.bytes,consumed_lines=traced.lines,
                    consumed_prefix_sha256=traced.digest.hexdigest(),complete_stream=False))
        # A real original reader prefix has the complete167 declaration schema,
        # but no EOF. It must fail the unchanged parser, not become a full proof.
        with gzip.open(old['bindings']['events']['path'],'rb') as stream:
            prefix=list(itertools.islice(stream,500))
        try:
            for t,clocks,values in audit.edges((r.decode('ascii') for r in prefix),audit.selection()):pass
            raise AssertionError('real incomplete prefix accepted')
        except ValueError as error:
            a.require('closed complete FST' in str(error),'exact incomplete-stream rejection')
            cases.append(dict(case='actual500-line prefix without EOF',rejected=str(error),
                prefix_sha256=hashlib.sha256(b''.join(prefix)).hexdigest(),complete_stream=False))
        # Mutate the final observed counter in the actual qualified projection.
        projection=args.qualified/'gp0-counter-projection.tsv.gz'
        with gzip.open(projection,'rb') as f:rows=f.readlines()
        handles={int(r.decode().split('\t')[3]) for r in rows if r.startswith(b'#SIGNAL\t')}
        index=max(n for n,r in enumerate(rows) if not r.startswith(b'#') and int(r.split(b'\t')[1]) in handles)
        fields=rows[index].decode().rstrip('\n').split('\t')
        fields[2]=fields[2][:-1]+('0' if fields[2][-1]=='1' else '1')
        rows[index]=('\t'.join(fields)+'\n').encode('ascii')
        sub=args.out/'counter-bit';sub.mkdir()
        with gzip.open(sub/'projection.gz','wb') as f:f.writelines(rows)
        a.write_json(sub/'verification.json',dict(bindings=dict(events=a.bind(sub/'projection.gz'),run=old['bindings']['run'])))
        command=[sys.executable,str(args.source_dir/'check_counter_words.py'),'--audit',str(sub),'--out',str(sub/'counter-words.json')]
        process=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
        (sub/'checker.log').write_bytes(process.stdout)
        a.require(process.returncode!=0 and not (sub/'counter-words.json').exists(),'actual GP0 counter mismatch rejected')
        a.require(b'actual FST counter words match exact GP0 read values' in process.stdout,'expected checker rejection')
        cases.append(dict(case='actual final GP0 word bit flip',checker_returncode=process.returncode,rejected=True))
        guard()
        a.write_json(args.out/'verification.json',dict(state='PASS negative archive qualification only',cases=cases,
            bindings=dict(accepted_archive=a.bind(args.qualified/'acceptance.json'),original_audit=a.bind(args.audit/'verification.json')),
            sources=sources+[a.bind(__file__),a.bind(a.__file__)],elapsed_s=time.monotonic()-start,
            limits='Corrupted host replay/prefix/projection only; no target or FST reader; no accepted corrupted proof.'))
        print(json.dumps(cases))
    finally:signal.alarm(0)


if __name__=='__main__':main()
