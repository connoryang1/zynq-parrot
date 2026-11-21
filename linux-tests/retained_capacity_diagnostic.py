"""Strict synthetic physical capacity diagnostic; no board actions or speed claims."""
import json
import math
from pathlib import Path
import re
import shlex
import subprocess

import retained29_protocol as base
import retained29_application_protocol as application
import retained29_stage_v2 as stage

SCHEMA='bp-retained-capacity-physical-diagnostic-v1'
ROOT=base.ROOT
ROLES=('d-enabled','d-off','i-enabled')
RUNNER='9c2648f1a9d2ceab2645895fdad74a5bc2c2ce62ad8f1161c6b3b72e74da42fa'
OLD=base.RUNNER_SHA
HELPER=base.HELPER_SHA
TOP='15288321bfb1443c5ce39318014f60cd979890f9'
BP='e10992a3eea3ba2ef6ae3ccb42ff5e8c658286a8'
MODEL='bdc8b908f55fbdb6e5b9dce22d8588cc163020fff74a44eda8a83a451a1ad8cf'
ELF='ab90a7927da1cf2b21a03e18d061c97fb27c94cd60819432d31306748a55c276'
BUILD='bea554ccfe813ea9a696e8566bfcde1c11ff6efe4e8858a6c7708032329efd08'
COMPILE='4ed7da7f3a69394e8bc115a6748fdbc8f9cd6d7ccd01014c72126af482b20d72'
NBFS=dict(zip(ROLES,('f5cd0e5dd6796252dce03ca38fbfae227cf14b3dbab395ec0eb791ba340063e1',
    '313666a37eed4467ec39b98f98a1980ec80e6157b11434b959e6d3008204e93e',
    'c19f4aeeb392169191722876695c780a5d3fce52c8ce83febe7ea1ce3efa7e1f')))
AUDITS=dict(zip(ROLES,('94c446f8275dd8c77d0572a357f2b2f7636032e74572a13e17892fd3703fa9ef',
    'c0383a6174b9aa2271e5160486c2876c67e90151a61e17056d5b15eba2d7d49e',
    '37673dfdc52ef1f8dd548572d9e52b177d7bb78443834f39c6794ceaf1b0b704')))
COUNTERS=dict(zip(ROLES,((0,1280,0,1280,0,10240),(0,0,0,0,0,0),(1280,0,1280,0,10240,0))))
PARAMETERS=dict(BP_RETAINED_BUFFER=1,BP_RETAINED_I_LINES=1280,BP_RETAINED_D_LINES=1280,
    BP_RETAINED_SETS=256,BP_RETAINED_OBSERVE=1,BP_AXI_RESPONSE_DELAY=0)
HARDWARE=dict(cfg='e_bp_unicore_zynqparrot_prefetch16k_cfg',l1i_bytes=32768,l1d_bytes=32768,
    l2_bytes=16384,resident_slots=2,logical_contexts=4,line_bytes=64,retained_i_lines=1280,
    retained_d_lines=1280,retained_sets=256,observe=1,response_age=0)
IO=dict(GP0_ENABLE=1,GP0_ADDR_BASE=0x40000000,GP0_ADDR_WIDTH=10,GP0_DATA_WIDTH=32,
    GP1_ENABLE=1,GP1_ADDR_BASE=0x80000000,GP1_ADDR_WIDTH=30,GP1_DATA_WIDTH=32,
    HP0_ENABLE=1,HP0_ADDR_WIDTH=32,HP0_DATA_WIDTH=64,HP0_ADDR_BASE=0,ACLK_MHZ=20,RTCLK_MHZ=8)
OFFSETS=dict(hits=0x3c,published=0x40,writes=0x44)
# r2 is a historical model proof, not an admissible deployment candidate.
# Populate only after independent review of a closed versioned bridge. There
# is deliberately no CLI override for an arbitrary future implementation.
REVIEWED_CANDIDATE_BRIDGES={}
SOURCE_FILES=(*application.SOURCE_FILES,'linux-tests/retained_capacity_diagnostic.py',
    'linux-tests/retained_capacity_install.py','linux-tests/run_retained_capacity_diagnostic.py')
require,binding,verify_binding=base.require,base.binding,base.verify_binding


def exact(actual,expected):
    """JSON booleans must never stand in for hardware integers."""
    return type(actual) is type(expected) and (set(actual)==set(expected)
        and all(exact(actual[k],expected[k]) for k in expected) if isinstance(expected,dict)
        else actual==expected)


