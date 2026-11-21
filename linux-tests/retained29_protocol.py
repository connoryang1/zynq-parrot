"""Strict ABI29 functional-only console and artifact contracts; no board actions."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

import run_resume_workload_session as maintained_session
import run_scheduler_pipe_hint as transport
from run_scheduler_tagged_replay import KERNEL_FAILURE_MARKER, TIMER_GUARD_MARKER

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = maintained_session.SCRIPTS
NBF_SHA = '1a06cae9ce4c93eeb634d109ce1e58d6b7d6cade85ec966e7bcd848828ef9d33'
RUNNER_SHA = '2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30'
HELPER_SHA = 'de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90'
KERNEL_PROOF_SHA = 'b4da4bffaeeb6e635e9799c6694e585c9852002ac6504963a3da036d79655cdf'
ABSENT_BIT_SHA = 'f744228b33b8c7c4bed552fb607ceee3d28418fe05569b60a42f547bbea8be9f'
ABSENT_PACKAGE_SHA = '07a48584e22de3e1d97cdaef16d27a92faabc1a9f3db82bafd5e76fe18f1bbe5'
ELF_SHAS = {'probe-absent':'9bb01f51b23ca190e7c1bc1c1bc935c01f3441bacab79463438312084c13f79a',
            'probe-present':'9bb01f51b23ca190e7c1bc1c1bc935c01f3441bacab79463438312084c13f79a',
            'benchmark-functional':'24c66080e836bbc17c64c7fc82d53575860c6ccd3e40de3ffb0554c3c58b26c6'}
GUEST = {'probe-absent':'/tmp/bp-retained29-probe', 'probe-present':'/tmp/bp-retained29-probe',
         'benchmark-functional':'/tmp/bp-retained29-benchmark'}
BENCH_ARGS = ['8','2','ordinary-joint','4','futex','plain','32','lookup','none']
SOURCE_FILES = tuple(dict.fromkeys((*maintained_session.HOST_SOURCES,
    'codex-skills/bp-fpga-synthesis/scripts/verify_pynq_package.sh',
    'codex-skills/bp-fpga-synthesis/scripts/board_run_pynq_interactive.sh',
    'linux-tests/retained29_protocol.py','linux-tests/run_retained29_session.py',
    'linux-tests/retained_store_probe.c','linux-tests/scheduler_retained29_benchmark.c',
    'linux-tests/resume_workload.h')))
GEOMETRY = 0x03ffffffffff0000
ALLOWED = GEOMETRY | (1<<63) | 0xf0f
PREFIX_PENDING = (1<<54) | 14
PREFIX_COUNTERS = (0xffff<<22)|(0xff<<38)|(0xff<<46)|(0x1ff<<55)
REPLAY_PENDING = 0xf00000000000000f
REPLAY_COUNTERS = 0x03fffffffffffc00


def require(condition, message):
    if not condition: raise ValueError(message)


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def verify_binding(value):
    require(set(value)=={'path','bytes','sha256'},'artifact binding fields')
    require(Path(value['path']).is_absolute(),'artifact path must be absolute')
    require(binding(value['path'])==value,'artifact changed: '+value['path'])


def source_hashes():
    return {name:binding(ROOT/name)['sha256'] for name in SOURCE_FILES}


def argv_for(role):
    require(role in ELF_SHAS,'unknown functional role')
    return [GUEST[role],* (BENCH_ARGS if role=='benchmark-functional' else [role.split('-')[1]])]


def guest_command(role):
    return ' '.join(argv_for(role))+'; r29_rc=$?; echo RETAINED29_EXIT rc=$r29_rc'


def transfer_commands(admission):
    """Reuse strict old transport validation without changing its globals.

    Remap only canonical fixed destinations after full payload/command checks;
    base64 cannot contain the old underscored filename. Embedded copies are
    deliberately unsupported until a separately reviewed new rootfs exists.
    """
    path = Path(admission['artifacts']['transfer']['path'])
    result = transport.validate_transfer(path,admission['artifacts']['elf']['sha256'])
    require(result is None,'ABI29 initial gates require wire payload, not embedded copy')
    return [line.replace(transport.GUEST_ELF,GUEST[admission['role']]) for line in path.read_text().splitlines()]


def validate_admission(admission):
    require(admission.get('schema')=='bp-retained29-functional-session-v1','admission schema')
    require(admission.get('state')=='bound-functional-only','unbound/draft admission cannot execute')
    role = admission.get('role');require(role in ELF_SHAS,'functional role')
    require(admission.get('guest_argv')==argv_for(role),'noncanonical functional argv')
    require(admission.get('one_guest_boot') is True and admission.get('performance_inference') is False,'functional scope')
    require(admission.get('host')=='xilinx@192.168.4.35','fixed board host')
    require(admission.get('runner_sha256')==RUNNER_SHA and admission.get('board_helper_sha256')==HELPER_SHA,'runner/helper binding')
    require(admission.get('runtime_ms')==3600000,'fixed native runtime bound')
    require(admission.get('sources')==source_hashes(),'host/guest source identity changed')
    artifacts = admission['artifacts']
    require(set(artifacts)=={'nbf','elf','transfer','package','bit','fit','kernel_verification'},'artifact set')
    for value in artifacts.values(): verify_binding(value)
    require(artifacts['nbf']['sha256']==NBF_SHA and artifacts['elf']['sha256']==ELF_SHAS[role]
            and artifacts['kernel_verification']['sha256']==KERNEL_PROOF_SHA,'kernel/ELF/proof identity')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+\.nbf',Path(artifacts['nbf']['path']).name),'NBF basename')
    proof = json.loads(Path(artifacts['kernel_verification']['path']).read_text())
    require(proof.get('state')=='PASS offline actual-linked-kernel and bounded-NBF verification; runtime pending','kernel proof')
    require(proof['load_bound']['allocation_bytes']==48234496 and proof['load_bound']['all_write_tails_within_allocation'] is True,'offline46M bound')
    fit = json.loads(Path(artifacts['fit']['path']).read_text())
    require(str(fit.get('state','')).startswith('routed-fit-and-package-PASS'),'routed fit not passed')
    require(fit.get('bit_sha256')==artifacts['bit']['sha256'] and fit.get('package_sha256')==artifacts['package']['sha256'],'fit/package/bit binding')
    require(fit.get('cfg')==admission['hardware']['cfg'],'hardware configuration binding')
    # The maintained verifier is local-only; it extracts no target workload and
    # performs no SSH/board action. Its source itself is pinned above.
    verified = subprocess.run([str(SCRIPTS/'verify_pynq_package.sh'),artifacts['package']['path'],artifacts['bit']['sha256']],
                              text=True,capture_output=True,timeout=90)
    require(verified.returncode==0 and 'PACKAGE_OK=1\n' in verified.stdout,'local package extraction verification')
    require('PACKAGE_SHA256='+artifacts['package']['sha256']+'\n' in verified.stdout,'package verifier identity')
    transfer_commands(admission)
    hardware = admission['hardware']
    require(hardware.get('l1i_bytes')==32768 and hardware.get('l1d_bytes')==32768,'ordinary L1 source geometry')
    require(hardware.get('l2_bytes') in (4096,16384),'explicit L2 geometry required')
    if role=='probe-absent':
        require(hardware.get('retained') is None and hardware['l2_bytes']==4096
                and artifacts['bit']['sha256']==ABSENT_BIT_SHA
                and artifacts['package']['sha256']==ABSENT_PACKAGE_SHA,'fixed accepted absent hardware')
    if role!='probe-absent':
        expected = hardware['retained']
        require(set(expected)=={'i_lines','d_lines','set_log2'},'retained geometry fields')
        require(all(type(expected[k]) is int for k in expected),'retained geometry integers')
        require(1<=expected['i_lines']<=65535 and 1<=expected['d_lines']<=65535 and 0<=expected['set_log2']<=15,'retained geometry range')
        require(hardware['l2_bytes']==16384,'new matched hardware L2 binding')
    if role=='benchmark-functional':
        verify_binding(admission['capability_gate'])
        gate = json.loads(Path(admission['capability_gate']['path']).read_text())
        require(gate.get('state')=='PASS-complete-recovered-functional-session' and gate.get('role')=='probe-present','successful present probe required')
        require(gate.get('guest_boots')==1 and gate.get('recovery')=='complete before reservation release'
                and gate.get('release_after_recovery_utc') and gate.get('performance_inference') is False,'probe recovery/release proof')
        require(gate.get('hardware')==hardware,'probe/benchmark hardware mismatch')
        for key in ('nbf','package','bit'):
            require(gate['artifacts'][key]==artifacts[key],'probe/benchmark '+key+' mismatch')
        validate_admission(gate['admission'])
        require(gate['admission']['role']=='probe-present' and gate['artifacts']==gate['admission']['artifacts']
                and gate['sources']==admission['sources'],'probe admission/source provenance')
        guest=gate['guest'];require(guest.get('runner_exit')==0 and guest.get('runner_signal') is None
                and guest.get('guest_exit')==0 and guest.get('shell_return') is True,'probe actual return proof')
        verify_binding(guest['console'])
        complete_console(Path(guest['console']['path']).read_text(),gate['admission'])
    return admission


def clean_lines(text): return [line.strip() for line in text.replace('\r','').splitlines()]


def identity_lines(text, admission):
    lines = clean_lines(text)
    for name, expected in (('CONTROL_PROGRAM_SHA256',RUNNER_SHA),('NBF_SHA256',NBF_SHA),
                           ('BITSTREAM_SHA256',admission['artifacts']['bit']['sha256'])):
        values = [s.split('=',1)[1] for s in lines if s.startswith(name+'=')]
        require(values==[expected],'actual '+name+' mismatch/duplicate')


def boot_bound(text, admission):
    identity_lines(text,admission)
    require(re.search(r'allocating owned DRAM buffer with size 48234496\b',text),'actual owned46M allocation missing')
    require(re.search(r'allocate_dram\(\) called with size 48234496 bytes',text),'actual allocation call size missing')
    require('Memory limited to 46MB' in text,'Linux46MB cap missing')
    require(re.search(r'Memory: \d+K/47104K available',text),'Linux total not47104K')
    require(re.search(r'DMA32\s+\[mem 0x0*80000000-0x0*82dfffff\]',text),'DMA32 bound')
    require(re.search(r'Domain0 Next Arg1\s*:\s*0x0*82200000\b',text),'runtime FDT destination')
    lines = clean_lines(text)
    command = [s.split('Kernel command line:',1)[1].strip() for s in lines if 'Kernel command line:' in s]
    require(len(command)==1 and command[0].split().count('mem=46M')==1
            and command[0].split().count('rdinit=/bin/sh')==1,'bootargs bound')
    require(not KERNEL_FAILURE_MARKER.search(text) and TIMER_GUARD_MARKER not in text,'boot failure marker')


def fields(line, prefix, names):
    parts = line.split();require(parts and parts[0]==prefix,'marker name/order')
    result = {}
    for part in parts[1:]:
        require(part.count('=')==1,'marker token')
        key,value = part.split('=');require(key not in result,'duplicate marker field')
        result[key]=value
    require(set(result)==set(names),'marker fields: '+prefix)
    return result


def number(value):
    require(re.fullmatch(r'0|[1-9][0-9]*',value),'unsigned canonical integer')
    result=int(value);require(result<1<<64,'integer overflow');return result


def raw(value):
    require(re.fullmatch(r'0x[0-9a-f]{16}',value),'raw status width');return int(value,16)


def status_geometry(value, expected, mode, idle):
    require(value&(1<<63) and value&(3<<56)==3<<56 and not value&~ALLOWED,'capability/status flags')
    require((value&15)==mode and (not idle or not value&0x300),'control readback/reset busy')
    require(((value>>16)&65535,(value>>32)&65535,(value>>48)&255)==
            (expected['i_lines'],expected['d_lines'],expected['set_log2']),'actual retained geometry')


def parse_guest(text, admission):
    lines = clean_lines(text);role=admission['role']
    require(not KERNEL_FAILURE_MARKER.search(text) and TIMER_GUARD_MARKER not in text,'console failure')
    require(not any('HOST_VERIFY_' in s or s.startswith(('PIPE_HINT_','ICACHE_RETENTION_PROBE_')) for s in lines),'legacy/host marker contamination')
    if role.startswith('probe-'):
        wanted='present' if role=='probe-present' else 'absent'
        selected=[s for s in lines if s.startswith('RETAINED_STORE_PROBE_')]
        require(selected and selected[-1]=='RETAINED_STORE_PROBE_PASS capability='+wanted,'new probe PASS')
        require(len(selected)==(2 if wanted=='present' else 1),'probe missing/extra rows')
        if wanted=='present':
            row=fields(selected[0],'RETAINED_STORE_PROBE_STATUS',
                       ('raw','i_lines','d_lines','set_log2','line_bytes','same_set_invalidation','busy_scope','poll_limit'))
            expected=admission['hardware']['retained'];status_geometry(raw(row['raw']),expected,0,True)
            require(all(number(row[k])==expected[k] for k in expected),'probe printed geometry')
            require(row['line_bytes']=='64' and row['same_set_invalidation']=='1' and
                    row['busy_scope']=='uce_client_backend' and row['poll_limit']=='4096','probe status schema')
        return dict(capability=wanted)
    selected=[s for s in lines if s.startswith('RESUME_RETAINED29_')]
    require(len(selected)==27 and selected[-1]=='RESUME_RETAINED29_PASS','complete four-cell functional marker set')
    config=fields(selected[0],'RESUME_RETAINED29_CONFIG',('loops','repeats','warmup','policy','enabled_mask','sync','profile',
         'corpus_kib','workload','advisory_source','task_preview_mode','i_lines','d_lines','set_log2','line_bytes','same_set_invalidation','poll_limit'))
    expected=dict(loops='8',repeats='2',warmup='4',policy='ordinary-joint',enabled_mask='15',sync='futex',profile='plain',
         corpus_kib='32',workload='lookup',advisory_source='none',task_preview_mode='0',line_bytes='64',same_set_invalidation='1',poll_limit='4096')
    require(all(config[k]==v for k,v in expected.items()),'fixed functional benchmark config')
    require(all(number(config[k])==v for k,v in admission['hardware']['retained'].items()),'benchmark configured geometry')
    require(selected[1]=='RESUME_RETAINED29_SCOPE version=29 mode=cell activation=before-allocation cleanup=mode0 busy=uce_client_backend matched_lifecycle=1 advisory_source=none','whole-cell scope')
    for cell,(repeat,order,enabled) in enumerate(((0,0,0),(0,1,1),(1,0,1),(1,1,0))):
        rows=selected[2+cell*6:8+cell*6];key=('repeat','order','enabled')
        schemas=(('RESULT',('cycles','loops')),('WHOLE',('cycles','loops')),
                 ('CONTROL',('requested','active_raw','reset_raw','busy_scope')),
                 ('RESOURCE',('minor_faults','major_faults','user_us','system_us','voluntary_switches','involuntary_switches')),
                 ('PREFIX',('before','after','new_activity','advisory_source')),
                 ('REPLAY',('before','after','new_activity','advisory_source')))
        parsed=[]
        for line,(name,names) in zip(rows,schemas):
            row=fields(line,'RESUME_RETAINED29_'+name,(*key,*names))
            require(tuple(number(row[k]) for k in key)==(repeat,order,enabled),'cell chronology/key')
            parsed.append(row)
        require(parsed[0]['loops']==parsed[1]['loops']=='8','loop count')
        require(0<number(parsed[0]['cycles'])<=number(parsed[1]['cycles']),'WHOLE vs steady')
        control=parsed[2];require(number(control['requested'])==15*enabled and control['busy_scope']=='uce_client_backend','cell control')
        status_geometry(raw(control['active_raw']),admission['hardware']['retained'],15*enabled,False)
        status_geometry(raw(control['reset_raw']),admission['hardware']['retained'],0,True)
        for k in schemas[3][1]:number(parsed[3][k])
        for row,pending,counters,shifts in ((parsed[4],PREFIX_PENDING,PREFIX_COUNTERS,((22,16),(38,8),(46,8),(55,9))),
                                           (parsed[5],REPLAY_PENDING,REPLAY_COUNTERS,((10,16),(26,16),(42,8),(50,8)))):
            a,b=raw(row['before']),raw(row['after'])
            require(row['new_activity']=='0' and row['advisory_source']=='none','source-none declaration')
            require(not (a|b)&pending and a&counters==b&counters,'advisory pending/activity')
            require(all((a>>s)&((1<<w)-1)!=(1<<w)-1 for s,w in shifts),'saturated source counters')
    return dict(complete_cells=4,functional_only=True,performance_inference=False)


def complete_console(text, admission):
    boot_bound(text,admission)
    parsed=parse_guest(text,admission)
    lines=clean_lines(text)
    require([s for s in lines if s.startswith('RETAINED29_EXIT ') ]==['RETAINED29_EXIT rc=0'],'actual normal guest return')
    require(sum(bool(re.fullmatch(r'(?:INFO:\s*)?CORE(?:\[0\])? PASS',s)) for s in lines)==1,'CORE PASS')
    require(sum('Returning from ps_main with RC: 0' in s for s in lines)==1,'HOST normal return')
    require(sum(s in ('INFO:    BSG PASS','INFO: BSG PASS','BSG PASS') for s in lines)==1,'HOST/BSG PASS')
    require([s for s in lines if s.startswith('BOARD_RUNNER_SOURCE_SHA256=')]==['BOARD_RUNNER_SOURCE_SHA256='+HELPER_SHA],'actual board helper source')
    passed=('RESUME_RETAINED29_PASS' if admission['role']=='benchmark-functional'
            else 'RETAINED_STORE_PROBE_PASS capability='+admission['role'].split('-')[1])
    ordered=(lines.index(passed),lines.index('RETAINED29_EXIT rc=0'),
             next(i for i,s in enumerate(lines) if re.fullmatch(r'(?:INFO:\s*)?CORE(?:\[0\])? PASS',s)),
             next(i for i,s in enumerate(lines) if 'Returning from ps_main with RC: 0' in s),
             next(i for i,s in enumerate(lines) if s in ('INFO:    BSG PASS','INFO: BSG PASS','BSG PASS')),
             lines.index('BOARD_RUNNER_SOURCE_SHA256='+HELPER_SHA))
    require(all(a<b for a,b in zip(ordered,ordered[1:])),'guest/CORE/HOST/helper completion order')
    return parsed
