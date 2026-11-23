"""Exact768 source successor; existing physical lifecycle, no authority by import."""
import json,math,re,shlex,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
MAIN=Path('/home/coyang/zynq-parrot-linux-capacity')
sys.path.insert(0,str(MAIN/'linux-tests'))
import retained_capacity_diagnostic as historical
import retained_capacity_diagnostic_v3 as history3
base,application,stage=historical.base,historical.application,historical.stage
require,binding,verify_binding,exact=historical.require,historical.binding,historical.verify_binding,historical.exact
HERE=Path(__file__).resolve().parent
ROOT=MAIN
SCHEMA='csr768-physical-capacity-functional-v1'
ROLES=('d-enabled','d-off','i-enabled')
RUNNER=historical.RUNNER
OLD,HELPER,COMPILE=historical.OLD,historical.HELPER,historical.COMPILE
TOP='1b24c915ed628f6d47a382b3aa89fb662884e1a1'
BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
MODEL='1f192b69fb95fce8919d7fbbe6a4c2c594fc8983982e7e2822821e74f2b75fef'
ELF='062a3dd884d64bc1fdf7f0048f312cc5efc84280eb89006c21ef6b60f1f43ed6'
BUILD='88546c8afc17c482e42cb731459f44c2a40f2f6aeee2c172321534c872dabd72'
NBFS=dict(zip(ROLES,('4a8512dfa3074997c7e6ecf63a733a5cc597595c455308397a7f3a88090d6921','b60a50bba248fd8c54a7cc1385a2e25eb852f1a7a53e39b162c479ed9087e9d4','047f330163a22ba0eda3ec8cd559f655a718bec8300b4113c745a86f4d764267')))
COUNTERS=dict(zip(ROLES,((0,768,0,768,0,6144),(0,0,0,0,0,0),(768,0,768,0,6144,0))))
PARAMETERS=dict(BP_RETAINED_BUFFER=1,BP_RETAINED_I_LINES=768,BP_RETAINED_D_LINES=768,BP_RETAINED_SETS=256,BP_RETAINED_OBSERVE=1,BP_AXI_RESPONSE_DELAY=0,BP_CACHE_MISS_TRACE=0)
HARDWARE=dict(historical.HARDWARE,retained_i_lines=768,retained_d_lines=768)
IO,OFFSETS=historical.IO,historical.OFFSETS
MAP_DEFINES={name:IO[name]for name in ('HP0_ADDR_BASE','GP0_ADDR_BASE','GP1_ADDR_BASE')}
FIXTURE_CONFIG={}
SOURCE_PATHS={name:MAIN/name for name in history3.SOURCE_FILES}
SOURCE_PATHS.update({'csr768-physical/'+name:HERE/name for name in ('protocol.py','collector.py','recovery.py')})
SOURCE_FILES=tuple(SOURCE_PATHS)
def source_hashes():return {name:binding(path)['sha256']for name,path in SOURCE_PATHS.items()}

def verify_candidate(a):
    verify_binding(a['approvals']);require(a['approvals']['path']==str(HERE/'approvals.ROOT.json'),'exact frozen ROOT promotion path');approvals=json.loads((HERE/'approvals.ROOT.json').read_text())
    require(approvals['ROOT_approved']is True and approvals['candidate_bridge']==a['candidate_bridge'],'fresh ROOT exact image approval; DRAFT cannot run')
    verify_binding(a['candidate_bridge']);bridge=json.loads(Path(a['candidate_bridge']['path']).read_text())
    require(bridge['schema']=='csr768-physical-image-approval-v1'and bridge['ROOT_verified']is True and bridge['state']=='PASS ROOT approved exact routed768 image and unchanged physical fixtures','actual physical image approval')
    require(bridge['candidate']==dict(top=TOP,bp=BP,model_sha256=MODEL)and bridge['hardware']==HARDWARE and bridge['parameters']==PARAMETERS,'fixed768 source/model/ordinary geometry')
    require(bridge['runner_API_ownership_accepted']is True and bridge['owned_DRAM_bytes']==48234496,'accepted deployed46MiB API ownership contract, no kernel-memory witness')
    for value in bridge['evidence'].values():verify_binding(value)
    return bridge['candidate']

def verify_files(a):
    for key in ('runner','rollback_runner','compile_gate','elf','build_gate','model_preparation','candidate_bridge'):verify_binding(a[key])
    for group in ('programs','model_audits','artifacts','rollback_overlay'):
        for value in a[group].values():verify_binding(value)

