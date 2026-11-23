"""Pure semantic geometry adapter; no lifecycle, stream I/O, or run authority."""
from collections import namedtuple
import hashlib
import importlib.util
import json
from pathlib import Path
from types import MappingProxyType
from csr1280_support import require
from csr1280_methods import SingleMethods,LaneMethods,JointMethods
from csr1280_parser import edges

HERE=Path(__file__).resolve().parent
Geometry=namedtuple('Geometry','lines sets')
ROLES=('d-enabled','d-off','i-enabled','i-off')


def geometry(lines,sets=256):
    require(type(lines) is int and lines in (256,1280) and type(sets) is int and sets==256,'explicit control256 or candidate1280, same256sets')
    return Geometry(lines,sets)


def expected_counters(profile,role):
    require(role in (*ROLES,'joint'),'explicit single/joint role')
    n=profile.lines
    return [n,n,n,n,8*n,8*n] if role=='joint' else [n,0,n,0,8*n,0] if role=='i-enabled' else [0,n,0,n,0,8*n] if role=='d-enabled' else [0]*6


def target_index(slot,sets):
    # At256 this reduces exactly to the established first-way constructor.
    # At1280 retain the way bits, covering five complete ways, no address search.
    return (slot&~(sets-1))+((slot*0xaaaaaaaaaaaaaaab)&(sets-1))


def targets(program,lane,profile,generator):
    require(profile==geometry(profile.lines,profile.sets),'validated explicit geometry')
    require(lane in ('i','d') and program['max_lines']==1792 and program['max_sets']==256,'unchanged bounded payload generator/program')
    require(profile.lines<=program['max_lines'] and program['code_stride']==192,'actual target layout bound')
    result={}
    for slot in range(profile.lines):
        index=target_index(slot,profile.sets)
        address=program['code_base']+192*index if lane=='i' else program['data_base']+64*slot
        require(address not in result,'unique target address')
        result[address]=dict(slot=slot,index=index,words=generator.code_words(index) if lane=='i' else generator.data_words(slot))
    return result


def _lane_fields(obj,program,role,profile,context,mode):
    require(role in ROLES,'declared role')
    kind='joint' if mode==3 else 'single'
    bound=context.anchors['programs'][kind]['manifest'];_verify(bound)
    require(program==json.loads(Path(bound['path']).read_text()),'unchanged exact program manifest; geometry is separate')
    obj.program=program;obj.lane=role[0];obj.active=role.endswith('enabled');obj.mode=mode
    obj.profile=profile;obj.lines=profile.lines;obj.sets=profile.sets
    obj.targets=targets(program,obj.lane,profile,context.generator)
    obj.marked={};obj.inflight=None;obj.lookup=None
    obj.actual_pub={};obj.actual_hit={};obj.retained={};obj.normal={};obj.burst=None
    obj.retired={};obj.d_load_retirements=0;obj.last_values=None;obj.target_mem_before_pub=[]
    obj.reset=context.strict.Validator({'i':[0]*8,'d':[0]*8},{})
    obj.markers={name:program['symbols']['retained_capacity_'+obj.lane+'_'+name]['address'] for name in ('populate_begin','verify_begin','verified')}
    obj.d_begin=program['symbols']['retained_capacity_d_populate_begin']['address']
    obj.d_end=program['symbols']['retained_capacity_d_verified']['address']


class SingleValidator(SingleMethods):
    def __init__(self,program,role,profile,context):
        mode=(1 if role[0]=='i' else 2) if role.endswith('enabled') else 0
        _lane_fields(self,program,role,profile,context,mode)
        self.role=role


class LaneValidator(LaneMethods):
    def __init__(self,program,lane,profile,context):
        _lane_fields(self,program,lane+'-enabled',profile,context,3)


class JointValidator(JointMethods):
    def __init__(self,program,profile,context):
        require(program['joint_schema']=='retained-joint-capacity-program-v1','exact joint program manifest; do not rewrite its old256 metadata')
        require(program['max_lines']==1792 and program['max_sets']==profile.sets==256,'unchanged joint software upper bounds')
        self.program=program;self.profile=profile
        self.lanes={lane:LaneValidator(program,lane,profile,context) for lane in ('i','d')}
        self.markers={key:program['symbols']['retained_capacity_'+key]['address'] for key in ('i_populated','joint_populated','joint_verified')}
        self.marked={};self.call=program['symbols']['retained_capacity_joint_call']['address']
        self.controlled_retirements=0


def finish_result(validator):
    """Return the untouched reference result plus separately labeled counts.

    Reference finish contains historical diagnostic limits/count labels. Keep
    them verbatim. No data-bearing semantic record/check is rewritten here.
    Independent full-stream GP0/counter checking is still required externally.
    """
    reference=validator.finish()
    joint=isinstance(validator,JointValidator);role='joint' if joint else validator.role
    return dict(schema='csr-capacity-explicit-geometry-semantic-result-v1',
        state='PASS reference semantic completion; independent full-stream/counter/owned acceptance still required',
        reference_semantic_result=reference,
        actual_count_summary=dict(lines=validator.profile.lines,sets=validator.profile.sets,role=role,
            expected_six_GP0=expected_counters(validator.profile,role),
            D_target_loads=8*validator.profile.lines if role in ('d-enabled','d-off','joint') else 0,
            I_target_instructions=16*validator.profile.lines if role in ('i-enabled','i-off','joint') else 0),
        limits='Explicit source profile only. Reference diagnostic256/64 labels are preserved historical metadata; no native/physical/app execution is authorized.')


