#!/usr/bin/env python3
"""Archive/recheck closed r2 gates only; never builds or executes a model."""
import argparse
import gzip
import json
from pathlib import Path
from run_gate import ROOT,R1,BP,bind,full_bind,write,git


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args();run=args.run.resolve();out=Path(__file__).resolve().parent/'closure01'
    if out.exists():raise ValueError('new closure required')
    m=json.loads((run/'session.json').read_text())
    if m['state']!='PASS clean1280+observe1 integrity/advisory execution; closed trace audits pending':raise ValueError('closed execution absent')
    if any(c.get('returncode') not in (0,-6) for c in m['commands']):raise ValueError('failed gate command')
    for c in m['commands']:
        if bind(c['log']['path'])!=c['log']:raise ValueError('command log changed')
    if full_bind(m['model']['path'])!=m['model']:raise ValueError('model changed')
    for name,b in m['source_before'].items():
        if full_bind(name)!=b:raise ValueError('critical source changed')
    g=json.loads((run/'integrity-geometry01/verification.json').read_text())
    v=json.loads((run/'strict-advisory01/verification.json').read_text())
    c=json.loads((run/'counter-audit01/verification.json').read_text())
    i=json.loads((run/'integrity/verification.json').read_text())
    a=json.loads((run/'advisory/verification.json').read_text())
    if not v['accepted'] or g['state']!='PASS-closed-geometry-and-selected-reader-EOF':raise ValueError('geometry/strict gate not passed')
    if not c['state'].startswith('PASS actual counter transitions') or c['firsttouch_counts']!={'i':[1,1,8],'d':[1,1,8]}:raise ValueError('observer gate')
    if v['bindings']['fst']!=a['trace'] or c['bindings']['fst']!=a['trace']:raise ValueError('same closed advisory trace required')
    for proof in (i,a):
        for b in proof['files']:
            if full_bind(b['path'])!=b:raise ValueError('closed runtime artifact changed')
    if git(ROOT,'rev-parse','refs/heads/experiment/linux-retained-native1280-r1')!=R1:raise ValueError('r1 moved')
    if git(ROOT,'rev-parse','refs/remotes/origin/experiment/linux-retained-native1280-r1')!=R1:raise ValueError('r1 remote-tracking moved')
    out.mkdir();artifacts=[]

    def keep(path,name=None,compress=True):
        path=Path(path);raw=path.read_bytes();name=name or str(path.relative_to(run))
        dest=out/(name+('.gz' if compress else ''));dest.parent.mkdir(parents=True,exist_ok=True)
        encoded=gzip.compress(raw,compresslevel=6,mtime=0) if compress else raw
        dest.write_bytes(encoded)
        if (gzip.decompress(encoded) if compress else encoded)!=raw:raise ValueError('archive roundtrip')
        artifacts.append(dict(source=bind(path),archive=bind(dest),gzip=compress))

    for name in ('session.json','actual-source-list.json','make-preflight.log','clean.log','build.log','loader.log',
                 'integrity-checker.log','advisory-checker.log'):
        keep(run/name)
    keep(Path(m['model']['path']),'model')
    keep(run/'verilator/obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat','verFiles.dat')
    for name in ('bsg_blackparrot_pkg.sv','bsg_bootrom.sv'):keep(run/'verilator'/name)
    for case in ('integrity','advisory'):
        for name in ('prog.riscv','prog.nbf','run.log','admission.json','process.json','verification.json'):keep(run/case/name)
    for case in ('integrity-geometry01','strict-advisory01','counter-audit01'):
        for path in sorted((run/case).iterdir()):
            if path.is_file():keep(path,compress=path.suffix!='.gz')
    for path in m['source_before']:keep(path,'source/'+str(Path(path).relative_to(ROOT)))
    lanes={name:dict(publications=len(lane['publications']),accepted_hits=len(lane['hits']),
                    complete_bursts=len(lane['bursts']),actual_words=[len(b['beats']) for b in lane['bursts']],
                    discarded=len(lane['discarded'])) for name,lane in v['lanes'].items()}
    record=dict(state='PASS clean1280+observe1/native0 scoped fulltop integrity, exact full-line restoration and actual observation',
        source_build_commit=m['source_repositories'][0]['head'],BP=BP,r1_local_and_remote_tracking_preserved=R1,
        model=m['model'],actual_sources=m['actual_source_list'],geometry=g['observed'],
        integrity_trace=i['trace'],advisory_trace=a['trace'],advisory_evidence=lanes,
        actual_GP0_counts=c['firsttouch_counts'],counter_nonzero_event_edges=len(c['nonzero_event_edges']),
        observer_rising_edges=c['observed_rising_edges'],scope=m['scope'],
        actual_process_returncodes=dict(integrity=i['actual_returncode'],advisory=a['actual_returncode']),
        complete_execution='Both guest checks then CORE PASS, host RC0 and BSG PASS; actual exits-6 preserved as maintained-checker accepted post-PASS GPIO teardown only.',
        future_route_prerequisite='Parent-owned Vivado farm admission; actual fulltop retained instance and1280/1280/256/observe1/native0 effective geometry must be verified before interpreting route reports.',
        limits='Not global/library assertion acceptance, exhaustive fullcore use of1280 slots, physical use/fit/timing/maximum, or application/FPGA benefit. Named16KiB L2 differs from historical accepted4KiB route.',
        archive_script=bind(__file__),artifacts=artifacts)
    write(out/'verification.json',record)
    print(out/'verification.json',len(artifacts),'lossless archives')


if __name__=='__main__':main()
