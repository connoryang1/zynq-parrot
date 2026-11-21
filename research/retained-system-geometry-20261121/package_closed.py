#!/usr/bin/env python3
"""Archive only closed proof from existing artifacts; never runs a model."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from run_isolated import artifact,TOP

HERE=Path(__file__).resolve().parent


def main():
    closure=HERE/'closure';closure.mkdir(exist_ok=False)
    integrity=HERE/'full-system1280-native0-03-runtime01/session.json';i=json.loads(integrity.read_text())
    advisory=HERE/'full-system1280-cold08-native0-01/session.json';a=json.loads(advisory.read_text())
    audit=HERE/'scaled-advisory-trace-audit01/verification.json';v=json.loads(audit.read_text())
    geom=HERE/'integrity-geometry-audit01/verification.json';g=json.loads(geom.read_text())
    if i['state']!='PASS-complete-checked-system-1280-native0-scoped-assertions' or not v['accepted'] or g['state']!='PASS-closed-geometry-and-selected-reader-EOF':raise ValueError('closed acceptance absent')
    if i['executable']!=a['executable'] or a['trace']!=v['bindings']['fst']:raise ValueError('advisory model/trace binding')
    build=json.loads(Path(i['build_session']['path']).read_text())
    for binding in build['sources_before'].values():
        if artifact(binding['path'])!=binding:raise ValueError('source changed')
    artifacts={}
    def keep(name,path,compressed=True):
        path=Path(path);raw=path.read_bytes();dest=closure/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if compressed:
            with dest.open('wb') as f:
                with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0,compresslevel=6) as z:z.write(raw)
            if gzip.decompress(dest.read_bytes())!=raw:raise ValueError('archive roundtrip')
        else:dest.write_bytes(raw)
        artifacts[name]=dict(source=artifact(path),archive=artifact(dest),gzip=compressed)
    for case in ('01','02','03'):
        base=HERE/('full-system1280-native0-'+case)
        for f in ('session.json','build.log','compile.log'):
            keep('attempt'+case+'-'+f+'.gz',base/f)
    for f in ('nbf.log','run.log','checker.log'):
        keep('attempt03-'+f+'.gz',HERE/'full-system1280-native0-03'/f)
    keep('failed-initial-top_zynq.sv.gz',HERE/'full-system1280-native0-01/source/failed-top_zynq.sv')
    keep('actual-source-list.json.gz',HERE/'full-system1280-native0-03/actual-source-list.json')
    model=Path(i['executable']['path']);keep('model.gz',model)
    keep('verFiles.dat.gz',model.parent/'Vbsg_nonsynth_zynq_testbench__verFiles.dat')
    for f in ('bsg_blackparrot_pkg.sv','bsg_bootrom.sv'):
        keep(f+'.gz',model.parent.parent/f)
    for tag,base in [('integrity',integrity.parent),('advisory',advisory.parent)]:
        for f in ('session.json','run.log','checker.log'):
            keep(tag+'-'+f+'.gz',base/f)
        for f in ('run_isolated.py','run_closed_model.py' if tag=='integrity' else 'run_advisory.py'):
            keep(tag+'-source/'+f,base/'source'/f,False)
    for name,path in [('legacy64.riscv.gz',HERE/'legacy-64.riscv'),('integrity-prog.riscv.gz',i['elf']['path']),('integrity-prog.nbf.gz',i['nbf']['path']),('advisory-prog.riscv.gz',a['elf']['path']),('advisory-prog.nbf.gz',a['nbf']['path'])]:keep(name,path)
    keep('geometry-verification.json',geom,False)
    keep('geometry-selected-events.tsv.gz',geom.parent/'selected-events.tsv')
    keep('geometry-selection.tsv',geom.parent/'selection.tsv',False)
    keep('advisory-verification.json',audit,False)
    keep('advisory-selected-events.tsv.gz',audit.parent/'selected-events.tsv.gz',False)
    keep('advisory-selection.tsv',audit.parent/'selection.tsv',False)
    for name in ('fst_events.build.json','fst_events.build.log'):
        keep('reader-'+name,HERE/'reader'/name,False)
    for path in (TOP/'testing/rtl/retained-advisory-trace/validate.py',TOP/'testing/rtl/retained-advisory-trace/fst_events.c',TOP/'testing/rtl/retained-advisory-trace/build_reader.py',TOP/'testing/check_run.py',TOP/'testing/rtl/scoped-assertions/bsg_clkgate_optional.sv',TOP/'testing/rtl/large_retained_system_test.c',TOP/'testing/Makefile'):
        keep('source/'+('testing-Makefile' if path.name=='Makefile' else path.name),path,False)
    lanes={k:dict(publications=len(s['publications']),hits=len(s['hits']),complete_bursts=len(s['bursts']),beat_words=[len(b['beats']) for b in s['bursts']],discarded=len(s['discarded']),active=s['active']) for k,s in v['lanes'].items()}
    record=dict(state='PASS-complete-integrity-and-scaled-advisory',scope=i['scope'],geometry=g['observed'],legacy_reproduction=artifact(HERE/'legacy-reproduction.json'),model=i['executable'],integrity_elf=i['elf'],integrity_nbf=i['nbf'],integrity_trace=i['trace'],advisory_elf=a['elf'],advisory_nbf=a['nbf'],advisory_trace=a['trace'],advisory_evidence=lanes,
                complete_execution='Both guest fixtures then CORE PASS and host RC0/BSG PASS; maintained checker accepts only documented post-PASS GPIO teardown failure. Integrity post-init assertions restored1. Raw process signal -6 is preserved, not described as clean process exit.',
                exclusions='Not exhaustive use of all1280 slots in full-core (component gates cover payload capacity). Not global/library assertion acceptance, routed fit, application performance, or FPGA evidence.',
                package_source=artifact(__file__),artifacts=artifacts)
    (closure/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print('PASS package',len(artifacts),'artifacts',sum(v['archive']['bytes'] for v in artifacts.values()),'bytes')

if __name__=='__main__':main()
