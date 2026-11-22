"""Actual borrowing256 qualification; old trace1 proof cannot approve this model."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
SOURCE=Path('/home/coyang/zynq-parrot-linux-borrow256-profile')
POOL=Path('/run/user/1001/zp-retained-borrow256-trace0-fullcore-20261122-01')
COHORT=POOL/'allslots01'
NATIVE=POOL/'full01'
CLONE=POOL/'scoped-clone01'
DURABLE=Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow256-trace0-fullcore-20261122')
SCOPED=DURABLE/'scoped-closed01/archive.json'
SCOPED_SHA='91cf86e4d25e81c68e910e23f3e00057104611e4585b8cf5d6e9d39b11d30b1d'
MODEL_SHA='6a4214d9b03574d0d0f75ab210e7c91dc447897eba5bee465965370a3dc433e0'
FULL_SHA='ccd530d02b959ac6d5da98d7ad08310d4c65c77942724e9e6136473e86542f4b'
QUAL_SHA='31dd37473171f7f849238f3065cbc86a0fe14dae5145e471582817b88bbe51bf'
PREP=Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/retained-borrow256-trace0-preparation-20261122')
STRICT_SHA='53eaca9a63bb31efa5571b6eb12279e1779339d4d3821f50488e7846f19d5d21'


def require(ok,message):
    if not ok:raise ValueError(message)


def bind(path):
    p=Path(path).resolve();h=hashlib.sha256()
    with p.open('rb') as stream:
        for data in iter(lambda:stream.read(1024**2),b''):h.update(data)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def verify(row):
    require(bind(row['path'])=={k:row[k] for k in ('path','bytes','sha256')},'frozen bytes changed: '+row['path'])


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def read():
    require(bind(SCOPED)['sha256']==SCOPED_SHA,'exact ROOT scoped archive')
    arc=json.loads(SCOPED.read_text())
    for row in arc['proof_files']:verify(row)
    for key in ('qualified_rawFST','gzip','filtered_Syms'):verify(arc[key])
    verify(arc['original_lossless_archive']);require(arc['original_lossless_archive']['sha256']=='9918f125af54570e183d249d22eef995f8da1d826d4992fcf24e568721669c59','exact native full archive')
    require(bind(NATIVE/'session.json')['sha256']==FULL_SHA,'actual new fullcore11phase proof')
    full=json.loads((NATIVE/'session.json').read_text())
    require(full['state'].startswith('PASS borrow-only trace0 clean fullcore') and len(full['commands'])==11,'complete actual native fullcore, no historical approval')
    require(full['source_tree_baseline']=='1008854d30e5d923c86c3232fc22af039467d552' and full['source_bp']=='bb575a764c200f07c6f3259a179bdc861dd7593f','exact new common architecture')
    require(bind(CLONE/'qualify-supervision.json')['sha256']=='9444e4555a4f0b9224aef18a5a38b4f46e175ac1bf8d23bedbb9b8dace1ac963','actual owned qualification closure')
    require(bind(CLONE/'flow.json')['sha256']=='2757435fe9f5d9f3e20067fea60640456c27e13e50b5dc5dc21660b4ee876274','actual clone flow closure')
    path=CLONE/'qualification01/qualification.json';require(bind(path)['sha256']==QUAL_SHA,'exact complete five-domain qualification')
    q=json.loads(path.read_text());require(q['state']=='PASS-matched256-cold08-five-domain-literal-equivalence-strict-counter-geometry','whole actual clone qualification')
    for key in ('strict','observer','geometry'):verify(q[key])
    require(set(q['domains'])=={'core252','observer_and_geometry','SP_strict162','actual_geometry17','capacity167'},'five complete domains incl17constants')
    require(all(row['literal_bytes_equal'] is True for row in q['domains'].values()),'all full literal comparisons')
    p=json.loads((CLONE/'records/proposal.json').read_text());a=json.loads((CLONE/'records/admission.json').read_text())
    require(bind(CLONE/'records/admission.json')['sha256']=='09e82bed02a79db8a8226833f10be65563f97b49cb90ea3496de9c05848b11ed','exact separately reviewed clone admission')
    verify(a['proposal']);require(p['original_model']['sha256']=='695e53dccdf418dac6e40ec1c652752e82fb7187c834dbd689ac80233445a80c','no old1e9519 model inheritance')
    model=arc['model'];verify(model);require(model['sha256']==MODEL_SHA and Path(model['path'])==CLONE/'build/obj/Vbsg_nonsynth_zynq_testbench','fixed actually qualified scoped binary')
    verify(full['actual_source_list'])
    source=json.loads(Path(full['actual_source_list']['path']).read_text())['sources']
    normalized={path:{k:row[k] for k in ('path','bytes','sha256')} for path,row in source.items()}
    require(normalized==p['compiled_sources'],'all actual clone evaluation sources unchanged')
    for row in normalized.values():verify(row)
    strict=SOURCE/'testing/rtl/retained-advisory-trace/validate.py'
    require(bind(strict)['sha256']==STRICT_SHA,'unchanged actual literal-root checker bytes')
    checker=module(strict,'actual_borrow256_tool_root')
    require(checker.ROOT==SOURCE,'literal checker ROOT equals compiled source ROOT before reader')
    checker.source_bindings(Path(full['actual_source_list']['path']))
    geometry=json.loads(Path(q['geometry']['path']).read_text())['facts']['values']
    require(len(geometry)==17 and geometry['retained_store.storage.i_lines_p']==geometry['retained_store.storage.d_lines_p']==256 and geometry['core_minimal.cache_miss_trace_p']==0,'actual256 trace0 geometry')
    require(geometry['l2_banks_p']==2 and geometry['l2_sets_p']==64 and geometry['l2_assoc_p']==2 and geometry['l2_block_width_p']==512,'actual16KiB L2')
    for row in p['linked_libraries']:verify(row)
    return dict(archive=bind(SCOPED),native=bind(NATIVE/'session.json'),qualification=bind(path),model=model,
                compiled_sources=normalized,geometry=geometry,environment=p['environment'],linked_libraries=p['linked_libraries'],reader=p['reader'],
                scope='Source/observation correctness only; new complete all256 gates pending, no fit/FPGA/application claim.')
