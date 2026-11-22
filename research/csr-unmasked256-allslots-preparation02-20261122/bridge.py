"""New CSR9c69/947 observation lineage; no old hardware approvals transfer."""
import hashlib,importlib.util,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
POOL=Path('/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01')
SOURCE=POOL/'source'
COHORT=POOL/'all256-csr01'
NATIVE=POOL/'full01'
CLONE=POOL/'scoped-csr01'
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fullcore-20261122')
DELTA=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-capacity-20261122')
PREP=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fullcore-preparation-20261122/preparation02')
OTHER_HELPERS=(PREP.parent,HERE.with_name('csr-unmasked256-observation-preparation-20261122'),HERE.with_name('csr-unmasked256-regression-preparation-20261122'),HERE.with_name('csr-unmasked256-allslots-preparation-20261122'))
ORIGINAL_SHA='9c69a2f83539ca7a3f2c74c3be0502dbbf929d09ea95f1d75bfd2bd7172fc1fd'
PREFIX='Vbsg_nonsynth_zynq_testbench'


def require(v,m):
    if not v:raise ValueError(m)


def bind(p):
    p=Path(p).resolve();h=hashlib.sha256()
    with p.open('rb') as f:
        for raw in iter(lambda:f.read(1024**2),b''):h.update(raw)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def verify(row):require(bind(row['path'])=={k:row[k]for k in ('path','bytes','sha256')},'frozen input changed '+row['path'])


