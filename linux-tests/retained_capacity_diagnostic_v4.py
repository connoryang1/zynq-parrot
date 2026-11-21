"""SP-only V4 contract; historical all-slot proof and physical approval are distinct."""
from retained_capacity_diagnostic import *
import retained_capacity_diagnostic_v3 as legacy

SCHEMA='bp-retained-capacity-physical-diagnostic-v4-sp'
SOURCE_FILES=(*legacy.SOURCE_FILES,'linux-tests/retained_capacity_diagnostic_v4.py',
    'linux-tests/run_retained_capacity_diagnostic_v4.py')
REVIEWED_CANDIDATE_BRIDGES={}
SP_PREPARED_SHA='ff95ca26a6ea1f8dc2e6acde3ddcca92907c9f42ed3ce5ac692257cda0a7a546'
SP_CANDIDATE=dict(top='11ca59a270b878e45c99fbfdb23a7fba01800d5c',
    bp='d766d42cdf04ee43ca1e915fb9da06f5cc117dde',
    model_sha256='f65c04d85f495e4412d782b32e362dd0ce09914787f8fbe61284964b7b34444e')
SP_EXECUTED_TOP='fa0549bd22a55aa2dc84557e08a9c3564bb839bd'
SP_EVIDENCE=('source_gate','component_proof','cycle_equivalence','negative_control',
    'fullcore_proof','strict_payload','observer','model_admission')

def source_hashes():return {name:binding(ROOT/name)['sha256'] for name in SOURCE_FILES}

def verify_prepared_sp(record):
    """Authentic offline source/model bridge; this grants NO physical authority."""
    verify_binding(record)
    require(record['sha256']==SP_PREPARED_SHA,'exact independently prepared SP source/model bridge')
    bridge=json.loads(Path(record['path']).read_text())
    require(bridge['schema']=='bp-retained-capacity-private1rw-bridge-v1'
        and bridge['state']=='PREPARED SP-only source/model bridge; review and fit pending'
        and bridge['profile']=='private-lane-1RW-storage','SP profile; M/AREA does not qualify')
    require(exact(bridge['candidate'],SP_CANDIDATE) and bridge['executed_top']==SP_EXECUTED_TOP,
        'exact SP final/executed/model identities')
    historical=bridge['historical']
    require(historical['original_top']==TOP and historical['original_bp']==BP
        and historical['allslot_model']==MODEL and exact(historical['allslot_audits'],AUDITS)
        and bridge['old_allslot_rerun_on_SP_model'] is False,'historical all-slot versus SP first-touch distinction')
    require(exact(bridge['hardware'],HARDWARE) and exact(bridge['parameters'],PARAMETERS),
        'unchanged1280/256/static16KiB/observe1/native0 geometry')
    require(bridge['component']['cases']==24 and bridge['component']['settled_evaluation_comparisons']==23401321
        and bridge['component']['clock_modes']==['inverted','different-periods']
        and bridge['component']['component_sets']==64 and bridge['component']['component_epoch_width']==2,
        'bounded component cycle-equivalence scope')
    require(bridge['physical_allowlist_approved'] is False
        and all(value is None for key,value in bridge['physical'].items() if key!='rollback_overlay')
        and all(value is None for value in bridge['physical']['rollback_overlay'].values()),
        'prepared bridge cannot pretend routed/physical approval')
    for key in SP_EVIDENCE:verify_binding(bridge[key])
    verify_binding(historical['M_AREA_bridge'])
    return bridge

def verify_candidate(a):
    record=a.get('candidate_bridge')
    require(record is not None,'UNLAUNCHABLE: actual SP source/model bridge required')
    bridge=verify_prepared_sp(record)
    require(record['sha256'] in REVIEWED_CANDIDATE_BRIDGES,'UNLAUNCHABLE: no root-reviewed SP candidate approval')
    require(exact(bridge['candidate'],REVIEWED_CANDIDATE_BRIDGES[record['sha256']]),
        'separately reviewed exact SP top/BP/model')
    return bridge['candidate']

def verify_files(a):
    for key in ('runner','rollback_runner','compile_gate','elf','build_gate','model_preparation'):
        verify_binding(a[key])
    for group in ('programs','model_audits','artifacts','rollback_overlay'):
        for record in a[group].values():verify_binding(record)
    verify_prepared_sp(a['candidate_bridge'])

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
