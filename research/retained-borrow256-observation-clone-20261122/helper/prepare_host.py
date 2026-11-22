#!/usr/bin/env python3
"""ROOT-only collection and original closed-FST references, no compiler/target."""
import argparse
import copy
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
sys.dont_write_bytecode=True
from common import *
from canonical import extract
from protocol import parse
from host_flow import members,ADMISSION,STAGE,validate,HOME_CAP

INVENTORY=HERE.parent/'inventory.py'
spec=importlib.util.spec_from_file_location('frozen_closed_inventory',INVENTORY)
inv=importlib.util.module_from_spec(spec);spec.loader.exec_module(inv)
ARCHIVE=inv.ARCHIVE;ARCHIVE_SHA=inv.ARCHIVE_SHA
TOP='1008854d30e5d923c86c3232fc22af039467d552'
BP='bb575a764c200f07c6f3259a179bdc861dd7593f'
LINEAGE=inv.TEMPLATE.parent
from bounded import Guard,contracts


def home_guard():
    require(sum(p.stat().st_size for p in STAGE.rglob('*') if p.is_file())<=ARTIFACT_ALLOCATION,'combined256MiB stage')


def unique(commands,predicate,label):
    rows=[a for a in commands if predicate(a)];require(len(rows)==1,'unique actual '+label);return rows[0]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepare-only',required=True,action='store_true');ap.add_argument('--worker',required=True,action='store_true');ap.parse_args();require(os.getpgrp()==os.getpid(),'owned ROOT preparation worker')
    require(not ROOT.exists() and STAGE.is_dir(),'fresh records in owned parent-created stage only')
    require(bind(ARCHIVE)['sha256']==ARCHIVE_SHA,'actual accepted durable closure')
    archive=json.loads(ARCHIVE.read_text())
    inv.verify(archive['composite'])
    inventory_path=ORIGINAL.parent/'scoped-inventory01/session.json'
    require(bind(inventory_path)['sha256']=='fc7d7e4cf7b3f7b36d3a1322d0811d6d52c7527934539aa9c07891c5cdd266fa','exact ROOT closed actual415 inventory')
    inventory=json.loads(inventory_path.read_text())
    require(inventory['state']=='PASS exact415 actual path/widths; clone remains pending','actual new model415 inventory before preparation')
    inv.verify(inventory['plan']);inventory_plan=json.loads(inv.PLAN.read_text())
    require(inventory['trace']['sha256']=='9a5b6acc78717534976aa2c5fec249db0bf1293119498f11087270c933908100','same closed full advisory FST')
    producer=json.loads((ORIGINAL/'session.json').read_text())
    require(producer['source_tree_baseline']==TOP and producer['source_bp']==BP,'matched source pins')
    obj=Path(archive['model']['path']).parent
    require(obj==ORIGINAL/'verilator/obj_dir' and bind(obj/PREFIX)['sha256']==MODEL_SHA,'actual model/root namespace')
    # Preflight the literal script root before any FST reader can start.
    strict=SP/'testing/rtl/retained-advisory-trace/validate.py'
    spec=importlib.util.spec_from_file_location('literal_compiled_root_validator',strict)
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    require(checker.ROOT==SP and bind(strict)['sha256']=='53eaca9a63bb31efa5571b6eb12279e1779339d4d3821f50488e7846f19d5d21','exact literal tool-root before reader')
    checker.source_bindings(ORIGINAL/'actual-source-list.json')
    budget,_=contracts();full_budget=budget.check()
    require(full_budget['own_bytes']+ARTIFACT_ALLOCATION<=budget.OWN_CAP,'full clone256MiB inside existing768MiB')
    template=json.loads((LINEAGE/'proposal.json').read_text());old_a=json.loads((LINEAGE/'admission.json').read_text())
    require(bind(LINEAGE/'admission.json')['sha256']=='31300f4846bba35676c1579398242d39643544710d6c137d737a28a8b6e31f5c','exact accepted414 lineage')
    require(bind(LINEAGE/'proposal.json')==old_a['proposal'],'exact proposal bound by accepted414 lineage admission')
    commands=[shlex.split(line) for line in (ORIGINAL/'build.log').read_text().splitlines() if line.startswith('g++ ')]
    compile=unique(commands,lambda a:a[-1]==SYMS+'.cpp','Syms compile')
    pch=unique(commands,lambda a:a[-1]==PREFIX+'__pch.h.slow.gch','slow PCH')
    link=unique(commands,lambda a:'-o' in a and a[a.index('-o')+1]==PREFIX,'link')
    require(compile[-6:]==['-include',PREFIX+'__pch.h.slow','-c','-o',SYMS+'.o',SYMS+'.cpp'],'actual Syms shape')
    require(pch[:-5]==compile[:-6] and pch[-5:]==['-x','c++-header',PREFIX+'__pch.h','-o',PREFIX+'__pch.h.slow.gch'],'same PCH/compile prefix')
    mapped=compile.copy();mapped[-5]=PREFIX+'__pch.h'
    host=['ps.o','main.o','bsg_nonsynth_dpi_clock_gen.o','verilated.o','verilated_dpi.o','verilated_fst_c.o','verilated_threads.o']
    require([v for v in link if v.endswith(('.o','.a'))]==host+[PREFIX+'__ALL.a'],'exact unchanged seven-host-object link order')
    names=set(host+[PREFIX,PREFIX+'__ALL.a',SYMS+'.cpp',SYMS+'.o',SYMS+'.d'])
    names.update(p.name for p in obj.glob('*.h'))
    required={name:bind(obj/name) for name in sorted(names)}
    require(sum(r['bytes'] for r in required.values())<=64*1024**2,'copy64MiB preflight, PCH excluded')
    object_inventory=tree(obj)
    compiled={name:bind(name) for name in json.loads((ORIGINAL/'actual-source-list.json').read_text())['sources']}
    stamp=list(obj.glob('.build_config-*'));require(len(stamp)==1,'one exact stamp')
    trace=ORIGINAL/'advisory/trace.fst';reader=template['reader'];verify(reader)
    inv.verify(inventory['hierarchy']);listing=Path(inventory['hierarchy']['path']).read_text()
    require(listing.rstrip().endswith('#END'),'full hierarchy EOF')
    declared={}
    for line in listing.splitlines():
        if line.startswith('#VAR\t'):
            _,width,handle,name=line.split('\t');require(name not in declared,'duplicate actual leaf');declared[name]=int(width)
    domains=copy.deepcopy(inventory_plan['domains'])
    for part in domains.values():
        for leaf in part:require(declared.get(leaf['path'])==leaf['width'],'literal required leaf/width '+leaf['path'])
    union={r['path']:r for part in domains.values() for r in part}
    require(len(union)==415 and any(k.endswith('.dcache_retained_maintenance_v') for k in union),'exact414 union including raw maintenance')
    ROOT.mkdir();(ROOT/'original-hierarchy.tsv.gz').write_bytes(gzip.compress(listing.encode(),mtime=0))
    # Parse the already executed ldd output rather than silently changing the
    # original loader environment. Build/qualify later independently recheck.
    ld=(ORIGINAL/'loader.log').read_text();require('not found' not in ld,'closed original loader')
    libraries=[bind(x) for line in ld.splitlines() for x in line.split() if x.startswith('/') and Path(x).is_file()]
    require(libraries,'actual loaded libraries')
    stat=ORIGINAL.stat()
    p=dict(state='PREPARED-matched256-host-observation-clone-NO-build-target',original_model=bind(obj/PREFIX),original_root=str(obj),original_inventory=object_inventory,
        required_copy=required,copy_bytes=sum(r['bytes'] for r in required.values()),compiled_sources=compiled,archive_members=members(obj/(PREFIX+'__ALL.a')),
        compile_argv=mapped,original_compile_argv=compile,PCH_creation_argv=pch,link_argv=link,domains=domains,
        writer_leaves=[union[k] for k in sorted(union)],reader=reader,environment=dict(LD_LIBRARY_PATH=producer['environment']['LD_LIBRARY_PATH']),
        linked_libraries=libraries,tools={n:bind(shutil.which(n)) for n in ('g++','ar','ldd')},model_stamp=bind(stamp[0]),runtime_sources=template['runtime_sources'],original_session=bind(ORIGINAL/'session.json'),
        original_build_log=bind(ORIGINAL/'build.log'),previous_accepted_plan=bind(LINEAGE/'admission.json'),namespace_sentinel=str(ORIGINAL),
        namespace_identity=dict(device=stat.st_dev,inode=stat.st_ino),original_TOP=TOP,original_BP=BP,fullcore_closure=bind(ARCHIVE),
        original_hierarchy=bind(ROOT/'original-hierarchy.tsv.gz'),capacity_schema=template['capacity_schema'],capacity_sources=template['capacity_sources'],
        scope='Trace registration only on actual borrowing256695e trace0 model. No RTL/evaluation/program change or all-slot/FPGA/application claim.',combined_resource_preflight=full_budget)
    for row in [*p['runtime_sources'].values(),p['capacity_schema'],*p['capacity_sources']]:verify(row)
    save(PROPOSAL,p)
    (ROOT/'required-leaves.tsv').write_text(''.join(str(r['width'])+'\t'+r['path']+'\n' for r in p['writer_leaves']))
    canonical={}
    for name,part in domains.items():
        canonical[name]=extract(reader['path'],trace,part,ROOT/('preflight-original-'+name),False)
    save(ROOT/'real-preflight.json',dict(state='PASS-borrow256-415leaves-five-complete-literal-domains',domains=canonical,proposal=bind(PROPOSAL)))
    reference={k:bind(ORIGINAL/'advisory'/n) for k,n in [('elf','prog.riscv'),('nbf','prog.nbf')]}
    process=json.loads((ORIGINAL/'advisory/process.json').read_text());text=(ORIGINAL/'advisory/run.log').read_text()
    reference.update(trace=bind(trace),returncode=process['returncode'],guest=parse(text,process['returncode']),
                     actual_geometry=json.loads((ORIGINAL/'parameters01/verification.json').read_text())['facts']['values'])
    inputs={str(x):bind(x) for x in [*HERE.glob('*.py'),INVENTORY,inv.PLAN,inventory_path,inv.PAIR,PROPOSAL,ROOT/'required-leaves.tsv',ROOT/'real-preflight.json',ARCHIVE,
             strict,SP/'testing/check_run.py',OLD_SOURCE/'research/retained-use-observation-20261121/build_full.py',
             OLD_SOURCE/'research/retained-use-observation-20261121/verify_counters.py',GEOMETRY_TOOL,Path(old_a['fixture_manifest']['path']),
             inv.QUALIFIED,*inv.PREP.glob('*.py')]}
    fixture=json.loads(Path(old_a['fixture_manifest']['path']).read_text())
    for row in [fixture['source'],fixture['elf'],p['capacity_schema'],*p['capacity_sources'],*(r['canonical_file'] for r in canonical.values())]:inputs[row['path']]=row
    a=dict(schema='borrow256-trace0-observation-only-host-admission-v1',state='FROZEN-PREPARED-HOLD-root-build-target-review',proposal=bind(PROPOSAL),stage=str(STAGE),inputs=inputs,
        PCH_inventory={x.name:bind(x) for x in obj.glob('*.gch')},budget=dict(stage_bytes=ARTIFACT_ALLOCATION,minimum_free_plus_remaining=RESERVE,
            home_bytes=HOME_CAP,native_seconds=180,host_seconds=360,FST_bytes=CAP,reader_seconds_per_domain=600,canonical_bytes_per_file=50*1024**2,attempts=1),
        fixture_manifest=old_a['fixture_manifest'],reference=reference,original_canonical=canonical,scope=p['scope'])
    save(ADMISSION,a);validate(a);home_guard()
    save(ROOT/'prepared-handoff.json',dict(state='PREPARED no clone/compiler/native',admission=bind(ADMISSION),proposal=bind(PROPOSAL),copy_bytes=p['copy_bytes']))
    print(ROOT/'prepared-handoff.json',bind(ADMISSION)['sha256'])


if __name__=='__main__':main()