def read(authority_row):
    verify(authority_row);a=json.loads(Path(authority_row['path']).read_text())
    require(a['schema']=='csr256-allslots-root-authority-v1' and a['ROOT_approved'] is True,'DRAFT no model/resource approval')
    require(a['source_plan']==bind(HERE/'source-plan.json'),'exact new source contract')
    verify(a['base_closure']);require(a['base_closure_reviewed_complete'] is True,'base32MiB all-member closure first')
    anchors=a['anchors']
    expected=dict(full=NATIVE/'session.json',supervision=CLONE/'qualify-supervision.json',flow=CLONE/'flow.json',qualification=CLONE/'qualification01/qualification.json',build=CLONE/'build/evidence/build.json',clone_admission=CLONE/'records/admission.json',std_supervision=CLONE/'architectural-regressions-supervision.json',std=CLONE/'architectural-regressions01/session.json')
    require(set(anchors)==set(expected),'all actual new full/clone/STD closure anchors')
    for key,path in expected.items():require(anchors[key]['path']==str(path),'fixed actual receipt '+key);verify(anchors[key])
    full=json.loads((NATIVE/'session.json').read_text())
    require(full['state'].startswith('PASS CSR unmasked256') and len(full['commands'])==11,'complete actual new fullcore')
    require(full['source_tree_baseline']=='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd' and full['source_bp']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','new exact source profile')
    require(full['model']['sha256']==ORIGINAL_SHA,'new full9c69, never695/6a')
    for key in ('supervision','std_supervision'):
        x=json.loads(Path(anchors[key]['path']).read_text());life=x['ownership']
        require(x['state'].startswith('PASS') and life['returncode']==0 and life['owned_group_remaining'] is False,'actual owned phase closure '+key)
    flow=json.loads((CLONE/'flow.json').read_text());require(flow['state']=='PASS-one-new-CSR-unmasked256-observation-qualification','new complete observation flow')
    verify(flow['build']);verify(flow['qualification'])
    require(flow['build']==anchors['build'] and flow['qualification']==anchors['qualification'],'same closed flow proofs')
    b=json.loads((CLONE/'build/evidence/build.json').read_text());model=b['binary'];verify(model)
    require(Path(model['path'])==CLONE/'build/obj'/PREFIX and a['model']==model,'ROOT actual new scoped model hash')
    require(b['original_model']['sha256']==b['baseline_relink']['sha256']==ORIGINAL_SHA,'untouched relink reproduced9c69')
    require(set(b['original_members'])==set(b['final_members']) and [k for k in b['original_members']if b['original_members'][k]!=b['final_members'][k]]==[PREFIX+'__Syms.o'],'Syms-only member change')
    mandatory={PREFIX,PREFIX+'__ALL.a',PREFIX+'__Syms.cpp',PREFIX+'__Syms.o'}
    require(mandatory<=set(b['changed_files'])<=mandatory|{PREFIX+'__Syms.d'},'four required trace/compiler products, optional unchanged dependency file only')
    q=json.loads((CLONE/'qualification01/qualification.json').read_text())
    require(q['state']=='PASS-matched256-cold08-five-domain-literal-equivalence-strict-counter-geometry','new full qualification')
    require(set(q['domains'])=={'core252','observer_and_geometry','SP_strict162','capacity167','actual_geometry17'},'all five actual domains')
    for d in q['domains'].values():
        require(d['literal_bytes_equal'] is True,'complete literal stream equality')
        for key in ('sha256','events','changes_by_index','first_tick','final_tick','timescale','clean_EOF'):require(d['reference'][key]==d['clone'][key],'whole domain summary '+key)
    for key in ('strict','observer','geometry'):verify(q[key])
    require(json.loads(Path(q['strict']['path']).read_text())['accepted'] is True,'actual strict all512/eightwrites/16I')
    require(json.loads(Path(q['observer']['path']).read_text())['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'actual observer transition proof')
    geo=json.loads(Path(q['geometry']['path']).read_text())['facts']['values']
    require(len(geo)==17 and geo['retained_store.storage.i_lines_p']==geo['retained_store.storage.d_lines_p']==256 and geo['retained_store.storage.sets_p']==256 and geo['retained_store.storage.epoch_width_p']==8 and geo['core_minimal.cache_miss_trace_p']==0,'actual256/256sets/epoch8/trace0')
    require(geo['icache_sets_p']==geo['dcache_sets_p']==64 and geo['icache_assoc_p']==geo['dcache_assoc_p']==8 and geo['icache_block_width_p']==geo['dcache_block_width_p']==512 and geo['l2_banks_p']==2 and geo['l2_sets_p']==64 and geo['l2_assoc_p']==2 and geo['l2_block_width_p']==512,'unchanged32KiB L1s/static16KiB L2')
    std=json.loads(Path(anchors['std']['path']).read_text())
    require(std['state']=='PASS four unchanged architectural tests on new CSR-unmasked qualified model; no performance claim' and [r['test']for r in std['tests']]==['mt_context_csr_rebind_test','mt_umode_nonresident_sv39_data_handoff_test','mt_resident_reseed_irq_test','mt_protected_rpc_hardware_test'],'all four new-model architectural tests')
    require(std['model']==model,'same qualified executable in all stdtests')
    p=json.loads((CLONE/'records/proposal.json').read_text());ad=json.loads((CLONE/'records/admission.json').read_text());verify(ad['proposal'])
    require(p['original_model']['sha256']==ORIGINAL_SHA,'same observation input model')
    verify(full['actual_source_list']);raw=json.loads(Path(full['actual_source_list']['path']).read_text())['sources']
    compiled={k:{f:v[f]for f in ('path','bytes','sha256')}for k,v in raw.items()}
    require(compiled==p['compiled_sources'],'every actual compiled evaluation source unchanged')
    for row in compiled.values():verify(row)
    for suffix,wanted in [('bp_be_csr_snapshot_store_production.sv','e5a1518bd6a587157e73895c2e962dd467438e2c25565ea3223d2fb259e5f805'),('integration-contract.sv','1754071b0512ab5974219a7c9c7d0d834e20ec008405388b16efeeed3f17b3ec')]:
        rows=[r for path,r in compiled.items()if path.endswith('/'+suffix)];require(len(rows)==1 and rows[0]['sha256']==wanted,'actual new store/ghost')
    strict=SOURCE/'testing/rtl/retained-advisory-trace/validate.py';verify(next(r for r in ad['inputs'].values()if r['path']==str(strict)))
    spec=importlib.util.spec_from_file_location('new_csr_literal_tool_root',strict);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);require(mod.ROOT==SOURCE,'actual new literal toolROOT');mod.source_bindings(Path(full['actual_source_list']['path']))
    reader=p['reader'];require(reader==dict(path='/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121/fst-reader/fst_events',bytes=151200,sha256='a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541'),'exact actual reader');verify(reader)
    for row in p['linked_libraries']:verify(row)
    return dict(archive=a['base_closure'],native=anchors['full'],qualification=anchors['qualification'],model=model,compiled_sources=compiled,geometry=geo,environment=p['environment'],linked_libraries=p['linked_libraries'],reader=reader,ROOT_authority=authority_row,scope='New model/source synthetic correctness only; all256 payload gates still pending, no hardware/application claim')