def verify_programs(a):
    verify_files(a);verify_candidate(a)
    require(a['runner']['sha256']==RUNNER and a['runner']['bytes']==35984 and a['rollback_runner']['sha256']==OLD and a['rollback_runner']['bytes']==35860,'unchanged private9c/accepted2dd bytes')
    require(a['compile_gate']['sha256']==COMPILE and a['elf']['sha256']==ELF and a['build_gate']['sha256']==BUILD,'unchanged exact static/software/native compile gates')
    built=json.loads(Path(a['build_gate']['path']).read_text());require(built['max_lines']==1792 and built['max_sets']==256 and built['elf']['sha256']==ELF,'same runtime-geometry MAX1792 ELF')
    FIXTURE_CONFIG.update(data_base='0x%016x'%built['data_base'],code_base='0x%016x'%built['code_base'])
    model=json.loads(Path(a['model_preparation']['path']).read_text())
    require(model['ROOT_verified']is True and model['lines']==768 and model['sets']==256 and model['model_sha256']==MODEL and model['completed_roles']==list(ROLES)and model['model_audits']==a['model_audits'],'actual complete768 per-address native proofs, not sparse/old1280 approval')
    for role in ROLES:
        nbf=a['programs'][role];require(nbf['sha256']==NBFS[role]and Path(nbf['path']).name=='retained-capacity768-'+role+'.nbf','unique fixed staged role name')
        require(nbf['sha256']==built['cases'][role]['nbf']['sha256'],'copy preserves exact existing NBF')
        cov=built['cases'][role]['coverage'];require(cov['missing_bytes']==cov['wrong_bytes']==0 and cov['load_bound']['allocation_bytes']==48234496 and int(cov['load_bound']['maximum_write_end_exclusive'],16)<=0x82e00000,'complete file-backed zeros and46MiB owned tail')
        audit=json.loads(Path(a['model_audits'][role]['path']).read_text())
        require(audit['state'].startswith('PASS')and audit['lines']==768 and audit['actual_count_summary']['sets']==256 and len(audit['targets'])==768 and audit['actual_count_summary']['expected_six_GP0']==list(COUNTERS[role]),'actual complete configured targets and counters')
        expected=0 if role=='d-off'else 768
        require(len(audit['publications'])==len(audit['hits'])==len(audit['retained_bursts'])==expected and len(audit['ordinary_bursts'])==(768 if role=='d-off'else 0),'complete same-model per-address positive/negative evidence')
        require(audit['bindings']['model']['sha256']==MODEL and audit['bindings']['program']['sha256']==BUILD,'actual same fixture/model audit')
        stream=audit['archive']['full_stream'];require(stream['reader_returncode']==0 and stream['exact_end_records']==1 and stream['lines']==stream['events']+169,'complete167 stream EOF')

def verify_map_defines(text):
    # Maintained generated MAP contains address bases ONLY. Widths/enables and
    # clocks belong to independently bound build/HWH/host evidence below.
    defines={}
    for token in shlex.split(text):
        require(token.startswith('-D')and '='in token,'generated address MAP token')
        name,value=token[2:].split('=',1)
        require(name in MAP_DEFINES and name not in defines,'unknown or duplicate generated address MAP define')
        try:defines[name]=int(value,0)
        except ValueError:raise ValueError('invalid generated address MAP value')
    require(defines==MAP_DEFINES,'actual generated MAP address bases differ')
    return defines


def verify_io_certificate(cert,artifacts,a):
    require(set(cert)=={'ROOT_verified','values','build','HWH','host_source','compile_gate','runner'},'independent build/HWH/host I/O certificate membership')
    require(cert['ROOT_verified']is True and cert['values']==IO,'actual widths/enables/20MHz-8MHz full I/O contract')
    require(cert['HWH']==artifacts['hwh']and cert['compile_gate']==a['compile_gate']and cert['runner']==a['runner']and cert['runner']['sha256']==RUNNER,'actual selected HWH and exact private host compile/source identity')
    for key in ('build','HWH','host_source','compile_gate','runner'):verify_binding(cert[key])
    return cert['values']


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
    verify_map_defines(Path(artifacts['map']['path']).read_text())
    verify_io_certificate(elaborated['io_contract'],artifacts,a)
    checked=subprocess.run([str(base.SCRIPTS/'verify_pynq_package.sh'),artifacts['package']['path'],artifacts['bit']['sha256']],
        capture_output=True,text=True,timeout=90)
    require(checked.returncode==0 and 'PACKAGE_OK=1\n' in checked.stdout
        and 'PACKAGE_SHA256='+artifacts['package']['sha256']+'\n' in checked.stdout,'maintained local package verification')
    return bundle


def validate(a):
    require(a.get('schema')==SCHEMA and a.get('state')=='bound-reviewed-capacity-diagnostic','DRAFT UNLAUNCHABLE768 functional qualification')
    require(not a.get('unlaunchable_reasons')and a.get('role')=='capacity-physical-diagnostic','explicit ROOT physical capacity role')
    require(a.get('host')=='xilinx@192.168.4.35'and a.get('schedule')==list(ROLES),'fixed host/schedule')
    require(exact(a.get('runtime_ms'),300000)and exact(a.get('outer_timeout_s'),420)and a.get('performance_inference')is False,'same functional native/outer limits')
    require(a.get('hardware')==HARDWARE and a.get('sources')==source_hashes(),'unchanged source/ordinary geometry contract')
    verify_programs(a);verify_route(a)
    require(set(a['rollback_overlay'])=={'bit','hwh','map'},'exact current original overlay collateral')
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
    require(config==dict(version='1',lane=role[0],active='0' if role=='d-off' else '1',lines='768',sets='256',max_lines='1792',
        line_bytes='64',data_base=FIXTURE_CONFIG['data_base'],code_base=FIXTURE_CONFIG['code_base'],code_stride='192',copy='0'),'actual capacity/control geometry')
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
