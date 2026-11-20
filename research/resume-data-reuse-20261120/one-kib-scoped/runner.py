#!/usr/bin/env python3
"""One checked lookup-reuse gate on the immutable full-burst capture-off40 model.

No RTL build or board operation. Invoke first for1KiB, then explicitly reuse
its program with --program-from only after the first trace is validated.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'linux-tests'))
from patch_nbf_memory_records import patch

MODEL_SESSION = ROOT / 'research/resume-retention-matrix-20261120/burst-off40/session.json'
MODEL_SHA = '85505d381643fca1a118c9e5d6930468e9bcce736ebfd0a926fb36419064af8b'
SCOPED_SHA = '77f76ae7527c2e9ed796fad48a8344e2dbbc10a5d90a69ccfb829e0bc2754ad5'
SCOPED_BUILD_SHA = '55c32689aa0dac158aa67c801fb3459de0ad40df1cc23b3b673f92b303c27f88'
SCOPED_VALIDATION_SHA = '2dad534ec94bc3036d6bd32f5674bea89c20227b8ba5b1ccd5dae53cfa664b5a'
REPEAT_ELF_SHA = 'cc97e23db7f56f59dd25be41b7e179d8643078fdee9d71e96d1ab3597216c204'
BP_REV = 'ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57'
PASS = '[BSG-PASS] checked nonresident data reuse ring lookup'
MASK = (1 << 64) - 1
TRACE_LIMIT = 150 * 1024 * 1024
DEPENDENCIES = ('testing/mt_resume_data_reuse_benchmark.c', 'testing/mt_seed.h',
                'linux-tests/resume_workload.h', 'testing/check_run.py')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def record(path):
    return {'path': str(path.resolve()), 'sha256': sha(path), 'bytes': path.stat().st_size}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def checked_copy(source, target, expected=None):
    expected = expected or sha(source)
    if sha(source) != expected:
        raise ValueError('source identity differs: ' + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if sha(source) != expected or sha(target) != expected:
        raise ValueError('source changed while copying: ' + str(source))
    return record(target)


def verify_record(item, relocated=None):
    """A relocation is allowed only where the caller explicitly defines it."""
    path = Path(relocated) if relocated is not None else Path(item['path'])
    if not path.is_file() or path.is_symlink() or sha(path) != item['sha256'] or path.stat().st_size != item['bytes']:
        raise ValueError('bound artifact missing/changed: ' + str(path))
    return path


def selected_model(scoped_validation=None):
    old = json.loads(MODEL_SESSION.read_text())
    model = Path(old['model']['binary']['path'])
    if (old['state'] != 'complete' or old['blackparrot_revision'] != BP_REV
            or old['model']['capture'] != 'off' or old['model']['transport'] != 'full-burst'
            or old['model']['configured_axi_memory_latency_ticks'] != 40 or sha(model) != MODEL_SHA):
        raise ValueError('immutable full-burst off40 model identity differs')
    if scoped_validation is None:
        return old, model, None
    scoped_validation = Path(scoped_validation).resolve()
    if sha(scoped_validation) != SCOPED_VALIDATION_SHA:
        raise ValueError('scoped validation is not the approved complete mode0 gate')
    gate = json.loads(scoped_validation.read_text())
    if (gate['state'] != 'pass-no-data-reuse-admission' or gate['complete_ring_cycles'] != 664
            or gate['required_signal_count'] != 105 or not gate['accepted_event_streams_byte_identical']
            or not gate['original_model_still_unchanged']):
        raise ValueError('scoped equivalence gate incomplete')
    if verify_record(gate['old_session']) != MODEL_SESSION.resolve():
        raise ValueError('scoped gate belongs to a different original session')
    if gate['build_manifest']['sha256'] != SCOPED_BUILD_SHA:
        raise ValueError('unapproved scoped build')
    # These two durable, exact relocations preserve the original RAM records;
    # arbitrary model path overrides and RAM-only execution are not admitted.
    build_path = verify_record(gate['build_manifest'], scoped_validation.parent / 'model/build.json')
    build = json.loads(build_path.read_text())
    prefix = 'Vbsg_nonsynth_zynq_testbench'
    allowed = {prefix, prefix+'__ALL.a', prefix+'__Syms.cpp', prefix+'__Syms.o', prefix+'__Syms.d'}
    if (build['state'] != 'built-not-validated' or set(build['changed_files']) != allowed
            or build['original_model']['sha256'] != MODEL_SHA
            or build['baseline_relinked_model']['sha256'] != MODEL_SHA
            or build['binary'] != gate['binary'] or build['binary']['sha256'] != SCOPED_SHA):
        raise ValueError('scoped build did not preserve the accepted model')
    before, after = build['original_archive_members'], build['final_archive_members']
    if list(before) != list(after) or [key for key in before if before[key] != after[key]] != [prefix+'__Syms.o']:
        raise ValueError('scoped archive changed beyond trace registration')
    for key in ('old_report', 'scoped_report', 'old_events', 'scoped_events', 'run_log', 'checker', 'stopped_fst'):
        verify_record(gate[key])
    if gate['old_events']['sha256'] != gate['scoped_events']['sha256']:
        raise ValueError('scoped full accepted event streams differ')
    previous = json.loads(Path(gate['old_report']['path']).read_text())
    current = json.loads(Path(gate['scoped_report']['path']).read_text())
    if (previous['validation'] != 'passed' or current['validation'] != 'passed'
            or previous['stats'] != current['stats'] or len(current['signals']) != 105):
        raise ValueError('scoped access audit incomplete')
    model = verify_record(gate['binary'], scoped_validation.parent / 'model' / prefix)
    admission = {'validation':record(scoped_validation), 'original_build_binding':gate['build_manifest'],
                 'durable_build':record(build_path), 'original_binary_binding':gate['binary'],
                 'durable_binary':record(model), 'original_model_sha256':MODEL_SHA,
                 'event_stream_sha256':gate['scoped_events']['sha256'],
                 'scope':'Approved trace-only equivalence for this exact copied model; no data-reuse result yet.'}
    return old, model, admission


def reuse_program(path, repeat, kib, model_sha, sources):
    earlier = json.loads(Path(path).read_text())
    if repeat:
        if (kib != 1 or model_sha != SCOPED_SHA or earlier['state'] != 'failed'
                or earlier['footprint_kib'] != 1 or earlier['model']['sha256'] != MODEL_SHA
                or earlier['program']['elf']['sha256'] != REPEAT_ELF_SHA):
            raise ValueError('repeat requires the exact failed1KiB program and admitted scoped model')
    elif (earlier['state'] != 'pass' or earlier['footprint_kib'] != 1
          or earlier['model']['sha256'] != model_sha):
        raise ValueError('first program requires completed accepted1KiB gate on the selected model')
    if earlier['blackparrot_revision'] != BP_REV or set(earlier['source']) != set(sources):
        raise ValueError('program source identity differs')
    verify_record(earlier['model'])
    for name, source in sources.items():
        verify_record(earlier['source'][name])
        if source['sha256'] != earlier['source'][name]['sha256']:
            raise ValueError('source changed since first ELF: ' + name)
    for key in ('elf', 'mem', 'nbf', 'symbol_file', 'disassembly'):
        verify_record(earlier['program'][key])
    verify_record(earlier['runtime_nbf'])
    symbols = earlier['program']['symbols']
    patched = patch_config(Path(earlier['program']['nbf']['path']).read_text(),
                           int(symbols['resume_data_config'],16), 1)
    if hashlib.sha256(patched.encode()).hexdigest() != earlier['runtime_nbf']['sha256']:
        raise ValueError('earlier runtime NBF is not the exact1KiB config patch')
    return earlier


def mix(x):
    x ^= x >> 30
    x = x * 0xbf58476d1ce4e5b9 & MASK
    x ^= x >> 27
    x = x * 0x94d049bb133111eb & MASK
    return x ^ (x >> 31)


def expected_target_loads(kib, actor):
    """Logical generator/probe counts only; no physical-address prediction."""
    count, records = kib * 64, kib * 32
    slots = [0] * count
    for key in range(1, records + 1):
        slot = mix(key) % count
        while slots[slot]:
            slot = (slot + 1) % count
        slots[slot] = key
    seed = 0x95cba137 + actor * 0x9e3779b9
    result = []
    for epoch in range(16):
        loads = 0
        for query in range(64):
            key = 1 + mix(seed + epoch * 64 + query) % records + (records if query & 7 == 7 else 0)
            slot = mix(key) % count
            for _ in range(count):
                loads += 1
                if not slots[slot]:
                    break
                if slots[slot] == key:
                    loads += 1  # Separate volatile value load after the key.
                    break
                slot = (slot + 1) % count
            else:
                raise ValueError('logical lookup table unexpectedly full')
        result.append(loads)
    return result


def patch_config(text, address, kib):
    if kib not in (1, 32) or address < 0x80000000 or address & 7:
        raise ValueError('only aligned initialized1/32KiB config words are allowed')
    lines = text.splitlines()
    if '\n'.join(lines) + '\n' != text:
        raise ValueError('NBF must use canonical newline-terminated records')
    changed = patch(lines, [(address, MASK, kib)])
    if patch(changed, [(address, kib, MASK)]) != lines:
        raise ValueError('configuration patch is not exactly reversible')
    if sum(a != b for a, b in zip(lines, changed)) != 1:
        raise ValueError('configuration patch changed more than one record')
    return '\n'.join(changed) + '\n'


def read_symbols(nm_text):
    required = ('resume_data_config', 'resume_data_request_begin', 'resume_data_request_end',
                'resume_data_warm_begin', 'resume_data_timed_begin', 'resume_data_timed_end')
    symbols = {}
    for name in required:
        matches = re.findall(r'^([0-9a-fA-F]+) ([A-Za-z]) ' + name + '$', nm_text, re.M)
        if len(matches) != 1:
            raise ValueError('missing/ambiguous ELF symbol: ' + name)
        value, kind = matches[0]
        if kind not in ('Dd' if name == 'resume_data_config' else 'Tt'):
            raise ValueError('wrong ELF symbol kind: ' + name)
        symbols[name] = int(value, 16)
    return symbols


def guest_observations(text, kib):
    text = text.replace('\r', '')
    config = re.findall(r'^DATA_REUSE_CONFIG lookup actors=4 resident=2 warm=8 timed=8 kib=(0x[0-9a-fA-F]+)$', text, re.M)
    if len(config) != 1 or int(config[0], 16) != kib or text.count(PASS) != 1:
        raise ValueError('missing exact config/custom completion marker')
    core = re.search(r'\bCORE(?:\[\d+\])?\s+PASS\b', text)
    if core is None or text.index(PASS) > core.start():
        raise ValueError('custom completion must precede CORE PASS')
    regions = [dict(context=int(a), base=b, bytes=int(c, 16), runs=int(d, 16), checksum=e)
               for a,b,c,d,e in re.findall(r'^DATA_REUSE_REGION actor=([0-3]) base=(0x[0-9a-fA-F]+) bytes=(0x[0-9a-fA-F]+) runs=(0x[0-9a-fA-F]+) sum=(0x[0-9a-fA-F]+)$', text, re.M)]
    if [r['context'] for r in regions] != list(range(4)) or any(r['bytes'] != kib * 1024 or r['runs'] != 16 for r in regions):
        raise ValueError('private region/actor/run counts differ')
    for i, a in enumerate(regions):
        for b in regions[i + 1:]:
            if max(int(a['base'],16),int(b['base'],16)) < min(int(a['base'],16)+a['bytes'],int(b['base'],16)+b['bytes']):
                raise ValueError('private corpus regions overlap')
    epochs = [dict(context=int(a), epoch=int(b,16), begin=int(c,16), end=int(d,16))
              for a,b,c,d in re.findall(r'^DATA_REUSE_EPOCH actor=([0-3]) epoch=(0x[0-9a-fA-F]+) begin=(0x[0-9a-fA-F]+) end=(0x[0-9a-fA-F]+)$', text, re.M)]
    if [(e['epoch'],e['context']) for e in epochs] != [(e,a) for e in range(16) for a in range(4)]:
        raise ValueError('missing/duplicate/out-of-order actor epochs')
    bounds = re.findall(r'^DATA_REUSE_PHASES warm_begin=(0x[0-9a-fA-F]+) timed_begin=(0x[0-9a-fA-F]+) timed_end=(0x[0-9a-fA-F]+) cycles=(0x[0-9a-fA-F]+)$', text, re.M)
    if len(bounds) != 1:
        raise ValueError('missing unique ring phase bounds')
    warm, begin, end, cycles = map(lambda x: int(x,16), bounds[0])
    if not 0 < warm < begin < end or cycles != end - begin:
        raise ValueError('nonmonotonic complete ring interval')
    previous = warm
    for row in epochs:
        if not previous < row['begin'] < row['end']:
            raise ValueError('request chronology is not a serialized4-context ring')
        if row['epoch'] < 8 and row['end'] >= begin or row['epoch'] >= 8 and not begin <= row['begin'] < row['end'] <= end:
            raise ValueError('request falls outside declared warm/timed phase')
        previous = row['end']
    return {'regions':regions, 'epochs':epochs, 'warm_begin':warm, 'timed_begin':begin,
            'timed_end':end, 'complete_ring_cycles':cycles, 'timed_ring_laps':8,
            'timed_requests':32, 'timed_context_switches':32,
            'scope':'Checked complete bare-metal ring interval; not Linux or FPGA performance.'}


def command(command, cwd, log):
    with log.open('w') as stream:
        subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--footprint-kib', type=int, choices=(1,32), default=1)
    reuse = p.add_mutually_exclusive_group()
    reuse.add_argument('--program-from', type=Path, help='first accepted session.json; exact ELF reuse required for32KiB')
    reuse.add_argument('--repeat-program-from', type=Path, help='repeat exact failed1KiB ELF only with the approved scoped model')
    p.add_argument('--scoped-validation', type=Path, help='approved complete mode0 gate and durable copied model binding')
    p.add_argument('--bp', type=Path, default=Path('/home/coyang/bp-linux-demand-copy-control'))
    p.add_argument('--toolchain', type=Path, default=Path('/home/coyang/zynq-parrot/install'))
    a = p.parse_args(argv)
    output = a.output.resolve()
    if output.exists(): p.error('output must be new; no retained evidence overwrite')
    if a.footprint_kib == 32 and not a.program_from: p.error('validate1KiB and reuse its exact program before32KiB')
    if a.repeat_program_from and (a.footprint_kib != 1 or not a.scoped_validation):
        p.error('failed-program repeat is only for1KiB with --scoped-validation')
    if shutil.disk_usage(output.parent if output.parent.exists() else ROOT).free < 2 * TRACE_LIMIT + 128 * 1024 * 1024:
        p.error('insufficient free workspace for bounded trace and recovery margin')
    old, model, scoped_admission = selected_model(a.scoped_validation)
    if a.scoped_validation and not (a.repeat_program_from or a.program_from):
        p.error('scoped model requires exact program reuse; no new ELF compilation')
    bp = a.bp.resolve()
    if not (bp/'.git').exists() or subprocess.check_output(['git','-C',str(bp),'rev-parse','HEAD'],text=True).strip()!=BP_REV:
        raise ValueError('selected NBF converter must belong to exact initialized FFC checkout')
    tool = bp/'bp_common/software/py/nbf.py'
    expected_tool = subprocess.check_output(['git','-C',str(bp),'show',BP_REV+':bp_common/software/py/nbf.py'])
    if sha(tool) != hashlib.sha256(expected_tool).hexdigest(): raise ValueError('NBF converter differs from immutable FFC source')
    output.mkdir(parents=True)
    state={'state':'preparing','scope':'Offline data-reuse observability gate only; no extra-capacity/prefetch speedup claim.',
           'model_session':record(MODEL_SESSION),'model':record(model),'blackparrot_revision':BP_REV,
           'physical_slots':2,'logical_contexts':4,'footprint_kib':a.footprint_kib,
           'trace_limit_bytes':TRACE_LIMIT,'native_runtime_seconds':600,'nbf_converter':record(tool)}
    if scoped_admission is not None:state['scoped_model_admission']=scoped_admission
    manifest=output/'session.json';save(manifest,state)
    try:
        source=output/'source';program=output/'program';runtime=output/'runtime'
        program.mkdir();runtime.mkdir()
        records={name:checked_copy(ROOT/name,source/name)for name in DEPENDENCIES}
        checked_copy(Path(__file__).resolve(),output/'runner.py')
        state['source']=records
        elf=program/'benchmark.riscv';mem=program/'prog.mem';nbf=program/'prog.nbf';install=a.toolchain.resolve()
        reuse_path = a.program_from or a.repeat_program_from
        if reuse_path:
            earlier=reuse_program(reuse_path, bool(a.repeat_program_from), a.footprint_kib, sha(model), records)
            for key,target in (('elf',elf),('mem',mem),('nbf',nbf)):
                checked_copy(Path(earlier['program'][key]['path']),target,earlier['program'][key]['sha256'])
            compile_command=earlier['program']['compile_command']
            state['repeat_program_from' if a.repeat_program_from else 'program_from']=record(reuse_path)
        else:
            compile_command=[str(install/'bin/riscv64-unknown-elf-gcc'),'-O2','-I'+str(install/'riscv64-unknown-elf/include'),
                '--specs='+str(install/'riscv64-unknown-elf/lib/dramfs.specs'),'--specs='+str(install/'riscv64-unknown-elf/lib/perch.specs'),
                '-DNUM_THREADS=2','-DBP_NUM_THREADS=2','-DBP_NUM_CONTEXTS=4','-DBP_RESUME_ZLIB=0',
                '-o',str(elf),str(source/'testing/mt_resume_data_reuse_benchmark.c')]
            command(compile_command,ROOT,program/'compile.log')
            command([str(install/'bin/riscv64-unknown-elf-objcopy'),'-O','verilog',str(elf),str(mem)],ROOT,program/'objcopy.log')
            mem.write_text(mem.read_text().replace('@8','@0'))
            with nbf.open('w')as stream:
                subprocess.run([sys.executable,str(tool),'--skip_zeros','--keep_mem_zeros','--mem',str(mem),'--ncpus','1','--config','--debug'],stdout=stream,check=True)
        nm=subprocess.check_output([str(install/'bin/riscv64-unknown-elf-nm'),'-n',str(elf)],text=True);(program/'symbols.txt').write_text(nm);symbols=read_symbols(nm)
        disassembly=subprocess.check_output([str(install/'bin/riscv64-unknown-elf-objdump'),'-d',str(elf)],text=True);(program/'disassembly.txt').write_text(disassembly)
        state['program']={'elf':record(elf),'mem':record(mem),'nbf':record(nbf),'compile_command':compile_command,'symbols':{k:hex(v)for k,v in symbols.items()},'symbol_file':record(program/'symbols.txt'),'disassembly':record(program/'disassembly.txt')};save(manifest,state)
        checked_copy(elf,runtime/'prog.riscv');(runtime/'prog.nbf').write_text(patch_config(nbf.read_text(),symbols['resume_data_config'],a.footprint_kib))
        state['runtime_nbf']=record(runtime/'prog.nbf')
        cmd=[str(model),'+c_args=prog.nbf 600000','+bsg_trace=dump.fst'];state['command']=cmd;save(runtime/'command.json',cmd)
        if sha(model) != state['model']['sha256']:
            raise ValueError('selected model changed after admission')
        env=os.environ.copy()
        for key in ('BSG_RUNTIME_PATCH_ADDR','BSG_RUNTIME_PATCH_VALUE','BSG_TRACE_TIMEOUT_S'): env.pop(key,None)
        env['LD_LIBRARY_PATH']=str(install/'lib')+':'+env.get('LD_LIBRARY_PATH','')
        def limits():
            resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(TRACE_LIMIT,TRACE_LIMIT))
        state['state']='running';save(manifest,state);start=time.monotonic();last=start
        with (runtime/'run.log').open('w')as stream:
            process=subprocess.Popen(cmd,cwd=runtime,env=env,stdout=stream,stderr=subprocess.STDOUT,preexec_fn=limits)
            while process.poll()is None:
                now=time.monotonic()
                if now-start>780:
                    process.terminate()
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                    raise ValueError('host guard exceeded after native600s budget')
                if now-last>=30:
                    fst=runtime/'dump.fst';print('running elapsed_s=%d trace_bytes=%d'%(now-start,fst.stat().st_size if fst.exists()else 0),flush=True);last=now
                time.sleep(1)
            code=process.returncode
        state['exit_code']=code;state['elapsed_seconds']=time.monotonic()-start
        state['run_log']=record(runtime/'run.log');fst=runtime/'dump.fst'
        # A stopped process alone does not establish a complete FST footer:
        # the hard file limit can terminate its writer mid-block.
        if fst.exists():state['stopped_fst']=record(fst)
        save(manifest,state)
        try:
            command([sys.executable,str(source/'testing/check_run.py'),str(runtime/'run.log'),'--exit-code',str(code)],ROOT,runtime/'acceptance.log')
        finally:
            if (runtime/'acceptance.log').exists():state['acceptance']=record(runtime/'acceptance.log')
        if not fst.is_file()or not 0<fst.stat().st_size<TRACE_LIMIT:raise ValueError('missing/incomplete/oversize trace')
        observations=guest_observations((runtime/'run.log').read_text(errors='replace'),a.footprint_kib);save(output/'guest-observations.json',observations)
        metadata={'begin_pc':hex(symbols['resume_data_request_begin']),'end_pc':hex(symbols['resume_data_request_end']),
                  'warmup_requests':8,'timed_requests':8,'regions':[{'context':r['context'],'base':r['base'],'bytes':r['bytes']}for r in observations['regions']],
                  'expected_target_loads_by_context':{str(actor):expected_target_loads(a.footprint_kib,actor)for actor in range(4)}}
        save(output/'trace-metadata.json',metadata)
        state.update(state='pass',guest_observations=record(output/'guest-observations.json'),trace_metadata=record(output/'trace-metadata.json'))
        print(json.dumps({'state':'pass','complete_ring_cycles':observations['complete_ring_cycles'],'elf_sha256':sha(elf),'trace_bytes':fst.stat().st_size,'metadata':str(output/'trace-metadata.json')},indent=2))
    except BaseException as error:
        state.update(state='failed',error=repr(error));raise
    finally:save(manifest,state)
    return 0


if __name__=='__main__':main()