def source_hashes():return {name:binding(ROOT/name)['sha256'] for name in SOURCE_FILES}


def verify_programs(a):
    for key in ('runner','rollback_runner','compile_gate','elf','build_gate','model_preparation'):
        verify_binding(a[key])
    require(a['runner']['sha256']==RUNNER and a['runner']['bytes']==35984
        and a['rollback_runner']['sha256']==OLD and a['rollback_runner']['bytes']==35860,'actual native/rollback runners')
    require(a['compile_gate']['sha256']==COMPILE and a['elf']['sha256']==ELF and a['build_gate']['sha256']==BUILD,'fixed compile/ELF/static gate')
    compiled=json.loads(Path(a['compile_gate']['path']).read_text())
    require(compiled['state']=='PASS root-run private native ARM compile; never installed/executed'
        and compiled['runner']['sha256']==RUNNER and compiled['accepted_runner']==OLD and compiled['helper']==HELPER
        and compiled['physical_program_runs']==compiled['overlay_actions']==0 and compiled['installed'] is False,'closed compile-only provenance')
    built=json.loads(Path(a['build_gate']['path']).read_text())
    require(built['max_lines']==1280 and built['max_sets']==256 and built['elf']['sha256']==ELF,'fixed1280 ELF')
    model=json.loads(Path(a['model_preparation']['path']).read_text())
    require(model['model']['sha256']==MODEL and model['geometry']==dict(i_lines=1280,d_lines=1280,sets=256,line_bytes=64,observe=1,delay=0)
        and model['schedule']==list(ROLES),'closed model topology/order')
    require(set(a['programs'])==set(a['model_audits'])==set(ROLES),'exact three fixture roles')
    names=[]
    for role in ROLES:
        nbf=a['programs'][role];verify_binding(nbf);verify_binding(a['model_audits'][role])
        require(nbf['sha256']==NBFS[role] and Path(nbf['path']).name=='retained-capacity1280-'+role+'.nbf','fixed uniquely named NBF')
        names.append(Path(nbf['path']).name)
        require(a['model_audits'][role]['sha256']==AUDITS[role],'fixed completed per-address audit')
        audit=json.loads(Path(a['model_audits'][role]['path']).read_text())
        expected='PASS negative actual ordinary-memory fallback with primary retained-use rejection' if role=='d-off' else 'PASS actual distinct configured-line publications/hits/full-SRAM payload and checked execution'
        require(audit['state']==expected and audit['lines']==1280 and audit['sets']==256 and audit['lane']==role[0],'passed matching model audit')
        require(len(audit['publications'])==len(audit['hits'])==len(audit['retained_bursts'])==(0 if role=='d-off' else 1280),'actual model line evidence')
        require(len(audit['ordinary_bursts'])==(1280 if role=='d-off' else 0),'negative ordinary-memory evidence')
        require(audit['bindings']['program']['sha256']==BUILD,'audit/ELF build binding')
        coverage=built['cases'][role]['coverage']
        require(coverage['missing_bytes']==coverage['wrong_bytes']==0
            and coverage['load_bound']['allocation_bytes']==48234496
            and int(coverage['load_bound']['maximum_write_end_exclusive'],16)<=0x82e00000,'zero-complete owned46M NBF loading')
    require(len(set(names))==3,'distinct staged names')


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


def positive_use(counts,lane):
    require(tuple(counts)==COUNTERS[lane+'-enabled'],'primary retained-use gate rejected')


