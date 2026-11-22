#!/usr/bin/env python3
"""Opt-in host replay of one closed stream; never launches a reader/model/tool."""
import argparse
from contextlib import redirect_stdout
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import signal
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent


def require(ok,message):
    if not ok:raise ValueError(message)


def binding(path):
    path=Path(path).resolve();h=hashlib.sha256();n=0
    with path.open('rb') as stream:
        for raw in iter(lambda:stream.read(1024**2),b''):h.update(raw);n+=len(raw)
    return dict(path=str(path),bytes=n,sha256=h.hexdigest())


def verify(row):
    require(binding(row['path'])==row,'input/source binding changed '+row['path'])


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def load_sources(plan):
    # Fresh process only: no production admission/profile module is imported.
    for row in plan['sources'].values():verify(row)
    source=Path(plan['source_dir']);sys.path.insert(0,str(source))
    original=module('schema_cache_original',plan['sources']['original_snapshot']['path'])
    candidate=module('schema_cache_candidate',plan['sources']['candidate']['path'])
    archive=module('schema_cache_archive',plan['sources']['archive']['path'])
    checker=module('schema_cache_counter',plan['sources']['counter_checker']['path'])
    require(Path(sys.modules['build'].__file__).resolve()==source/'build.py','literal original helper root, no import shadow')
    return original,candidate,archive,checker


def plain_gzip_sha(path):
    h=hashlib.sha256()
    with gzip.open(path,'rb') as stream:
        for raw in iter(lambda:stream.read(65536),b''):h.update(raw)
    return h.hexdigest()


