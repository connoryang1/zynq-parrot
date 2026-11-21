#!/usr/bin/env python3
"""One strict, same-ELF32KiB latency200 control; never builds RTL or a target.

Requires the exact closed/audited32KiB40 case and the exact passed200 filter
gate. Copies the existing ELF and patched NBF byte for byte. No board access.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=Path('/home/coyang/zynq-parrot-linux-research')
BASELINE=ROOT/'research/resume-data-reuse-20261120/compact-thirtytwo-kib'
GATE=HERE/'scoped-mode0-validation/validation.json'
SOURCE200=ROOT/'research/resume-retention-matrix-20261120/burst-off200/session.json'
PREFIX='Vbsg_nonsynth_zynq_testbench'
MODEL40='77f76ae7527c2e9ed796fad48a8344e2dbbc10a5d90a69ccfb829e0bc2754ad5'
MODEL200='e52fa2473b3e35f0c14ae13973ec8ebdd7f0cbf9414ac49dae5e379b42230c3f'
ORIGINAL200='a654e3fdc1ecbed116f249350515f0967edbb68cf027ff1f1317c17f0e50785a'
ELF='f35e5da8dcb527cfa04c16edab0616f1f80a7715c9b05278500799c9b66393dd'
RUNTIME_NBF='18dbba12d432e6cfde94e7a16887d52f4e6edf0114b21a4fd227c0fbe4bc103d'
PINS={
    'session40':'ed7512587138883bc6044d30eeb3ce412d710a2d9111bf384f6bc992a929ec0e',
    'audit40':'41949658aa0ccab468a73358ef05d1105102f2aef371ac9baf95a4a24f826b4a',
    'gate200':'ba62705210c6970e2ba6f56836e720239274731e39bf716cc8c638ca02a3d7be',
    'build200':'c247b7c9579fad02bbef5ec75d85c6db89d1c718366b33d457fc73c28652f85b',
    'source200':'68edbecf3b012d73c9c926e7df2e690ed4ce887aa9307837859667091aff6b50',
}
TRACE_LIMIT=150*1024*1024
NATIVE_SECONDS=2400
HOST_GUARD_SECONDS=NATIVE_SECONDS+180


def require(value,message):
    if not value:raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def rec(path):
    path=Path(path)
    return {'path':str(path.resolve()),'bytes':path.stat().st_size,'sha256':sha(path)}


def verify(item,relocated=None):
    path=Path(relocated)if relocated is not None else Path(item['path'])
    require(path.is_file()and not path.is_symlink()and path.stat().st_size==item['bytes']
            and sha(path)==item['sha256'],'bound artifact missing/changed: '+str(path))
    return path


def pinned(path,name):
    require(sha(path)==PINS[name],'unapproved '+name+' manifest')
    return json.loads(Path(path).read_text())


def load_parser(audit):
    runner=verify(audit['frozen_runner']);helper=verify(audit['parser_import_helper'])
    require(audit['frozen_runner']['sha256']=='1b601b14bdbedf6c58a19baaa8e34e27f58b15fdf361d783080aa0f7ce8e1c41',
            'unexpected frozen compact parser')
    # Install the exact verified helper before loading the archived runner.
    # Only its pure parser/generator/NBF checks are used; its CLI is never run.
    spec=importlib.util.spec_from_file_location('patch_nbf_memory_records',helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sys.modules['patch_nbf_memory_records']=module
    spec=importlib.util.spec_from_file_location('frozen_natural32_parser',runner)
    parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
    return parser


def admit():
    source=pinned(BASELINE/'session.json','session40')
    audit=pinned(BASELINE/'dcache-audit/manifest.json','audit40')
    require(source['state']=='pass'and source['protocol']=='compact-v1'and source['footprint_kib']==32
            and source['physical_slots']==2 and source['logical_contexts']==4
            and source['blackparrot_revision']=='ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57'
            and source['model']['sha256']==MODEL40 and source['program']['elf']['sha256']==ELF
            and source['runtime_nbf']['sha256']==RUNTIME_NBF,'wrong closed32KiB40 source')
    require(audit['state']=='passed'and audit['complete_converter_eof']
            and audit['inputs_unchanged_after_analysis']
            and audit['complete_custom_guest_parser_recheck']
            and audit['independent_metadata_load_generator_recheck']
            and all(audit[key]==0 for key in ('analyzer_returncode','converter_returncode',
                       'maintained_checker_returncode','host_tests_returncode')),'baseline40 full audit incomplete')
    for item in audit['inputs'].values():verify(item)
    require(audit['inputs']['session']['sha256']==PINS['session40'],'audit/source session mismatch')
    for item in source['source'].values():verify(item)
    for key in ('elf','mem','nbf','symbol_file','disassembly'):verify(source['program'][key])
    for item in audit['model_admission_bindings'].values():verify(item)
    for item in audit['artifacts'].values():verify(item)
    for item in audit['model_rtl_source_conditions']:verify(item)
    for pair in audit['source_pairs']:verify(pair['retained'])
    parser=load_parser(audit)
    observations=parser.compact_guest_observations(Path(source['run_log']['path']).read_text(),32)
    require(observations==json.loads(Path(source['guest_observations']['path']).read_text()),
            'closed40 guest metadata differs from frozen parser')
    metadata=json.loads(Path(source['trace_metadata']['path']).read_text())
    require(metadata['expected_target_loads_by_context']==
            {str(c):parser.expected_target_loads(32,c)for c in range(4)},'independent target-load map changed')
    require(metadata['begin_pc']==source['program']['symbols']['resume_data_request_begin']
            and metadata['end_pc']==source['program']['symbols']['resume_data_request_end'],
            'boundary PCs differ from exact ELF')
    original=Path(source['program']['nbf']['path']).read_text()
    patched=parser.patch_config(original,int(source['program']['symbols']['resume_data_config'],16),32)
    require(hashlib.sha256(patched.encode()).hexdigest()==RUNTIME_NBF,'not the exact single32KiB footprint patch')

    gate=pinned(GATE,'gate200')
    require(gate['state']=='pass-no-data-reuse-admission'and gate['complete_ring_cycles']==1944
            and gate['required_signal_count']==105 and gate['accepted_event_streams_byte_identical']
            and gate['original_model_still_unchanged'] and gate['configured_memory_latency_ticks']==200
            and gate['model_l2_banks']==1 and gate['binary']['sha256']==MODEL200,
            '200 trace equivalence gate incomplete/wrong model')
    require(gate['build_manifest']['sha256']==PINS['build200'],'wrong200 build binding')
    build_path=verify(gate['build_manifest'],GATE.parent/'model/build.json')
    build=pinned(build_path,'build200')
    require(build['state']=='built-not-validated'and build['configured_memory_latency_ticks']==200
            and build['model_l2_banks']==1 and build['original_model']['sha256']==ORIGINAL200
            and build['baseline_relinked_model']['sha256']==ORIGINAL200
            and build['binary']==gate['binary'],'200 build provenance differs')
    allowed={PREFIX,PREFIX+'__ALL.a',PREFIX+'__Syms.cpp',PREFIX+'__Syms.o',PREFIX+'__Syms.d'}
    require(set(build['changed_files'])==allowed,'200 build changed evaluation files')
    before,after=build['original_archive_members'],build['final_archive_members']
    require(list(before)==list(after)and[k for k in before if before[k]!=after[k]]==[PREFIX+'__Syms.o'],
            '200 archive changed beyond trace registration')
    model=verify(gate['binary'],GATE.parent/'model'/PREFIX)
    old200=pinned(SOURCE200,'source200');configuration=old200['model']
    require(old200['state']=='complete'and old200['blackparrot_revision']==source['blackparrot_revision']
            and configuration['capture']=='off'and configuration['transport']=='full-burst'
            and configuration['configured_axi_memory_latency_ticks']==200
            and configuration['memory_queue_depth']==4 and configuration['axi_data_width_bits']==64
            and configuration['physical_threads']==2 and configuration['logical_contexts']==4
            and 'BP_ZYNQ_PREFETCH_TWO_BANKS'not in configuration['defines'],
            '200 source/configuration differs beyond approved service control')
    verify(configuration['binary']);verify(gate['old_session'])
    for key in ('old_report','scoped_report','old_events','scoped_events','run_log','stopped_fst','checker',
                'own_old200_baseline'):verify(gate[key])
    require(gate['old_events']['sha256']==gate['scoped_events']['sha256']
            =='536f21200d76458a73f6c4f88e3cca7d710d1ba8a95d6fbbb0b00d4be52bc0f9',
            '200 gate does not reproduce its OWN event stream')
    for item in (source['model'],source['runtime_nbf'],source['trace_metadata'],source['guest_observations']):verify(item)
    bindings={'baseline40_session':rec(BASELINE/'session.json'),'baseline40_audit':rec(BASELINE/'dcache-audit/manifest.json'),
              'gate200':rec(GATE),'build200':rec(build_path),'durable_model200':rec(model),
              'original200_session':rec(SOURCE200),'frozen_parser':audit['frozen_runner'],
              'parser_import_helper':audit['parser_import_helper']}
    return source,audit,metadata,observations,parser,model,bindings


def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')


def copy_bound(item,target):
    source=verify(item);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    verify(item,target)
    return rec(target)


def run_model(command,runtime,log,guard):
    env=os.environ.copy()
    for key in ('BSG_RUNTIME_PATCH_ADDR','BSG_RUNTIME_PATCH_VALUE','BSG_TRACE_TIMEOUT_S'):env.pop(key,None)
    env['LD_LIBRARY_PATH']='/home/coyang/zynq-parrot/install/lib:'+env.get('LD_LIBRARY_PATH','')
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(TRACE_LIMIT,TRACE_LIMIT))
    process=None;start=time.monotonic();last=start
    try:
        with log.open('w')as stream:
            process=subprocess.Popen(command,cwd=runtime,env=env,stdout=stream,stderr=subprocess.STDOUT,preexec_fn=limits)
            while process.poll()is None:
                now=time.monotonic()
                require(now-start<=guard,'native2400s+180s host guard exceeded')
                if now-last>=30:
                    fst=runtime/'dump.fst'
                    print('latency20032KiB elapsed_s=%d trace_bytes=%d'%(now-start,fst.stat().st_size if fst.exists() else 0),flush=True)
                    last=now
                time.sleep(1)
            return process.returncode,time.monotonic()-start
    finally:
        if process is not None and process.poll()is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()


def full_audit(output,source,audit,metadata):
    directory=output/'dcache-audit';directory.mkdir()
    retained={}
    for pair in audit['source_pairs']:
        item=pair['retained'];retained[Path(item['path']).name]=copy_bound(item,directory/'source'/Path(item['path']).name)
    analyzer=Path(retained['analyze_resume_data_reuse_vcd.py']['path'])
    converter=verify(audit['converter_binary'])
    command=[sys.executable,'-B',str(analyzer),'--metadata',str(output/'trace-metadata.json'),
             '--output',str(directory/'analysis.json'),'--events',str(directory/'events.jsonl')]
    save(directory/'command.json',{'converter':[str(converter),str(output/'runtime/dump.fst')],'analyzer':command})
    with(directory/'converter.stderr').open('w')as err,(directory/'analysis.log').open('w')as log:
        process=subprocess.Popen([str(converter),str(output/'runtime/dump.fst')],stdout=subprocess.PIPE,stderr=err)
        try:
            result=subprocess.run(command,stdin=process.stdout,stdout=log,stderr=subprocess.STDOUT,timeout=900)
            process.stdout.close();process.wait(timeout=10)
            require(result.returncode==process.returncode==0,'complete200 FST audit/conversion failed')
        finally:
            if process.poll()is None:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
    report=json.loads((directory/'analysis.json').read_text())
    require((directory/'converter.stderr').stat().st_size==0,'converter emitted a warning/error')
    require(report['validation']=='passed' and len(report['requests'])==64 and len(report['signals'])==105,
            'full200 request/tag audit incomplete')
    expected=metadata['expected_target_loads_by_context']
    for context in range(4):
        rows=[row for row in report['requests']if row['context']==context]
        require([r['epoch']for r in rows]==list(range(16))and
                [r['stats']['target_loads']for r in rows]==expected[str(context)],
                '200 request load counts differ from fixed-work source')
    manifest={'state':'passed','complete_converter_eof':True,'converter_returncode':process.returncode,
              'analyzer_returncode':result.returncode,'source':retained,'metadata':rec(output/'trace-metadata.json'),
              'fst':rec(output/'runtime/dump.fst'),'report':rec(directory/'analysis.json'),
              'events':rec(directory/'events.jsonl'),'converter_stderr':rec(directory/'converter.stderr'),
              'scope':'Conditional fixed-execution victim coverage only; no retained-data correctness/prefetch/FPGA projection.'}
    save(directory/'manifest.json',manifest)
    return rec(directory/'manifest.json')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--native-runtime-seconds',type=int,choices=(2400,),required=True,
                   help='explicit2400s control budget; source40 used1800s, no timed-work change')
    args=p.parse_args(argv);output=args.output.resolve()
    require(not output.exists(),'output must be new; retained evidence is never overwritten')
    require(shutil.disk_usage(output.parent if output.parent.exists() else ROOT).free>2*TRACE_LIMIT+128*1024*1024,
            'insufficient free space for bounded trace/event evidence')
    source,audit,metadata,old_observations,parser,model,bindings=admit()
    output.mkdir(parents=True);runtime=output/'runtime';runtime.mkdir()
    state={'state':'preparing','scope':'Same fixed32KiB workload, only model first response40to200 ticks; not Linux/FPGA.',
           'protocol':'compact-v1','footprint_kib':32,'physical_slots':2,'logical_contexts':4,'model_l2_banks':1,
           'blackparrot_revision':source['blackparrot_revision'],'model':rec(model),'admission':bindings,
           'native_runtime_seconds':args.native_runtime_seconds,'host_guard_seconds':HOST_GUARD_SECONDS,
           'baseline40_native_seconds':source['native_runtime_seconds'],'trace_limit_bytes':TRACE_LIMIT,
           'budget_reason':'Allow slower service control to complete stdout/terminal; native wall budgets are not the timed metric.',
           'configured_memory_latency_ticks':200,'baseline40_configured_memory_latency_ticks':40}
    manifest=output/'session.json';save(manifest,state)
    try:
        program={}
        for key in ('elf','mem','nbf','symbol_file','disassembly'):
            program[key]=copy_bound(source['program'][key],output/'program'/Path(source['program'][key]['path']).name)
        program['compile_command']=source['program']['compile_command'];program['symbols']=source['program']['symbols']
        state['program']=program
        state['source']={name:copy_bound(item,output/'source'/name)for name,item in source['source'].items()}
        state['frozen_parser']=copy_bound(audit['frozen_runner'],output/'source/frozen-runner.py')
        state['parser_import_helper']=copy_bound(audit['parser_import_helper'],output/'source/patch_nbf_memory_records.py')
        state['runtime_elf']=copy_bound(source['program']['elf'],runtime/'prog.riscv')
        state['runtime_nbf']=copy_bound(source['runtime_nbf'],runtime/'prog.nbf')
        copy_bound(source['trace_metadata'],output/'trace-metadata.json')
        state['trace_metadata']=rec(output/'trace-metadata.json')
        state['runner']=rec(__file__);shutil.copy2(__file__,output/'runner.py')
        command=[str(model),'+c_args=prog.nbf '+str(args.native_runtime_seconds*1000),'+bsg_trace=dump.fst']
        state.update(state='running',command=command);save(manifest,state)
        require(sha(model)==MODEL200,'selected200 model changed before launch')
        code,elapsed=run_model(command,runtime,runtime/'run.log',HOST_GUARD_SECONDS)
        state.update(exit_code=code,elapsed_seconds=elapsed,run_log=rec(runtime/'run.log'))
        if(runtime/'dump.fst').exists():state['stopped_fst']=rec(runtime/'dump.fst')
        save(manifest,state)
        checker=Path(state['source']['testing/check_run.py']['path'])
        with(runtime/'acceptance.log').open('w')as log:
            result=subprocess.run([sys.executable,'-B',str(checker),str(runtime/'run.log'),'--exit-code',str(code)],
                                  stdout=log,stderr=subprocess.STDOUT)
        state['acceptance']=rec(runtime/'acceptance.log')
        require(result.returncode==0,'whole200 execution failed maintained guest/host acceptance')
        observations=parser.compact_guest_observations((runtime/'run.log').read_text(),32)
        require(observations['regions']==old_observations['regions']and observations['stacks']==old_observations['stacks'],
                'only-latency control changed corpus/layout/checksum metadata')
        save(output/'guest-observations.json',observations);state['guest_observations']=rec(output/'guest-observations.json')
        require('stopped_fst'in state and 0<state['stopped_fst']['bytes']<TRACE_LIMIT,'missing/truncated200 FST')
        state['state']='execution-passed-auditing';save(manifest,state)
        state['full_access_audit']=full_audit(output,source,audit,metadata)
        for item in (state['program']['elf'],state['runtime_nbf'],state['model'],state['trace_metadata']):verify(item)
        state.update(state='pass-full-audit',complete_ring_cycles=observations['complete_ring_cycles'],
                     complete_execution_and_full_access_accepted=True)
        print(json.dumps({'state':state['state'],'complete_ring_cycles':state['complete_ring_cycles'],
                          'session':str(manifest),'scope':state['scope']},indent=2))
    except BaseException as error:
        state.update(state='failed',error=repr(error));raise
    finally:save(manifest,state)
    return 0


if __name__=='__main__':main()
