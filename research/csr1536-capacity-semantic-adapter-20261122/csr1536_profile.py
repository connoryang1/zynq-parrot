"""Pure semantic geometry adapter; no lifecycle, stream I/O, or run authority."""
from collections import namedtuple
import hashlib
import importlib.util
import json
from pathlib import Path
from types import MappingProxyType
from csr1536_support import require
from csr1536_methods import SingleMethods,LaneMethods,JointMethods
from csr1536_parser import edges

HERE=Path(__file__).resolve().parent
Geometry=namedtuple('Geometry','lines sets')
ROLES=('d-enabled','d-off','i-enabled','i-off')


def geometry(lines,sets=256):
    require(type(lines) is int and lines in (256,1536) and type(sets) is int and sets==256,'explicit control256 or candidate1536, same256sets')
    return Geometry(lines,sets)


def expected_counters(profile,role):
    require(role in (*ROLES,'joint'),'explicit single/joint role')
    n=profile.lines
    return [n,n,n,n,8*n,8*n] if role=='joint' else [n,0,n,0,8*n,0] if role=='i-enabled' else [0,n,0,n,0,8*n] if role=='d-enabled' else [0]*6


def target_index(slot,sets):
    # At256 this reduces exactly to the established first-way constructor.
    # At1536 retain the way bits, covering six complete ways, no address search.
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


def load_context():
    """Explicit later ROOT read/import gate; never imports historical audit ROOT."""
    a=json.loads((HERE/'anchors.json').read_text())
    for row in a['closed_anchors'].values():_verify(row)
    _verify(a['model']);_verify(a['original_model']);_verify(a['actual_source_list'])
    for row in a['critical_ingested'].values():_verify(row)
    require(a['model']['sha256']=='5bdbcd740944e5f42e3780f8e26492a8a1189b4710faab9c510d94ea9169b7ec' and a['original_model']['sha256']=='ac3ad3af06b4db95398ef471585529add0a1fb9099229aff812f6fd8a9c4e5ac','exact current1536 model lineage')
    strict=_module(a['strict'],'csr1536_actual_literal_strict')
    require(strict.ROOT==Path(a['SOURCE']),'literal actual compiled SOURCE; no historical global replacement')
    strict.source_bindings(Path(a['actual_source_list']['path']))
    generator=_module(a['generator'],'csr1536_exact_analytic_generator')
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
    require(actual==a['actual_geometry17'] and len(actual)==17 and actual['retained_store.storage.i_lines_p']==actual['retained_store.storage.d_lines_p']==1536 and actual['retained_store.storage.sets_p']==256,'actual17 geometry fields, candidate1536 only')
    proposal=json.loads(Path(a['closed_anchors']['proposal']['path']).read_text())
    require(len(proposal['writer_leaves'])==415,'actual415 union')
    for suffix,width in selected.values():
        found=[r for r in proposal['writer_leaves']if r['path']==suffix or r['path'].endswith('.'+suffix)]
        require(len(found)==1 and found[0]['width']==width,'one current writer leaf/width '+suffix)
    qualification=json.loads(Path(a['closed_anchors']['qualification']['path']).read_text())
    require(qualification['state']=='PASS-matched1536-cold08-five-domain-literal-equivalence-strict-counter-geometry' and len(qualification['domains'])==5 and all(r['literal_bytes_equal']for r in qualification['domains'].values()),'actual current five complete domains')
    return namedtuple('Context','strict generator selected anchors')(strict,generator,MappingProxyType(selected),a)


def event_samples(lines,context):
    # Same qualified parser signature and all records; no event filtering.
    return edges(lines,context.selected)


# Explicit compatibility name for the established single-role audit interface.
Validator=SingleValidator