def _binding(path):
    p=Path(path).resolve();h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024**2),b''):h.update(chunk)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def _verify(row):
    require(_binding(row['path'])=={k:row[k]for k in ('path','bytes','sha256')},'frozen semantic dependency '+row['path'])


def _module(row,name):
    _verify(row);spec=importlib.util.spec_from_file_location(name,row['path'])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def load_context(anchors_path,expected_sha):
    """Later explicit ROOT metadata/source import; no implicit old context."""
    require(_binding(anchors_path)['sha256']==expected_sha,'exact ROOT reviewed1280 context SHA')
    a=json.loads(Path(anchors_path).read_text())
    require(a['schema']=='csr1280-semantic-current-anchors-v1' and a['state']=='ROOT-BOUND current1280 semantic source context; no run authority' and a['ROOT_reviewed']is True,'pending DRAFT cannot load or approve a context')
    require(a['TOP']=='88ab04dfcc508176cc977096ca0c132299a8a460' and a['BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','new1280 source only')
    require(a['SOURCE']=='/run/user/1001/zp-csr-unmasked1280-fullcore-20261122-01/source','actual new1280 SOURCE namespace')
    require(set(a['closed_anchors'])=={'full','flow','proposal','qualification','clone_admission','build','STD','geometry','base','future_freeze'},'all actual1280 full/scoped/STD/base anchors')
    for row in a['closed_anchors'].values():_verify(row)
    _verify(a['model']);_verify(a['original_model']);_verify(a['actual_source_list'])
    for row in a['critical_ingested'].values():_verify(row)
    require(a['original_model']['sha256']=='95699e2ab8c4b3ef7fa8999688d2908dffa65a396c51f63aee522bbf4156a742','actual current1280 original model, not1536/ac3 or historical1280')
    full=json.loads(Path(a['closed_anchors']['full']['path']).read_text())
    require(full['state']=='PASS CSR unmasked1280 trace0 clean fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-17geometry-source-audits' and full['source_tree_baseline']==a['TOP'] and full['source_bp']==a['BP'] and full['source_endcheck']=='PASS','actual clean11phase1280 producer')
    require({k:full['model'][k]for k in ('path','bytes','sha256')}==a['original_model'],'original model receipt match')
    strict=_module(a['strict'],'csr1280_actual_literal_strict')
    require(strict.ROOT==Path(a['SOURCE']),'literal actual compiled SOURCE; no historical global replacement')
    strict.source_bindings(Path(a['actual_source_list']['path']))
    generator=_module(a['generator'],'csr1280_exact_analytic_generator')
    _verify(a['schema167']);schema=json.loads(Path(a['schema167']['path']).read_text())
    selected=dict(strict.selections())
    selected.update({'mutation':('unicore_lite.dcache_retained_mutation_v',1),
        'maintenance':('unicore_lite.dcache_retained_maintenance_v',1),
        'obs.hits':('retained_observe.counts.hits_o',32),
        'obs.published':('retained_observe.counts.published_o',32),
        'obs.beats':('retained_observe.counts.write_beats_o',32)})
    expected={r['key']:(r['suffix'],r['width'])for r in schema['leaves']}
    require(len(selected)==167 and selected==expected and list(selected)==list(expected),'exact immutable raw167 key/path/width/order contract')
    actual=json.loads(Path(a['closed_anchors']['geometry']['path']).read_text())['facts']['values']
    require(actual==a['actual_geometry17'] and len(actual)==17 and actual['retained_store.storage.i_lines_p']==actual['retained_store.storage.d_lines_p']==1280 and actual['retained_store.storage.sets_p']==256,'actual17 geometry, candidate1280 only')
    proposal=json.loads(Path(a['closed_anchors']['proposal']['path']).read_text())
    require(len(proposal['writer_leaves'])==415 and proposal['original_TOP']==a['TOP'] and proposal['original_BP']==a['BP'] and proposal['original_model']==a['original_model'],'actual1280 original/415 union/source proof')
    require(proposal['original_session']==a['closed_anchors']['full'],'same accepted fullsession')
    for suffix,width in selected.values():
        found=[r for r in proposal['writer_leaves']if r['path']==suffix or r['path'].endswith('.'+suffix)]
        require(len(found)==1 and found[0]['width']==width,'one current writer leaf/width '+suffix)
    build=json.loads(Path(a['closed_anchors']['build']['path']).read_text())
    require(build['binary']==a['model'] and build['baseline_relink']['sha256']==a['original_model']['sha256'],'exact new scoped1280 from untouched relink')
    require(a['model']['path']=='/run/user/1001/zp-csr-unmasked1280-fullcore-20261122-01/scoped-csr01/build/obj/Vbsg_nonsynth_zynq_testbench','actual new1280 scoped namespace')
    qualification=json.loads(Path(a['closed_anchors']['qualification']['path']).read_text())
    require(qualification['state']=='PASS-matched1280-cold08-five-domain-literal-equivalence-strict-counter-geometry' and len(qualification['domains'])==5 and all(r['literal_bytes_equal']for r in qualification['domains'].values()),'actual current five complete domains')
    std=json.loads(Path(a['closed_anchors']['STD']['path']).read_text())
    require(std['model']==a['model'] and std['state']=='PASS four unchanged architectural tests on new CSR-unmasked qualified model; no performance claim','new1280 STD model match; generic label alone insufficient')
    return namedtuple('Context','strict generator selected anchors')(strict,generator,MappingProxyType(selected),a)


def event_samples(lines,context):
    # Same qualified parser signature and all records; no event filtering.
    return edges(lines,context.selected)


# Explicit compatibility name for the established single-role audit interface.
Validator=SingleValidator
