#!/usr/bin/env python3
"""Future full167 audit with full validator input and supplemental counter archive."""
import argparse
from contextlib import closing
import fcntl
import gzip
import json
import os
from pathlib import Path
import signal
import sys
import contract as c


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation',required=True,type=Path)
    parser.add_argument('--preparation-sha256',required=True)
    parser.add_argument('--role',choices=c.ORDER,required=True)
    parser.add_argument('--native-sha256',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    c.require(args.execute,'default offline; explicit ROOT admission and --execute required')
    p,program=c.load(args.preparation,args.preparation_sha256)
    stage=Path(p['stage']);case=stage/args.role;out=stage/(args.role+'-audit')
    def interrupted(signum,frame):raise RuntimeError('audit caught signal '+str(signum))
    handlers={s:signal.signal(s,interrupted) for s in (signal.SIGINT,signal.SIGTERM,signal.SIGALRM,signal.SIGHUP)}
    signal.alarm(c.CAPS['audit_outer_s'])
    owned=False
    try:
        with (stage/'acquisition.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            c.require(not (case/'FAIL.json').exists(),'native failure cannot be audited as PASS')
            out.mkdir(exist_ok=False);owned=True
            with c.resource_phase(stage,p,out,out/'resource-phase.json') as guard:
                run=c.check_native(stage,args.role,p,args.preparation,args.native_sha256)
                c.require(not (case/'FAIL.json').exists(),'native failure cannot be audited as PASS')
                selected=c.original.audit.selection()
                selection=out/'selection.tsv'
                selection.write_text(''.join(key+'\t'+suffix+'\n' for key,(suffix,width) in selected.items()))
                c.require(c.bind(selection)['sha256']=='2c38d34248a066f58ed9526784955dab7d0b23b1cc15b240129530ec1f81086c','exact unchanged167 selection')
                fst=c.bind(case/'trace.fst')
                command=[p['reader']['path'],str(case/'trace.fst'),str(selection)]
                def completion():
                    life=json.loads((out/'reader.owned.json').read_text())
                    c.require(life['failure'] is None and life['owned_group_remaining'] is False,'reader ownership fully closed')
                    return life['returncode']
                with closing(c.original.guarded_reader(command,out/'reader.stderr',guard,timeout=c.CAPS['reader_s'])) as lines:
                    with gzip.open(out/'gp0-counter-projection.tsv.gz','wb') as saved:
                        # guarded_reader preserves exact ASCII line bytes, including
                        # missing final newline. No semantic/address/time filtering.
                        result,digest=c.archive.validate_complete((line.encode('ascii') for line in lines),saved,
                            selected,c.Validator(program,args.role),c.original.audit.edges,completion,guard)
                c.require(c.bind(case/'trace.fst')==fst,'closed rawFST unchanged')
                result['bindings']=dict(fst=fst,run=c.bind(case/'verification.json'),admission=c.bind(case/'admission.json'),
                    program=p['program'],model=p['model'],reader=p['reader'],selection=c.bind(selection),preparation=c.bind(args.preparation))
                result['archive']=dict(schema='full167-digest-explicit-counter-projection-v1',full_stream=digest,
                    counter_projection=c.bind(out/'gp0-counter-projection.tsv.gz'),
                    limits='Only three-counter projection archived; complete167 input fully validated and SHA/count retained; rawFST+schema+reader/source retained.')
                c.archive.write_json(out/'verification.json',result)
                adapter=out/'counter-check-input';adapter.mkdir()
                c.archive.write_json(adapter/'verification.json',dict(schema='counter-projection-input-only-v1',
                    full_audit=c.bind(out/'verification.json'),bindings=dict(events=c.bind(out/'gp0-counter-projection.tsv.gz'),run=c.bind(case/'verification.json'))))
                checker=next(r for r in c.FOUNDATION if r['path'].endswith('/check_counter_words.py'))
                checker_command=[sys.executable,checker['path'],'--audit',str(adapter),'--out',str(out/'counter-words.json')]
                def allowance():return c.CAPS['audit_per_case']-sum(f.stat().st_size for f in out.rglob('*') if f.is_file())-65536
                cp=c.native.owned_run(checker_command,out,dict(os.environ),out/'counter-checker.log',30,
                    None,guard,allowance)
                c.require(cp.returncode==0,'unchanged counter checker actual0')
                c.load(args.preparation,args.preparation_sha256)
                c.check_native(stage,args.role,p,args.preparation,args.native_sha256)
                names=('verification.json','selection.tsv','gp0-counter-projection.tsv.gz','counter-check-input/verification.json','counter-words.json','counter-checker.log','counter-checker.owned.json','reader.stderr','reader.owned.json')
            c.archive.write_json(out/'acceptance.json',dict(schema='csr-unmasked256-stream-acceptance-v1',role=args.role,
                preparation=c.bind(args.preparation),sources=p['runtime_sources'],native_sha256=args.native_sha256,
                resource_phase=c.bind(out/'resource-phase.json'),sealed_inputs=c.bind(out/'sealed-exit.json'),
                files=[c.bind(out/name) for name in names]))
            c.verify_audit(stage,args.role,p,args.preparation,c.bind(out/'acceptance.json')['sha256'])
            c.check_budget(stage,p)
    except BaseException:
        for s in handlers:signal.signal(s,signal.SIG_IGN)
        if owned and (out/'acceptance.json').exists():(out/'acceptance.json').rename(out/'FAILED-acceptance.json')
        raise
    finally:
        signal.alarm(0)
        for s,handler in handlers.items():signal.signal(s,handler)
    print(out/'acceptance.json')


if __name__=='__main__':main()
