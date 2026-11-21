#!/usr/bin/env python3
"""Prepared metadata-only fullcore gate; build/runtime require explicit --execute admission."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import signal
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
INSTALL = Path('/home/coyang/zynq-parrot-linux-research/install')
READER = Path('/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121/fst-reader/fst_events')
R1 = '6f29d685332a44e89dcaba5b5adb33520b678da4'
BP = '225489a435cb0b2a2c0b237077f94418dc89549b'
SOURCE_TOP = '9a188f87fdf19a72c64c24a9c425f6876be4ea37'
RESERVE = 3*1024**3
ALLOCATION = 768*1024**2
FST_LIMIT = 150*1024**2
BASE = Path('/home/coyang/fpga-artifacts/context-resume/retained-dense-fullcore-20261121')
HERE = Path(__file__).resolve().parent
PROGRAM_DIR = BASE/'program02'
PROGRAM_PROOF = PROGRAM_DIR/'program-proof.json'
FIXTURE = Path('/home/coyang/zynq-parrot-linux-fit1280/research/retained-control-abi-20261121/advisory-fixture-cold08/manifest.json')
READER_SHA = 'a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541'
PROGRAMS = {
    'integrity': ('6dc1d67b880e85d9841c8a2ae5fc86043e2944f2925e5384c6edb8416dfc1277',
                  'f856b599e14a1567c836b621d80581c533fbeec6955516ebbd6c157891cda9d9'),
    'advisory': ('3fe096173e3a63b2656c1fadf0a058a328fb5f1ee375be652176408856f897b8',
                 '627662f775f9c2645e5b5687a9df3bfaed25d42265e125a0386047ebe1daad4b')}


def bind(path):
    path = Path(path).resolve(); h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576), b''):h.update(block)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=h.hexdigest())


def full_bind(path):
    result = bind(path); stat = Path(path).stat()
    result.update(inode=stat.st_ino,mtime_ns=stat.st_mtime_ns,ctime_ns=stat.st_ctime_ns)
    return result


def git(path,*args):
    return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,512*1024**2))


def validate_output(out):
    if out.exists() or out.parent != BASE:raise ValueError('fresh exact metadata artifact-root child required')


def all_own_preparation(status):
    return all(line[3:].startswith('research/retained-dense-fullcore-20261121/') for line in status.splitlines())


def validate_source_tree(root):
    subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',SOURCE_TOP,'HEAD'],check=True)
    changed=git(root,'diff',SOURCE_TOP,'--name-only').splitlines()
    if any(p!='cosim/black-parrot-example/Makefile.design' and not p.startswith('research/retained-dense-fullcore-20261121/') for p in changed):
        raise ValueError('compiled source differs from frozen TOP55ed tree')
    if git(root/'import/black-parrot','rev-parse','HEAD')!=BP:raise ValueError('metadata BP pin')
    config='cosim/black-parrot-example/Makefile.design'
    original=subprocess.check_output(['git','-C',str(root),'show',SOURCE_TOP+':'+config]).decode()
    expected=original.replace('BP_RETAINED_I_LINES ?= 1280','BP_RETAINED_I_LINES ?= 1792').replace('BP_RETAINED_D_LINES ?= 1280','BP_RETAINED_D_LINES ?= 1792')
    if (root/config).read_text()!=expected:raise ValueError('only two authorized retained defaults may change')


def input_bindings():
    files=[PROGRAM_PROOF,HERE/'prepare_programs.py',READER,FIXTURE,ROOT/'research/retained-private-sp-ram-20261121/run_full.py',
           ROOT/'research/retained-private-sp-ram-20261121/close_full.py',
           ROOT/'testing/check_run.py',ROOT/'testing/rtl/retained-advisory-trace/validate.py',
           ROOT/'research/retained-use-observation-20261121/verify_counters.py',
           ROOT/'research/retained-maintenance-acyclic-20261121/bind_geometry.py',
           HERE/'geometry.py',HERE/'close_full.py']
    files += [PROGRAM_DIR/(kind+'-prog.'+suffix+'.gz')
              for kind in PROGRAMS for suffix in ('riscv','nbf')]
    fixture=json.loads(FIXTURE.read_text());files += [Path(fixture[k]['path']) for k in ('elf','source')]
    return [bind(p) for p in files]


def validate_inputs():
    proof=json.loads(PROGRAM_PROOF.read_text())
    if proof['state']!='PASS-fresh1792-integrity-accepted-flags-CRT-and-byteidentical-cold08-preparation-only':
        raise ValueError('fresh1792 accepted-flags/CRT software proof required')
    if proof['expected']!=dict(i_lines=1792,d_lines=1792,sets=256) or not proof['accepted_compiler_comment_match']:
        raise ValueError('software capacity/compiler identity')
    for row in proof['sources']+proof['tools']+proof['link_inputs']:
        if bind(row['path'])!=row:raise ValueError('software/CRT/toolchain source drift '+row['path'])
    if bind(READER)['sha256']!=READER_SHA:raise ValueError('exact existing FST reader required')
    for kind,expected in PROGRAMS.items():
        for suffix,wanted in zip(('riscv','nbf'),expected):
            path=PROGRAM_DIR/(kind+'-prog.'+suffix+'.gz')
            if hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()!=wanted:
                raise ValueError('immutable program/archive drift '+kind)
    if bind(FIXTURE)['sha256']!='977bfe0c4502d36fb367137e96c56e6db50c024ad634a63ee06ef3cb94ee3e0d':
        raise ValueError('exact cold08 manifest')
    fixture=json.loads(FIXTURE.read_text())
    for key in ('elf','source'):
        if bind(fixture[key]['path'])!=fixture[key]:raise ValueError('closed cold08 input drift')


def validate_actual_command(text):
    for token in ('--assert','--trace-fst','--build-jobs 3','-DBSG_HIDE_FROM_SYNTHESIS'):
        if token not in text:raise ValueError('actual scopedassert/trace/jobs '+token)
    for name,value in [('ACLK_MHZ',20),('BP_RETAINED_BUFFER',1),('BP_RETAINED_I_LINES',1792),
                       ('BP_RETAINED_D_LINES',1792),('BP_RETAINED_SETS',256),
                       ('BP_RETAINED_OBSERVE',1),('BP_AXI_RESPONSE_DELAY',0)]:
        if not re.search(r'(?<!\S)-D'+name+'='+str(value)+r'(?=\s|"|$)',text):
            raise ValueError('actual Verilator flag '+name)
    if 'BP_RETAINED_METADATA_VERIFY' in text:raise ValueError('component checker leaked into production model')
    if 'BP_CUSTOM_BASE_CFG' in text or 'BP_NUM_THREADS' in text:raise ValueError('CUSTOM configuration forbidden')
    for suffix in ('bp_common/src/v/bp_retained_line_store.sv','bp_me/src/v/cce/bp_uce.sv'):
        if str(ROOT/'import/black-parrot'/suffix) not in text:raise ValueError('wrong actual BP source '+suffix)


def validate_stamp(name):
    for token in ('cfge_bp_unicore_zynqparrot_prefetch16k_cfg','trace1',
                  'BP_RETAINED_BUFFER_1','BP_RETAINED_I_LINES_1792','BP_RETAINED_D_LINES_1792',
                  'BP_RETAINED_SETS_256','BP_RETAINED_OBSERVE_1','BP_AXI_RESPONSE_DELAY_0',
                  '-assert-bsgsimhidden-support'):
        if token not in name:raise ValueError('wrong production model stamp '+token)


def directory_bytes(out):
    return sum(p.stat().st_size for p in out.rglob('*') if p.is_file())


def resource_check(out):
    used=directory_bytes(BASE);free=shutil.disk_usage(BASE).free
    if used>ALLOCATION or free<RESERVE+max(0,ALLOCATION-used):
        raise ValueError('fixed768MiBallocation/3GiBreserve violated')


def monitored_run(argv,cwd,env,log,timeout,out,runtime):
    resource_check(out)
    def child_limits():
        limits()
        if runtime:resource.setrlimit(resource.RLIMIT_FSIZE,(FST_LIMIT,FST_LIMIT))
    process=subprocess.Popen(argv,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,
                             start_new_session=True,preexec_fn=child_limits)
    start=time.monotonic()
    try:
        while process.poll() is None:
            if time.monotonic()-start>=timeout:raise TimeoutError('fixed outer timeout')
            resource_check(out)
            try:process.wait(timeout=1)
            except subprocess.TimeoutExpired:pass
        resource_check(out)
        return process.returncode
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        raise


def run_closed_audits(out,record,run):
    # Reuse the unchanged generated-bank/RAM auditor, exact strict payload/I
    # retirement validator, and independent real-edge/GP0 counter validator.
    spec=importlib.util.spec_from_file_location('metadata_geometry_base',ROOT/'research/retained-maintenance-acyclic-20261121/bind_geometry.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    facts,paths=module.inspect(out,record['model']['sha256'])
    write(out/'geometry.json',dict(state='PASS actual generated STATIC16KiB L2 geometry',facts=facts,
        source_auditor=bind(module.__file__),snapshot_paths=list(map(str,paths))))
    advisory=out/'advisory';rc=json.loads((advisory/'process.json').read_text())['returncode']
    if run('advisory-strict',['python3','-B',ROOT/'testing/rtl/retained-advisory-trace/validate.py',
          '--fst',advisory/'trace.fst','--reader',READER,'--model-source-list',out/'actual-source-list.json',
          '--fixture-manifest',FIXTURE,'--log',advisory/'run.log','--exit-code',str(rc),'--reader-timeout','600',
          '--out',out/'advisory-strict01'],timeout=660):raise ValueError('strict fullpayload/Iretire/eight-L1-write proof failed')
    if run('advisory-counter',['python3','-B',ROOT/'research/retained-use-observation-20261121/verify_counters.py',
          '--fst',advisory/'trace.fst','--reader',READER,'--strict-proof',out/'advisory-strict01/verification.json',
          '--run-proof',advisory/'verification.json','--out',out/'advisory-counter01'],timeout=240):
        raise ValueError('actual edge/reset/GP0 transition proof failed')
    if run('advisory-geometry',['python3','-B',HERE/'geometry.py','--fst',advisory/'trace.fst',
          '--reader',READER,'--out',out/'actual-parameters01'],timeout=660):raise ValueError('actual parameter geometry failed')
    record['closed_audits']={key:bind(out/path) for key,path in (
        ('strict','advisory-strict01/verification.json'),('counter','advisory-counter01/verification.json'),
        ('generated_l2','geometry.json'),('parameters','actual-parameters01/verification.json'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--execute',action='store_true',help='requires separate root admission; never implied by preparation')
    parser.add_argument('--prepared',type=Path)
    args = parser.parse_args(); out = args.out.resolve()
    validate_output(out)
    if args.prepare_only == args.execute:raise ValueError('choose exactly one of --prepare-only/--execute')
    if shutil.disk_usage(BASE.parent).free < RESERVE+ALLOCATION:raise ValueError('need3GiBreserve+768MiBallocation')
    validate_source_tree(ROOT)
    if git(ROOT,'rev-parse','refs/heads/experiment/linux-retained-native1280-r1') != R1:raise ValueError('r1 ref changed')
    repos = [(ROOT,git(ROOT,'rev-parse','HEAD')),(ROOT/'import/black-parrot',BP)]
    for relative,sha in [('external/basejump_stl','3dff9f43af8e1bb850da0b41696514396fa0fa7e'),
                         ('external/HardFloat','5b7d5fe2df7e297b5ba095b3eb8a9517dc2e9d88'),
                         ('external/bedrock','ed68e749079df57afa4b2e153184bf9301137bf2')]:
        repos.append((ROOT/'import/black-parrot'/relative,sha))
    repos += [(ROOT/'import/basejump_stl','6cd7d830b732079ab7316c6288e2e819e3fab474'),
              (ROOT/'import/black-parrot-subsystems','f6ce99ea7ebdcb97a46f73c296505071e9fb22ab'),
              (ROOT/'import/bsg_replicant','83e2441b3bab646a69159fa9dee80de2af9b24ae')]
    before_repos = []
    for path,sha in repos:
        if not (path/'.git').is_file() or git(path,'rev-parse','--show-toplevel') != str(path):
            raise ValueError('missing real initialized worktree '+str(path))
        if git(path,'rev-parse','HEAD') != sha:raise ValueError('wrong commit '+str(path))
        status=git(path,'status','--porcelain','--untracked-files=normal')
        if status and not (args.prepare_only and path==ROOT and all_own_preparation(status)):raise ValueError('dirty source '+str(path))
        before_repos.append(dict(path=str(path),head=sha,status=status))
    BASE.mkdir(exist_ok=True)
    out.mkdir(); runtime=out/'verilator';runtime.mkdir()
    (out/'Makefile.design').symlink_to(ROOT/'cosim/black-parrot-example/Makefile.design')
    recipe=ROOT/'research/hp0-response-path-20261121/full-system-delay200-10/source-before.json.gz'
    command=json.loads(gzip.decompress(recipe.read_bytes()))['command_prefix']
    command=[arg.replace('/home/coyang/zynq-parrot-linux-capacity',str(ROOT)) for arg in command]
    # Admit defaults from the candidate Makefile rather than forcing the four
    # retained geometry/observe flags in this model's command line.
    command=[arg for arg in command if not arg.startswith(('BP_RETAINED_BUFFER=','BP_RETAINED_I_LINES=',
                 'BP_RETAINED_D_LINES=','BP_RETAINED_SETS=','BP_RETAINED_OBSERVE='))]
    command=[('BP_AXI_RESPONSE_DELAY=0' if arg.startswith('BP_AXI_RESPONSE_DELAY=') else arg) for arg in command]
    command+=['ZP_IMPORT_DIR='+str(ROOT/'import'),'COSIM_VSRC_DIR='+str(ROOT/'cosim/v')]
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    env['LD_LIBRARY_PATH']=str(INSTALL/'lib')+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    for key in list(env):
        if key.startswith(('BP_RETAINED_','BP_AXI_RESPONSE_DELAY')):env.pop(key)
    critical=[ROOT/p for p in ('cosim/black-parrot-example/Makefile.design','cosim/black-parrot-example/Makefile.hardware',
        'cosim/black-parrot-example/v/top_zynq.sv','cosim/black-parrot-example/ps.cpp','cosim/black-parrot-example/ps.hpp',
        'cosim/v/bp_retained_use_counters.sv','cosim/mk/Makefile.verilator','cosim/tcl/vivado-utils.tcl',
        'cosim/src/main.cpp','testing/rtl/scoped-assertions/bsg_clkgate_optional.sv',
        'import/black-parrot/bp_top/src/v/bp_unicore_lite.sv','import/black-parrot/bp_me/src/v/cce/bp_uce.sv',
        'import/black-parrot/bp_common/src/v/bp_retained_line_store.sv')]
    before={str(path):full_bind(path) for path in critical}
    record=dict(state='prepared',source_repositories=before_repos,source_before=before,script=bind(__file__),
        recipe=bind(recipe),command_prefix=command,environment=dict(LD_LIBRARY_PATH=env['LD_LIBRARY_PATH']),commands=[],
        fresh_program_proof=bind(PROGRAM_PROOF),
        geometry=dict(i_lines=1792,d_lines=1792,sets=256,line_bytes=64,observe=1,delay=0,resident=2,logical=4,l2_bytes=16384,aclk_mhz=20),
        source_tree_baseline=SOURCE_TOP,source_bp=BP,free_before=shutil.disk_usage(out).free,
        resource_admission=dict(reserve_bytes=RESERVE,allocation_bytes=ALLOCATION,per_runtime_file_bytes=FST_LIMIT),
        scope='Synthetic scoped actual-fulltop correctness; runtime BP assertions after reset, guarded library/timezero checks excluded. No all-slot fullcore utilization, FPGA fit or application performance claim.')

    def run(label,argv,cwd=out,timeout=120):
        entry=dict(label=label,argv=list(map(str,argv)),cwd=str(cwd),timeout_seconds=timeout)
        record['commands'].append(entry);write(out/'session.json',record)
        start=time.monotonic()
        with (out/(label+'.log')).open('wb') as log:
            result=monitored_run(entry['argv'],cwd,env,log,timeout,out,label.endswith('-run'))
        entry.update(returncode=result,elapsed_seconds=time.monotonic()-start,log=bind(out/(label+'.log')))
        write(out/'session.json',record)
        return result

    try:
        validate_inputs()
        record['inputs']=input_bindings()
        if args.execute:
            if not args.prepared:raise ValueError('explicit immutable preparation record required')
            prepared=json.loads(args.prepared.read_text())
            if not prepared['state'].startswith('PASS prepared-only') or prepared['launchable'] is not False:
                raise ValueError('preparation scope')
            if prepared['script']!=bind(__file__) or prepared['inputs']!=record['inputs'] or prepared['command_prefix']!=command:
                raise ValueError('prepared flow/input/command changed')
            if prepared['geometry']!=record['geometry'] or prepared['resource_admission']!=record['resource_admission']:
                raise ValueError('prepared geometry/resource change')
            record['prepared']=bind(args.prepared)
        if args.prepare_only:
            record['state']='PASS prepared-only: exact sources/inputs/resource/command guards; NO make/build/model execution'
            record['launchable']=False
            return
        if run('make-preflight',command+['-n','build'],runtime):raise ValueError('Make parse/preflight failed')
        dry=(out/'make-preflight.log').read_text()
        for flag in ('BP_RETAINED_BUFFER=1','BP_RETAINED_I_LINES=1792','BP_RETAINED_D_LINES=1792',
                     'BP_RETAINED_SETS=256','BP_RETAINED_OBSERVE=1','BP_AXI_RESPONSE_DELAY=0'):
            if flag not in dry:raise ValueError('candidate default not expanded: '+flag)
        if run('clean',command+['clean'],runtime):raise ValueError('clean failed')
        record['state']='clean complete; building'
        if run('build',command+['build'],runtime,3600):raise ValueError('clean model build failed')
        metadata=runtime/'obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat';actual={}
        for line in metadata.read_text().splitlines():
            match=re.fullmatch(r'S\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"([^"]+)"',line)
            if not match:continue
            size,inode,ctime,cnsec,mtime,mnsec=map(int,match.groups()[:6]);path=Path(match[7])
            if not path.is_absolute():path=runtime/path
            bound=full_bind(path)
            if (bound['bytes'],bound['inode'],bound['ctime_ns'],bound['mtime_ns'])!=(size,inode,ctime*10**9+cnsec,mtime*10**9+mnsec):
                raise ValueError('actual source ingestion metadata differs: '+str(path))
            actual[str(path.resolve())]=bound
        c_line=next((line for line in metadata.read_text().splitlines() if line.startswith('C ')), '')
        validate_actual_command(c_line)
        for name in ('cosim/v/bp_retained_use_counters.sv','cosim/black-parrot-example/v/top_zynq.sv',
                     'import/black-parrot/bp_top/src/v/bp_unicore_lite.sv','import/black-parrot/bp_common/src/v/bp_retained_line_store.sv'):
            if str(ROOT/name) not in actual:raise ValueError('candidate source not consumed '+name)
        write(out/'actual-source-list.json',dict(sources=actual,metadata=bind(metadata)))
        model=runtime/'obj_dir/Vbsg_nonsynth_zynq_testbench';record['model']=full_bind(model)
        record['actual_source_list']=bind(out/'actual-source-list.json')
        stamps=list((runtime/'obj_dir').glob('.build_config-*'))
        tokens=('BP_RETAINED_BUFFER_1','BP_RETAINED_I_LINES_1792','BP_RETAINED_D_LINES_1792',
                'BP_RETAINED_SETS_256','BP_RETAINED_OBSERVE_1','BP_AXI_RESPONSE_DELAY_0','trace1','-assert-bsgsimhidden-support')
        if len(stamps)!=1 or not all(t in stamps[0].name for t in tokens):raise ValueError('wrong actual model stamp')
        validate_stamp(stamps[0].name)
        record['model_stamp']=bind(stamps[0]);record['state']='PASS clean build; runtime pending'
        if run('loader',['ldd',model]):raise ValueError('loader preflight failed')
        if 'not found' in (out/'loader.log').read_text():raise ValueError('unresolved loader input')
        closure=PROGRAM_DIR
        for name,hashes in PROGRAMS.items():
            target=out/name;target.mkdir()
            for suffix,wanted in zip(('riscv','nbf'),hashes):
                raw=gzip.decompress((closure/(name+'-prog.'+suffix+'.gz')).read_bytes())
                if hashlib.sha256(raw).hexdigest()!=wanted:raise ValueError('closed program mismatch '+name)
                (target/('prog.'+suffix)).write_bytes(raw)
            native,guard=(600000,780) if name=='integrity' else (180000,240)
            argv=[model,'+c_args=prog.nbf '+str(native),'+bsg_trace='+str(target/'trace.fst')]
            write(target/'admission.json',dict(model=record['model'],compiled_sources=record['actual_source_list'],
                elf=bind(target/'prog.riscv'),nbf=bind(target/'prog.nbf'),command=list(map(str,argv)),
                native_host_runtime_ms=native,outer_timeout_s=guard,geometry=record['geometry']))
            rc=run(name+'-run',argv,target,guard)
            shutil.copyfile(out/(name+'-run.log'),target/'run.log')
            write(target/'process.json',dict(returncode=rc))
            check=['python3','-B',ROOT/'testing/check_run.py',target/'run.log','--exit-code',str(rc)]
            if name=='integrity':check+=['--test','mt_large_retained_system_test']
            if run(name+'-checker',check):raise ValueError('complete execution checker rejected '+name)
            text=(target/'run.log').read_text()
            if text.count('Verilator assertion setting restored to 1')!=1:raise ValueError('runtime assertions not restored')
            if name=='advisory':
                marker='[BSG-PASS] retained advisory full-line I/D checked all words completed'
                if text.count(marker)!=1 or text.index(marker)>text.index('CORE PASS'):raise ValueError('exact advisory fixture incomplete')
                rows=re.findall(r'RETAINED_USE_COUNTERS version=1 i_hits=(\d+) d_hits=(\d+) i_published=(\d+) d_published=(\d+) i_write_beats=(\d+) d_write_beats=(\d+) saturating_bits=16 reset=axi_only',text)
                if len(rows)!=1 or tuple(map(int,rows[0]))!=(1,1,1,1,8,8):raise ValueError('actual GP0 observer counts '+repr(rows))
                state='PASS complete scoped wholecore and actual GP0 1hit/1publish/8writes per lane; strict closed trace audit pending'
            else:state='PASS-complete-checked-system-1792-native0-scoped-assertions'
            runproof=dict(state=state,actual_returncode=rc,known_postPASS_GPIO_exception=rc!=0,
                counter_values=rows[0] if name=='advisory' else None,sources=record['actual_source_list'],
                trace=bind(target/'trace.fst'),files=[full_bind(target/p) for p in ('admission.json','process.json','run.log','prog.riscv','prog.nbf','trace.fst')])
            write(target/'verification.json',runproof)
        run_closed_audits(out,record,run)
        for path,bound in actual.items():
            if full_bind(path)!=bound:raise ValueError('actual consumed source changed during gate '+path)
        if before!={str(path):full_bind(path) for path in critical}:raise ValueError('critical source changed during gate')
        if record['model']!=full_bind(model):raise ValueError('model changed during gate')
        for row in before_repos:
            if git(row['path'],'rev-parse','HEAD')!=row['head'] or git(row['path'],'status','--porcelain','--untracked-files=normal'):
                raise ValueError('source repository changed during gate '+row['path'])
        record['state']='PASS dense1792 fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-geometry-source-audits'
        validate_source_tree(ROOT)
        record['free_after']=shutil.disk_usage(out).free
        record['output_bytes_after']=directory_bytes(BASE)
    except BaseException as error:
        record.update(state='FAIL preserved, no accepted result',error=repr(error));raise
    finally:
        write(out/'session.json',record);print(out/'session.json',record['state'],flush=True)


if __name__=='__main__':main()
