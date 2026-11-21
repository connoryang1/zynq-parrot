"""V3 admission for own-session guarded recovery; prior V1 stays immutable."""
from retained_capacity_diagnostic import *
import retained_capacity_diagnostic_v2 as legacy

SCHEMA='bp-retained-capacity-physical-diagnostic-v3'
SOURCE_FILES=(*legacy.SOURCE_FILES,'linux-tests/retained_capacity_diagnostic_v3.py',
    'linux-tests/retained_capacity_recovery_v3.py','linux-tests/run_retained_capacity_diagnostic_v3.py')
REVIEWED_CANDIDATE_BRIDGES={}

def source_hashes():return {name:binding(ROOT/name)['sha256'] for name in SOURCE_FILES}

def verify_candidate(a):
    record=a.get('candidate_bridge')
    require(record is not None,'UNLAUNCHABLE: canceled r2; new candidate bridge pending')
    verify_binding(record)
    require(record['sha256'] in REVIEWED_CANDIDATE_BRIDGES,'UNLAUNCHABLE: no reviewed candidate bridge')
    bridge=json.loads(Path(record['path']).read_text())
    require(bridge['schema']=='bp-retained-capacity-candidate-bridge-v1'
        and bridge['state']=='PASS reviewed maintenance+area candidate bridge','versioned closed candidate bridge')
    require(bridge['original']==dict(top=TOP,bp=BP,model=MODEL,model_audits=AUDITS)
        and bridge['original_fit_status']=='CANCELLED structural maintenance feedback; no accepted route','historical proof/canceled-fit distinction')
    candidate=bridge['candidate']
    require(exact(candidate,REVIEWED_CANDIDATE_BRIDGES[record['sha256']])
        and re.fullmatch(r'[0-9a-f]{40}',candidate['top']) and re.fullmatch(r'[0-9a-f]{40}',candidate['bp'])
        and candidate['top']!=TOP and candidate['bp']!=BP and re.fullmatch(r'[0-9a-f]{64}',candidate['model_sha256'])
        and candidate['model_sha256']!=MODEL,'separately reviewed actual new candidate/model')
    require(exact(bridge['hardware'],HARDWARE) and exact(bridge['parameters'],PARAMETERS)
        and bridge['source_change_scope']=='acyclic maintenance equivalence plus two ram_decomp area attributes'
        and exact(bridge['maintenance_endpoint_vectors'],18370560),'bounded capacity-preserving implementation bridge')
    require(set(bridge['evidence'])=={'source_diff','maintenance_equivalence','new_model_admission',
        'strict_integrity','strict_advisory','observer_counters'},'new actual model and correctness evidence required')
    for proof in bridge['evidence'].values():verify_binding(proof)
    return candidate

def verify_route(a):
    candidate=verify_candidate(a)
    artifacts=a['artifacts'];require(set(artifacts)=={'package','bit','hwh','map','fit','elaboration'},'route artifact set')
    for record in artifacts.values():verify_binding(record)
    fit=json.loads(Path(artifacts['fit']['path']).read_text())
    require(fit.get('state')=='routed-fit-and-package-PASS' and fit['top']==candidate['top'] and fit['bp']==candidate['bp']
        and fit['candidate_bridge']==a['candidate_bridge']
        and fit['cfg']==HARDWARE['cfg'] and exact(fit['parameters'],PARAMETERS),'actual new candidate routed source/feature proof')
    require(fit['package_sha256']==artifacts['package']['sha256'] and fit['bit_sha256']==artifacts['bit']['sha256']
        and fit['map_sha256']==artifacts['map']['sha256'] and fit['hwh_sha256']==artifacts['hwh']['sha256'],'routed package collateral identity')
    require(type(fit['wns_ns']) in (int,float) and math.isfinite(fit['wns_ns']) and fit['wns_ns']>=0
        and type(fit['tns_ns']) in (int,float) and fit['tns_ns']==0,'routed timing required')
    require(set(fit['reports'])=={'timing','utilization','route','run_manifest'},'actual route report bindings')
    for report in fit['reports'].values():verify_binding(report)
    elaborated=json.loads(Path(artifacts['elaboration']['path']).read_text())
    require(elaborated['state']=='PASS actual fulltop retained geometry and observer decode'
        and elaborated['top']==candidate['top'] and elaborated['bp']==candidate['bp'] and exact(elaborated['hardware'],HARDWARE)
        and exact(elaborated['parameters'],PARAMETERS) and exact(elaborated['gp0_offsets'],OFFSETS),'actual compiled fulltop/map acceptance')
    require(set(elaborated['evidence'])=={'fulltop_retained_geometry','observer_decode','synthesis_defines'},'actual compiled/elaborated evidence required')
    for report in elaborated['evidence'].values():verify_binding(report)
    require(fit['elaboration']==artifacts['elaboration'],'fit/elaboration binding')
    mini=dict(artifacts=dict(package=artifacts['package'],bit=artifacts['bit']))
    bundle=stage.local_bundle(mini)
    for key in ('bit','map','hwh'):
        require(all(bundle['members'][key][k]==artifacts[key][k] for k in ('bytes','sha256')),'exact package '+key)
    defines={}
    for token in shlex.split(Path(artifacts['map']['path']).read_text()):
        if token.startswith('-D') and '=' in token:
            name,value=token[2:].split('=',1)
            if name in IO:
                require(name not in defines,'duplicate accepted MMIO map define');defines[name]=int(value,0)
    require(defines==IO,'actual map differs from native runner MMIO/clock definitions')
    checked=subprocess.run([str(base.SCRIPTS/'verify_pynq_package.sh'),artifacts['package']['path'],artifacts['bit']['sha256']],
        capture_output=True,text=True,timeout=90)
    require(checked.returncode==0 and 'PACKAGE_OK=1\n' in checked.stdout
        and 'PACKAGE_SHA256='+artifacts['package']['sha256']+'\n' in checked.stdout,'maintained local package verification')
    return bundle

def validate(a):
    require(a.get('schema')==SCHEMA and a.get('state')=='bound-reviewed-capacity-diagnostic','DRAFT UNLAUNCHABLE capacity diagnostic')
    require(not a.get('unlaunchable_reasons') and a.get('role')=='capacity-physical-diagnostic','reviewed explicit diagnostic role')
    require(a.get('host')=='xilinx@192.168.4.35' and a.get('schedule')==list(ROLES),'fixed host/case schedule')
    require(exact(a.get('runtime_ms'),300000) and exact(a.get('outer_timeout_s'),420) and a.get('performance_inference') is False,'fixed functional bounds only')
    require(exact(a.get('hardware'),HARDWARE) and a.get('sources')==source_hashes(),'hardware/frozen runtime source identity')
    verify_programs(a);verify_route(a)
    require(set(a['rollback_overlay'])=={'bit','hwh','map'},'reviewed original overlay triplet required')
    for record in a['rollback_overlay'].values():verify_binding(record)
    return a