def replay(name,edges,original,archive,checker,plan,out,guard):
    arm=out/name;arm.mkdir();started=time.monotonic()
    def interrupted(sig,frame):raise RuntimeError('fixed600s replay deadline/interruption '+str(sig))
    handlers={s:signal.signal(s,interrupted) for s in (signal.SIGALRM,signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
    signal.alarm(600)
    try:
        audit=json.loads(Path(plan['inputs']['original_audit']['path']).read_text())
        program=json.loads(Path(plan['inputs']['program']['path']).read_text())
        run=json.loads(Path(plan['inputs']['run']['path']).read_text())
        projection=arm/'gp0-counter-projection.tsv.gz'
        with gzip.open(plan['inputs']['events']['path'],'rb') as stream,gzip.open(projection,'wb') as saved:
            result,digest=archive.validate_complete(stream,saved,original.selection(),
                original.Validator(program,run['role']),edges,0,guard)
        require(digest==plan['expected_full_stream'],'all original bytes/events/counts/SHA/EOF, inherited closed reader0')
        expected={k:v for k,v in audit.items() if k!='bindings'}
        require(archive.semantic_bytes(result)==archive.semantic_bytes(expected),'every complete Validator semantic field identical')
        require(plain_gzip_sha(projection)==plain_gzip_sha(plan['inputs']['qualified_projection']['path']),'every supplemental counter-projection byte equal')
        archive.write_json(arm/'verification.json',dict(schema='parser-cache-host-replay-v1',
            scope='HOST ONLY; reader0 inherited from closed source, no reader/model execution',
            semantic=result,full_stream=digest,projection=binding(projection)))
        adapter=arm/'counter-check-input';adapter.mkdir()
        archive.write_json(adapter/'verification.json',dict(schema='counter-projection-input-only-v1',
            full_audit=binding(arm/'verification.json'),bindings=dict(events=binding(projection),run=plan['inputs']['run'])))
        argv=sys.argv
        try:
            sys.argv=['unchanged-counter-checker','--audit',str(adapter),'--out',str(arm/'counter-words.json')]
            with (arm/'counter-checker.log').open('w') as log,redirect_stdout(log):checker.main()
        finally:sys.argv=argv
        counter=json.loads((arm/'counter-words.json').read_text())
        require(counter['state']=='PASS final FST counter words equal actual GP0 reads' and counter['values']==plan['expected_counter_words'],'unchanged independent counter checker/all six words')
        summary=dict(state='PASS host equivalence only',arm=name,full_stream=digest,
            semantic_sha256=hashlib.sha256(archive.semantic_bytes(result)).hexdigest(),
            counter_words=counter['values'],elapsed_s_host_verification_only=time.monotonic()-started)
        archive.write_json(arm/'summary.json',summary);guard();return summary
    finally:
        signal.alarm(0)
        for sig,handler in handlers.items():signal.signal(sig,handler)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-sha256',required=True)
    parser.add_argument('--release',required=True,type=Path)
    parser.add_argument('--release-sha256',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();require(args.execute,'default offline; ROOT resource review/release required')
    path=HERE/'plan.DRAFT.json';require(binding(path)['sha256']==args.plan_sha256,'external fixed plan SHA')
    plan=json.loads(path.read_text());require(plan['state']=='PREPARED UNEXECUTED; ROOT resource release required','source-only plan')
    require(binding(args.release)['sha256']==args.release_sha256,'external ROOT release SHA')
    release=json.loads(args.release.read_text())
    require(release['schema']=='retained-parser-cache-host-release-v2-normal' and release['ROOT_approved'] is True and release['plan']==binding(path) and release['qualified_outer_guard_prices_all_current_OTHER'] is True,'actual ROOT ownership/resource pricing first')
    require(release['fixed_selection_no_mutator_precondition_reviewed'] is True,'fixed selected mapping, not arbitrary caller mutation')
    require(release['malformed_input_gate_reviewed'] is True,'separate actual malformed-input host gate required first')
    verify(release['malformed_input_gate'])
    out=Path(release['output_root']);require(out.is_absolute() and not out.exists() and release['output_cap_bytes']==32*1024**2 and release['per_arm_timeout_s']==600 and release['outer_timeout_s']==1280,'fresh fixed32MiB/600-per-arm/1280-outer release')
    prior_bytes=release['preserved_prior_attempt_output_bytes']
    require(type(prior_bytes) is int and 0<=prior_bytes<32*1024**2,'ROOT measured closed prior output inside unchanged combined cap')
    for row in plan['inputs'].values():verify(row)
    for row in plan['prior_attempt']['bindings'].values():verify(row)
    original,candidate,archive,checker=load_sources(plan)
    out.mkdir();started=time.monotonic();previous=None;max_gap=0
    def guard():
        nonlocal previous,max_gap
        now=time.monotonic()
        if previous is not None:max_gap=max(max_gap,now-previous);require(now-previous<=1,'host replay guard gap over1s')
        previous=now;require(now-started<1280,'fixed1280s complete host batch')
        used=prior_bytes+sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
        require(used<=32*1024**2,'same32MiB output cap')
        require(shutil.disk_usage(out).free>=1024**3+32*1024**2-used,'RUN floor+remaining output; outer guard prices OTHER')
    before={name:binding(row['path']) for name,row in plan['sources'].items()}
    guard()
    # Entire same raw stream enters the same original Validator for both arms.
    results=[replay(name,edges,original,archive,checker,plan,out,guard)
        for name,edges in (('original',original.edges),('candidate',candidate.edges))]
    require(results[0]['full_stream']==results[1]['full_stream'] and results[0]['semantic_sha256']==results[1]['semantic_sha256'] and results[0]['counter_words']==results[1]['counter_words'],'complete baseline/candidate equivalence')
    for name,row in plan['sources'].items():require(before[name]==binding(row['path']),'source immutable '+name)
    for row in plan['inputs'].values():verify(row)
    for row in plan['prior_attempt']['bindings'].values():verify(row)
    archive.write_json(out/'equivalence.json',dict(state='PASS HOST ONLY parser-cache equivalence; no production promotion',
        plan=binding(path),release=binding(args.release),arms=results,max_guard_gap_s=max_gap,
        no_new_reader_model_target=True,no_speedup_claim=True))
    print(out/'equivalence.json')


if __name__=='__main__':main()
