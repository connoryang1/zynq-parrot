#!/usr/bin/env python3
"""ROOT-only closed actual new768 model collection; no compiler or target here."""
import argparse,copy,gzip,importlib.util,json,os,resource,shlex,shutil,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
from common import *
from canonical import extract
from protocol import parse
from host_flow import members,ADMISSION,validate
from bounded import Guard

TOP='1b24c915ed628f6d47a382b3aa89fb662884e1a1'
BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
LINEAGE=Path('/home/coyang/fpga-artifacts/context-resume/retained-canonical-scoped-20261121')


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepare-only',required=True,action='store_true');ap.add_argument('--worker',required=True,action='store_true');ap.add_argument('--fullcore-sha',required=True);args=ap.parse_args()
    require(os.getpgrp()==os.getpid(),'owned ROOT preparation worker')
    require(not ROOT.exists() and STAGE.is_dir(),'fresh records only')
    session=BUILD/'session.json';require(bind(session)['sha256']==args.fullcore_sha,'externally trusted actual768 clean fullcore SHA')
    accepted=producer()
    require(json.loads(Path(accepted['closed_audits']['strict']['path']).read_text())['accepted'] is True,'actual new strict result')
    require(json.loads(Path(accepted['closed_audits']['counter']['path']).read_text())['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'actual new counter result')
    obj=BUILD/'verilator/obj_dir';model=obj/PREFIX
    require(bind(model)['sha256']==MODEL_SHA and accepted['model']['sha256']==MODEL_SHA,'actual ROOT-bound new768 model')
    actual=json.loads(Path(accepted['actual_source_list']['path']).read_text())
    compiled={path:bind(path) for path in actual['sources']}
    for path,row in compiled.items():
        require(row['sha256']==actual['sources'][path]['sha256'],'new actual ingested source drift')
    store=SP/'import/black-parrot/bp_be/src/v/bp_be_csr_snapshot_store_production.sv'
    top=SP/'import/black-parrot/bp_be/src/v/bp_be_top.sv'
    ghost=Path('/home/coyang/zynq-parrot-linux-capacity/research/csr-unmasked-integration-preparation-20261122/integration-contract.sv')
    for path,wanted in [(store,'e5a1518bd6a587157e73895c2e962dd467438e2c25565ea3223d2fb259e5f805'),(top,'96915d9ea91370349975b758b862eddd031e8f44e961c224e69dddf5a115a79c'),(ghost,'1754071b0512ab5974219a7c9c7d0d834e20ec008405388b16efeeed3f17b3ec')]:
        require(str(path) in compiled and compiled[str(path)]['sha256']==wanted,'new store/top/ghost actually ingested')
    rawmeta=(obj/(PREFIX+'__verFiles.dat')).read_text();command=next(x for x in rawmeta.splitlines() if x.startswith('C '))
    require('--assert' in command and str(ghost) in command,'actual parsed ghost/assert command')
    require(any('CSR integration valid full1666 image differs from reference' in p.read_text() for p in obj.glob('*.cpp')),'actual generated full-image ghost assertion')
    strict=SP/'testing/rtl/retained-advisory-trace/validate.py';checker=module(strict,'new_literal_strict_root')
    require(checker.ROOT==SP and bind(strict)['sha256']=='53eaca9a63bb31efa5571b6eb12279e1779339d4d3821f50488e7846f19d5d21','literal new checker root before readers')
    checker.source_bindings(Path(accepted['actual_source_list']['path']))
    old=json.loads((LINEAGE/'admission.json').read_text());template=json.loads((LINEAGE/'proposal.json').read_text())
    require(bind(LINEAGE/'admission.json')['sha256']=='31300f4846bba35676c1579398242d39643544710d6c137d737a28a8b6e31f5c','qualified recipe lineage only')
    require(bind(LINEAGE/'proposal.json')==old['proposal'],'old recipe not new-model approval')
    reader=template['reader'];verify(reader);require(reader['sha256']=='a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541','actual reader bytes')
    parts=json.loads(gzip.decompress((HERE.parent/'domains.json.gz').read_bytes()))
    union={r['path']:r for rows in parts.values() for r in rows}
    require(len(union)==415 and {k:len(v) for k,v in parts.items()}==dict(core252=252,observer_and_geometry=45,SP_strict162=162,actual_geometry17=17,capacity167=167),'unchanged exact415/five domains')
    log=(BUILD/'build.log').read_text();commands=[shlex.split(x) for x in log.splitlines() if x.startswith('g++ ')]
    comp=[a for a in commands if a[-1]==SYMS+'.cpp'];link=[a for a in commands if '-o' in a and a[a.index('-o')+1]==PREFIX]
    require(len(comp)==len(link)==1,'one actual Syms compile/link');comp=comp[0];link=link[0]
    require(comp[-4:]==['-c','-o',SYMS+'.o',SYMS+'.cpp'] and not any('.gch' in a or '__pch.h.slow' in a for a in comp),'actual no-PCH textual header compile')
    require(not list(obj.glob('*.gch')),'no copied/generated PCH')
    host=['ps.o','main.o','bsg_nonsynth_dpi_clock_gen.o','verilated.o','verilated_dpi.o','verilated_fst_c.o','verilated_threads.o']
    require([a for a in link if a.endswith(('.o','.a'))]==host+[PREFIX+'__ALL.a'],'actual unchanged ps/main link order')
    names=set(host+[PREFIX,PREFIX+'__ALL.a',SYMS+'.cpp',SYMS+'.o',SYMS+'.d']);names.update(p.name for p in obj.glob('*.h'))
    required={name:bind(obj/name) for name in sorted(names)};require(sum(x['bytes'] for x in required.values())<=64*1024**2,'copy64MiB cap')
    guard=Guard(3600);guard();ROOT.mkdir()
    # First actual new path/width inventory. It is not inherited from old695/6a.
    with (ROOT/'original-hierarchy.tsv').open('x') as f:
        argv=[reader['path'],str(ORIGINAL/'advisory/trace.fst'),'--list']
        def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024**2,20*1024**2))
        # Same outer owned phase PG, never an escaping nested child session.
        child=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,preexec_fn=limit)
        try:rc=child.wait(timeout=60)
        finally:
            if child.poll() is None:child.kill();child.wait()
        life=dict(argv=argv,returncode=rc,seconds_limit=60,owning_group='outer ROOT preparation phase',output_cap=20*1024**2)
    require(life['returncode']==0,'actual new hierarchy reader return')
    listing=(ROOT/'original-hierarchy.tsv').read_text();require(listing.rstrip().endswith('#END'),'complete hierarchy EOF')
    declared={}
    for line in listing.splitlines():
        if line.startswith('#VAR\t'):
            _,width,handle,path=line.split('\t');require(path not in declared,'unique hierarchy');declared[path]=int(width)
    for path,row in union.items():require(declared.get(path)==row['width'],'new actual required leaf/width '+path)
    (ROOT/'original-hierarchy.tsv.gz').write_bytes(gzip.compress(listing.encode(),mtime=0))
    libraries=[bind(x) for line in (BUILD/'loader.log').read_text().splitlines() for x in line.split() if x.startswith('/') and Path(x).is_file()]
    require(libraries,'actual loader libraries');stamp=list(obj.glob('.build_config-*'));require(len(stamp)==1,'actual single model stamp')
    stat=ORIGINAL.stat()
    proposal=dict(actual_source_list=accepted['actual_source_list'],inherited_cleanbuild=bind(BUILD/'session.json'),state='PREPARED new CSR768 ROOT-bound observation clone; no compiler/native',original_model=bind(model),original_root=str(obj),original_inventory=tree(obj),required_copy=required,copy_bytes=sum(x['bytes'] for x in required.values()),compiled_sources=compiled,archive_members=members(obj/(PREFIX+'__ALL.a')),compile_argv=comp,original_compile_argv=comp,link_argv=link,domains=parts,writer_leaves=[union[k] for k in sorted(union)],reader=reader,environment=dict(LD_LIBRARY_PATH=accepted['environment']['LD_LIBRARY_PATH']),linked_libraries=libraries,tools={n:bind(shutil.which(n)) for n in ('g++','ar','ldd')},model_stamp=bind(stamp[0]),runtime_sources=template['runtime_sources'],original_session=bind(session),original_build_log=bind(BUILD/'build.log'),namespace_identity=dict(device=stat.st_dev,inode=stat.st_ino),original_TOP=TOP,original_BP=BP,fullcore_producer=bind(session),capacity_schema=template['capacity_schema'],capacity_sources=template['capacity_sources'],ghost=bind(ghost),store=bind(store),scope='New768 ROOT-bound Syms trace-registration only; evaluation/ghost/program unchanged; no all-slot/FPGA/application claim')
    save(PROPOSAL,proposal)
    canonical={name:extract(reader['path'],ORIGINAL/'advisory/trace.fst',part,ROOT/('original-'+name),False) for name,part in parts.items()}
    reference={k:bind(ORIGINAL/'advisory'/n) for k,n in [('elf','prog.riscv'),('nbf','prog.nbf')]}
    rc=json.loads((ORIGINAL/'advisory/process.json').read_text())['returncode']
    reference.update(trace=bind(ORIGINAL/'advisory/trace.fst'),returncode=rc,guest=parse((ORIGINAL/'advisory/run.log').read_text(),rc),actual_geometry=json.loads(Path(accepted['closed_audits']['parameters']['path']).read_text())['facts']['values'])
    inputs={str(p):bind(p) for p in [*HERE.glob('*.py'),HERE.parent/'domains.json.gz',HERE.parent/'preparation-source.json',MODEL_INPUT,PROPOSAL,strict,SP/'testing/check_run.py',OLD_SOURCE/'research/retained-use-observation-20261121/build_full.py',OLD_SOURCE/'research/retained-use-observation-20261121/verify_counters.py',GEOMETRY_TOOL,Path(old['fixture_manifest']['path'])]}
    for row in [*proposal['runtime_sources'].values(),proposal['capacity_schema'],*proposal['capacity_sources'],*(x['canonical_file'] for x in canonical.values())]:verify(row);inputs[row['path']]=row
    a=dict(schema='csr768-observation-only-host-admission-v1',state='FROZEN PREPARED pending separate ROOT clone approval',proposal=bind(PROPOSAL),stage=str(STAGE),inputs=inputs,PCH_inventory={},budget=dict(stage_bytes=ARTIFACT_ALLOCATION,minimum_free_plus_remaining=RESERVE,home_bytes=32*1024**2,native_seconds=180,host_seconds=360,FST_bytes=CAP,reader_seconds_per_domain=600,canonical_bytes_per_file=50*1024**2,attempts=1),fixture_manifest=old['fixture_manifest'],reference=reference,original_canonical=canonical,scope=proposal['scope'])
    save(ADMISSION,a);validate(a);guard.finish();save(ROOT/'prepared-handoff.json',dict(state='PREPARED actual new415/five full references; clone build/native pending',admission=bind(ADMISSION),proposal=bind(PROPOSAL),copy_bytes=proposal['copy_bytes'],hierarchy_reader=life))
    print(ADMISSION,bind(ADMISSION)['sha256'])


if __name__=='__main__':main()