def parse_console(text,role,bit_sha):
    require(role in ROLES,'declared diagnostic fixture')
    lines=base.clean_lines(text)
    require(not base.KERNEL_FAILURE_MARKER.search(text) and base.TIMER_GUARD_MARKER not in text,'kernel/runtime failure')
    require(not any('HOST_VERIFY' in s or '[BSG-FAIL]' in s or 'CORE FAIL' in s or 'BSG FAIL' in s
        or 'NATIVE_RETAINED_OBSERVER_FAIL' in s or 'target runtime limit reached' in s
        or s.startswith(('ACTIVE_RUNNER','RUNNER_CLEANUP_SYNC_FAILED','NBF_SHA_MISMATCH','CONTROL_PROGRAM_SHA_MISMATCH',
            'BITSTREAM_SHA_MISMATCH','RESUME_RETAINED29_','PIPE_HINT_')) for s in lines),'guest/host/helper failure or wrong role')
    for key,expected in [('CONTROL_PROGRAM_SHA256',RUNNER),('NBF_SHA256',NBFS[role]),('BITSTREAM_SHA256',bit_sha),('BOARD_RUNNER_SOURCE_SHA256',HELPER)]:
        require([s for s in lines if s.startswith(key+'=')]==[key+'='+expected],'executed '+key+' identity')
    configs=[s for s in lines if s.startswith('RETAINED_CAPACITY_CONFIG ')]
    require(len(configs)==1,'one exact capacity config')
    config=base.fields(configs[0],'RETAINED_CAPACITY_CONFIG',('version','lane','active','lines','sets','max_lines','line_bytes','data_base','code_base','code_stride','copy'))
    require(config==dict(version='1',lane=role[0],active='0' if role=='d-off' else '1',lines='1280',sets='256',max_lines='1280',
        line_bytes='64',data_base='0x0000000080058000',code_base='0x0000000080008000',code_stride='192',copy='0'),'actual capacity/control geometry')
    def one(pattern):
        found=[(n,m) for n,s in enumerate(lines) if (m:=re.fullmatch(pattern,s))]
        require(len(found)==1,'one exact complete terminal/counter row: '+pattern);return found[0]
    prefix=r'(?:(?:BSG-)?INFO:\s*)?'
    decoded=one(prefix+r'RETAINED_USE_COUNTERS version=1 i_hits=(\d+) d_hits=(\d+) i_published=(\d+) d_published=(\d+) i_write_beats=(\d+) d_write_beats=(\d+) saturating_bits=16 reset=axi_only')
    require(sum('RETAINED_USE_COUNTERS' in line for line in lines)==2,'only one decoded and one stability snapshot row')
    counts=tuple(map(int,decoded[1].groups()));require(counts==COUNTERS[role] and all(v<65535 for v in counts),'exact nonsaturated fixture counters')
    stable=one(prefix+r'RETAINED_USE_COUNTERS_STABILITY version=1 stable=1 equal=1 saturated=0 gap_us=1000 delay_rc=0 first_hits=(0x[0-9a-f]{8}) first_published=(0x[0-9a-f]{8}) first_writes=(0x[0-9a-f]{8}) second_hits=(0x[0-9a-f]{8}) second_published=(0x[0-9a-f]{8}) second_writes=(0x[0-9a-f]{8})')
    raw=tuple(int(value,16) for value in stable[1].groups())
    require(raw[:3]==raw[3:] and tuple(v for word in raw[:3] for v in (word&65535,word>>16))==counts,'actual both snapshots/raw decoded consistency')
    guest=one(r'\[BSG-PASS\] retained capacity checked all full64B payloads completed')[0]
    core=one(prefix+r'CORE(?:\[0\])? PASS')[0]
    host=one(prefix+r'Returning from ps_main with RC: 0')[0];bsg=one(prefix+r'BSG PASS')[0]
    helper=lines.index('BOARD_RUNNER_SOURCE_SHA256='+HELPER)
    require(lines.index(configs[0])<guest<core<decoded[0]<stable[0]<host<bsg<helper,'complete guest/counter/host/helper chronology')
    allocation=one(prefix+r'ps.cpp: allocating owned DRAM buffer with size 48234496')[0]
    runtime=one(prefix+r'ps.cpp: limiting target runtime to 300000 ms')[0]
    native=one(r'bsg_zynq_pl: allocate_dram\(\) called with size 48234496 bytes --> virtual ptr=0x[0-9a-f]+, physical ptr=(0x[0-9a-f]+)')
    physical=int(native[1][1],16)
    require(runtime<allocation<native[0]<lines.index(configs[0]) and physical>0 and physical%4096==0 and physical+48234496<=2**32,'actual native bounded owned46M allocation/base')
    require(all(lines.index(key+'='+expected)<runtime for key,expected in
        [('CONTROL_PROGRAM_SHA256',RUNNER),('NBF_SHA256',NBFS[role]),('BITSTREAM_SHA256',bit_sha)]),'prelaunch identities precede actual runtime')
    rejected=False
    if role=='d-off':
        try:positive_use(counts,'d')
        except ValueError:rejected=True
        require(rejected,'negative must fail primary retained-use gate')
    else:positive_use(counts,role[0])
    return dict(role=role,counters=list(counts),raw_snapshots=list(raw),observed_stable_interval=True,
        primary_use_gate_rejected=rejected,owned_bytes=48234496,physical_base=hex(physical),
        limits='Synthetic checked execution plus aggregate nonsaturated stable counters; weaker than per-address model FST, not a halt/global-drain/application benefit proof.')
