#!/usr/bin/env python3
"""Latency200 host-only copy/relink and its OWN old200 mode-0 equivalence gate.

Never elaborates RTL, recompiles a target program, modifies the original model,
or admits the new data-reuse workload. Every output directory must be new.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = Path('/home/coyang/zynq-parrot-linux-research')
OLD = REPO / 'research/resume-retention-matrix-20261120/burst-off200'
AUDIT = REPO / 'research/resume-data-reuse-20261120/dcache-observability'
PREFIX = 'Vbsg_nonsynth_zynq_testbench'
SYMS = PREFIX + '__Syms'
MODEL_SHA = 'a654e3fdc1ecbed116f249350515f0967edbb68cf027ff1f1317c17f0e50785a'
SYMS_SHA = '0b18a9494fc274cd95333648cba1480ee4beb9f8ac887ff755366512e9e4c687'
BUILD_LOG_SHA = '06711afa3d0ef07210670367ae19ec2bb6bc80f4fb596dcdd3426c5e6dcec748'
HOST_OBJECTS = ('ps.o', 'main.o', 'bsg_nonsynth_dpi_clock_gen.o', 'verilated.o',
                'verilated_dpi.o', 'verilated_fst_c.o', 'verilated_threads.o')
TRACE_LIMIT = 150 * 1024 * 1024
EXPECTED_CYCLES = 1944
EXPECTED_LATENCY = 200
OLD200_AUDIT = HERE / 'old200-audit'
SESSION_SHA = '68edbecf3b012d73c9c926e7df2e690ed4ce887aa9307837859667091aff6b50'
ARCHIVE_SHA = 'dd1448b39780f5648007f8f0d5d3ee30802ce3b1b6fa18148b7b4fa7e8495914'
INVENTORY_SHA = 'd81d77b7614a56afa4f577bb1c759ba151de7f4960aac8d6bb18951c78f0aed4'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def rec(path):
    path = Path(path)
    return dict(path=str(path.resolve()), bytes=path.stat().st_size, sha256=sha(path))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def require(value, message):
    if not value:
        raise ValueError(message)


def tree(path):
    """Bind source, headers, objects and binary; omit only disposable PCH blobs."""
    result = {}
    for item in sorted(Path(path).rglob('*')):
        require(not item.is_symlink(), 'generated input contains symlink: ' + str(item))
        if item.is_file() and not item.name.endswith('.gch'):
            result[str(item.relative_to(path))] = rec(item)
    return result


def run(argv, cwd, stem):
    save(str(stem) + '.argv.json', argv)
    with Path(str(stem) + '.log').open('w') as stream:
        subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)


def archive_members(path):
    names = subprocess.check_output(['ar', 't', str(path)], text=True).splitlines()
    require(len(names) == len(set(names)), 'duplicate archive member names')
    return {name: hashlib.sha256(subprocess.check_output(['ar', 'p', str(path), name])).hexdigest()
            for name in names}


def original_session():
    require(sha(OLD / 'session.json') == SESSION_SHA, 'original200 session changed')
    old = json.loads((OLD / 'session.json').read_text())
    model = old['model']
    require(old['state'] == 'complete' and old['blackparrot_revision'] ==
            'ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57', 'wrong original200 source')
    require(model['binary']['sha256'] == MODEL_SHA and model['capture'] == 'off'
            and model['transport'] == 'full-burst' and model['trace'] == 'FST'
            and model['configured_axi_memory_latency_ticks'] == EXPECTED_LATENCY
            and model['memory_queue_depth'] == 4 and model['axi_data_width_bits'] == 64
            and model['physical_threads'] == 2 and model['logical_contexts'] == 4,
            'original200 configuration differs')
    require('BP_ZYNQ_PREFETCH_TWO_BANKS' not in model['defines'],
            'this control is source-bound to the one-L2-bank model')
    return old


def old200_baseline():
    """Reuse the already audited *200* trace, never a40 count/timestamp oracle."""
    manifest = json.loads((OLD200_AUDIT / 'manifest.json').read_text())
    require(manifest['state'] == 'passed-retained-old200' and manifest['complete_converter_eof'],
            'retained old200 full-access baseline is incomplete')
    require(manifest['old_session']['sha256'] == SESSION_SHA,
            'baseline audit belongs to another session')
    for key in ('report', 'events', 'analyzer', 'clock_helper'):
        item = manifest[key]
        require(sha(Path(item['path'])) == item['sha256'], 'old200 baseline binding changed: ' + key)
    report = json.loads(Path(manifest['report']['path']).read_text())
    require(report['validation'] == 'passed', 'old200 baseline tag/cache audit failed')
    return manifest, report


def commands():
    log = OLD / 'model/build.log'
    require(sha(log) == BUILD_LOG_SHA, 'original compiler/link log changed')
    lines = log.read_text().splitlines()
    compile_lines = [line for line in lines if line.startswith('g++ ') and
                     ('-o ' + SYMS + '.o ') in line]
    link_lines = [line for line in lines if line.startswith('g++ ') and
                  line.rstrip().endswith('-o ' + PREFIX)]
    require(len(compile_lines) == len(link_lines) == 1, 'ambiguous original host commands')
    compiler, linker = shlex.split(compile_lines[0]), shlex.split(link_lines[0])
    for command in (compiler, linker):
        require(not set(command) & {'|', '&&', ';', '>', '2>&1'}, 'shell syntax in argv')
    require(compiler[-4:] == ['-c', '-o', SYMS + '.o', SYMS + '.cpp'], 'wrong compile output')
    require('-DVM_TRACE=1' in compiler and '-DVM_TRACE_FST=1' in compiler,
            'TRACE=1 FST flags absent')
    require('-DBP_AXI_MEM_READ_LATENCY=200' in compiler and
            '-DBP_AXI_MEM_READ_LATENCY=40' not in compiler,
            'wrong original memory-model latency')
    objects = [arg for arg in linker if arg.endswith(('.o', '.a'))]
    require(objects == list(HOST_OBJECTS) + [PREFIX + '__ALL.a'], 'unexpected link objects')
    # GCC accepted an include *alias* backed only by alias.gch in the original
    # build. Without that disposable blob, parse the actual source header used
    # to create it. Require identical preprocessing/compiler flags first.
    header = PREFIX + '__pch.h'
    alias = header + '.slow'
    pch_lines = [line for line in lines if line.startswith('g++ ') and
                 line.rstrip().endswith('-x c++-header ' + header + ' -o ' + alias + '.gch')]
    require(len(pch_lines) == 1, 'ambiguous original slow-PCH creation command')
    pch = shlex.split(pch_lines[0])
    require(pch[-5:] == ['-x', 'c++-header', header, '-o', alias + '.gch'],
            'unexpected PCH input/output')
    require(compiler[-6:] == ['-include', alias, '-c', '-o', SYMS + '.o', SYMS + '.cpp'],
            'unexpected original PCH include alias')
    require(pch[:-5] == compiler[:-6], 'slow PCH and Syms compiler flags differ')
    original_compiler = list(compiler)
    compiler[-5] = header
    binding = dict(original_compile_argv=original_compiler, original_pch_creation_argv=pch,
                   original_include_alias=alias, textual_include_header=header,
                   identical_compiler_and_preprocessor_prefix=True)
    return compiler, linker, binding


def build(args):
    original, output = args.original.resolve(), args.output.resolve()
    require(not output.exists(), 'output must be new')
    require(original.is_dir(), 'preserved generated directory unavailable')
    require(sha(original / PREFIX) == MODEL_SHA, 'original generated binary is not immutable model')
    require(sha(OLD / 'model' / PREFIX) == MODEL_SHA, 'durable immutable model changed')
    require(sha(original / (SYMS + '.cpp')) == SYMS_SHA, 'generated Syms source changed')
    original_session()
    require(sha(original / (PREFIX + '__ALL.a')) == ARCHIVE_SHA, 'original200 archive changed')
    inventory_path = HERE / 'source-review/generated-inventory.json'
    require(sha(inventory_path) == INVENTORY_SHA, 'reviewed generated inventory changed')
    inventory = json.loads(inventory_path.read_text())
    allow = json.loads((HERE / 'required-signals.json').read_text())
    names = allow['canonical_names_verbatim']
    _, frozen = old200_baseline()
    require(len(names) == len(set(names)) == 105 and
            set(names) == set(frozen['signals'].values()), 'allowlist differs from validated signals')
    for item in allow['reviewed_runtime_sources']:
        require(sha(item['path']) == item['sha256'], 'reviewed Verilator runtime changed')
    before = tree(original)
    require({name:item['sha256'] for name,item in before.items()} ==
            {item['name']:item['sha256'] for item in inventory['files']},
            'original200 generated files differ from reviewed inventory')
    space = shutil.disk_usage(output.parent if output.parent.exists() else original.parent).free
    require(space > sum(item['bytes'] for item in before.values()) + 128 * 1024 * 1024,
            'insufficient output filesystem space')
    compiler, linker, pch_binding = commands()
    require((original / pch_binding['textual_include_header']).is_file(),
            'original textual PCH source header missing')
    output.mkdir(parents=True)
    evidence = output / 'evidence'; evidence.mkdir()
    obj = output / 'obj'
    state = dict(state='copying', scope='Host trace filtering only; no RTL elaboration or target execution.',
                 original_root=str(original), original_model=rec(original / PREFIX),
                 driver=rec(__file__), allowlist=rec(HERE / 'required-signals.json'),
                 original_build_log=rec(OLD / 'model/build.log'), original_files=before,
                 textual_pch_binding=pch_binding,
                 textual_pch_source=rec(original / pch_binding['textual_include_header']),
                 original_session=rec(OLD / 'session.json'), generated_inventory=rec(inventory_path),
                 configured_memory_latency_ticks=EXPECTED_LATENCY, model_l2_banks=1,
                 platform_scope='One-L2-bank synthetic model; physical two-bank FPGA is a separate platform.')
    manifest = evidence / 'build.json'
    save(manifest, state)
    try:
        shutil.copytree(original, obj, ignore=shutil.ignore_patterns('*.gch'))
        copied = tree(obj)
        require({k:v['sha256'] for k,v in copied.items()} ==
                {k:v['sha256'] for k,v in before.items()}, 'copy changed generated input bytes')
        archive = obj / (PREFIX + '__ALL.a')
        members = archive_members(archive)
        require(SYMS + '.o' in members, 'archive has no Syms object')
        # A baseline direct relink proves that these exact objects reconstruct
        # the accepted executable before introducing any host trace change.
        run(linker, obj, evidence / 'baseline-link')
        require(sha(obj / PREFIX) == MODEL_SHA, 'untouched direct relink did not reproduce accepted binary')
        state['baseline_relinked_model'] = rec(obj / PREFIX)
        source = obj / (SYMS + '.cpp')
        needle = '        __Vm_modelp->trace(__Vm_dumperp, 0, 0);\n'
        text = source.read_text()
        require(text.count(needle) == 1, 'ambiguous trace registration point')
        insertion = ('        // Host-only observation filter; target evaluation is unchanged.\n' +
                     ''.join('        __Vm_dumperp->dumpvars(1, ' + json.dumps(name) + ');\n'
                             for name in names))
        source.write_text(text.replace(needle, needle + insertion))
        (evidence / 'inserted-filter.txt').write_text(insertion)
        run(compiler, obj, evidence / 'compile-syms')
        run(['ar', 'rcs', archive.name, SYMS + '.o'], obj, evidence / 'replace-syms')
        changed_members = archive_members(archive)
        require(list(members) == list(changed_members), 'archive order/membership changed')
        require([name for name in members if members[name] != changed_members[name]] == [SYMS + '.o'],
                'archive changed beyond Syms.o')
        run(linker, obj, evidence / 'filtered-link')
        after = tree(obj)
        permitted = {SYMS + '.cpp', SYMS + '.o', SYMS + '.d', PREFIX + '__ALL.a', PREFIX}
        require(set(after) == set(before), 'host build created/deleted unexpected generated files')
        changes = [name for name in before if before[name]['sha256'] != after[name]['sha256']]
        require(set(changes) <= permitted and SYMS + '.cpp' in changes and SYMS + '.o' in changes,
                'host build changed other objects/generated evaluation files')
        require({k:v['sha256'] for k,v in tree(original).items()} ==
                {k:v['sha256'] for k,v in before.items()}, 'original model directory changed')
        require(sha(OLD / 'model' / PREFIX) == MODEL_SHA, 'durable original model changed')
        state.update(state='built-not-validated', changed_files=changes, final_files=after,
                     original_archive_members=members, final_archive_members=changed_members,
                     binary=rec(obj / PREFIX), compiler=compiler, linker=linker,
                     compiler_binary=rec(Path(shutil.which(compiler[0])).resolve()))
        print(json.dumps({'state':state['state'], 'manifest':str(manifest),
                          'binary':state['binary'], 'next':'separate validate-mode0 command only; no data-reuse admission'}, indent=2))
    except BaseException as error:
        state.update(state='failed', error=repr(error))
        raise
    finally:
        save(manifest, state)


def audit(fst, label, output, converter, analyzer):
    print('auditing complete %s trace (streaming, no VCD file)' % label, flush=True)
    with (output / (label + '-audit.log')).open('w') as log:
        source = subprocess.Popen([converter, str(fst)], stdout=subprocess.PIPE, stderr=log)
        try:
            result = subprocess.run([sys.executable, str(analyzer), '--output',
                                     str(output / (label + '-audit.json')), '--events',
                                     str(output / (label + '-events.jsonl'))],
                                    stdin=source.stdout, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=1200)
            source.stdout.close()
            source.wait(timeout=30)
            require(result.returncode == source.returncode == 0, label + ' full trace audit failed')
        finally:
            if source.poll() is None:
                source.terminate()
                try: source.wait(timeout=10)
                except subprocess.TimeoutExpired: source.kill(); source.wait()
    return json.loads((output / (label + '-audit.json')).read_text())


def mode0_values(text):
    require(re.findall(r'^Mode:\s+(0x[0-9a-fA-F]+)$', text, re.M) == ['0x0000000000000000'],
            'mode differs from old200 control')
    cycles = re.findall(r'^Resume cycles:\s+(0x[0-9a-fA-F]+)$', text, re.M)
    require(len(cycles) == 1 and int(cycles[0], 16) == EXPECTED_CYCLES,
            'mode-0 cycles differ from old200')
    for field in ('Prefix operations', 'Prefix checksum'):
        values = re.findall('^' + field + r':\s+(0x[0-9a-fA-F]+)$', text, re.M)
        require(len(values) == 1 and int(values[0], 16) == 0x60, field + ' differs')
    return EXPECTED_CYCLES


def compare_own200_audit(scoped_report, scoped_events, expected_names, baseline, baseline_report):
    require(scoped_report['validation'] == baseline_report['validation'] == 'passed',
            'old200/scoped cache audit incomplete')
    require(set(scoped_report['signals'].values()) == set(expected_names),
            'required scoped signal names differ')
    require(scoped_report['stats'] == baseline_report['stats'],
            'full access/tag/fill statistics differ from own old200 baseline')
    require(sha(scoped_events) == baseline['events']['sha256'],
            'full accepted event stream differs from own old200 baseline')


def validate(args):
    output = args.output.resolve()
    require(not output.exists(), 'validation output must be new')
    built = json.loads(args.build.read_text())
    require(built['state'] == 'built-not-validated', 'require completed scoped build manifest')
    binary = Path(built['binary']['path'])
    require(sha(binary) == built['binary']['sha256'], 'scoped binary changed')
    old = original_session()
    mode = next(row for row in old['runs'] if row['mode'] == 0)
    require(mode['state'] == 'pass' and mode['resume_core_global_cycles'] == EXPECTED_CYCLES,
            'wrong old mode-0 control')
    for key in ('elf', 'nbf', 'fst'):
        require(sha(mode[key]['path']) == mode[key]['sha256'], 'old mode-0 input changed: ' + key)
    frozen_manifest = json.loads((AUDIT / 'manifest.json').read_text())
    require(frozen_manifest['state'] == 'complete_bounded_observability_gate',
            'frozen auditor validation not complete')
    for item in frozen_manifest['analyzer_sources']:
        require(sha(item['path']) == item['sha256'], 'frozen auditor source changed')
    baseline, baseline_report = old200_baseline()
    analyzer = AUDIT / 'analyzer/analyze_resume_data_reuse_vcd.py'
    require(sha(HERE / 'required-signals.json') == built['allowlist']['sha256'],
            'allowlist changed since scoped build')
    converter = shutil.which('fst2vcd')
    require(converter, 'fst2vcd unavailable')
    require(shutil.disk_usage(output.parent if output.parent.exists() else REPO).free >
            TRACE_LIMIT + 64 * 1024 * 1024, 'insufficient validation filesystem space')
    output.mkdir(parents=True)
    runtime = output / 'runtime'; runtime.mkdir()
    shutil.copy2(mode['elf']['path'], runtime / 'prog.riscv')
    shutil.copy2(mode['nbf']['path'], runtime / 'prog.nbf')
    checker = output / 'check_run.py'; shutil.copy2(REPO / 'testing/check_run.py', checker)
    env = os.environ.copy()
    for key in ('BSG_RUNTIME_PATCH_ADDR', 'BSG_RUNTIME_PATCH_VALUE', 'BSG_TRACE_TIMEOUT_S'):
        env.pop(key, None)
    env['LD_LIBRARY_PATH'] = '/home/coyang/zynq-parrot/install/lib:' + env.get('LD_LIBRARY_PATH', '')
    command = [str(binary), '+c_args=prog.nbf 240000', '+bsg_trace=dump.fst']
    state = dict(state='running', scope='Old mode-0 trace-only equivalence gate; no data-reuse execution.',
                 build_manifest=rec(args.build), binary=rec(binary), driver=rec(__file__),
                 old_session=rec(OLD / 'session.json'), old_mode0=mode, command=command,
                 checker=rec(checker), auditor_manifest=rec(AUDIT / 'manifest.json'),
                 fst2vcd=rec(converter), native_seconds=240, trace_limit_bytes=TRACE_LIMIT,
                 own_old200_baseline=rec(OLD200_AUDIT / 'manifest.json'),
                 configured_memory_latency_ticks=EXPECTED_LATENCY, model_l2_banks=1,
                 platform_scope='Synthetic one-L2-bank model, not physical two-bank FPGA latency.')
    manifest = output / 'validation.json'; save(manifest, state)
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (TRACE_LIMIT, TRACE_LIMIT))
    try:
        start = time.monotonic()
        with (runtime / 'run.log').open('w') as log:
            process = subprocess.Popen(command, cwd=runtime, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, preexec_fn=limits)
            last = start
            while process.poll() is None:
                now = time.monotonic()
                if now - start > 300:
                    process.terminate()
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
                    raise ValueError('host validation guard exceeded')
                if now - last >= 30:
                    print('mode0 runtime elapsed_s=%d' % (now - start), flush=True); last = now
                time.sleep(1)
        state.update(exit_code=process.returncode, elapsed_seconds=time.monotonic() - start,
                     run_log=rec(runtime / 'run.log'))
        fst = runtime / 'dump.fst'
        if fst.exists(): state['stopped_fst'] = rec(fst)
        save(manifest, state)
        run([sys.executable, str(checker), str(runtime / 'run.log'), '--exit-code',
             str(process.returncode), '--test', 'mt_context_resume_prefix_benchmark'],
            REPO, output / 'acceptance')
        text = (runtime / 'run.log').read_text()
        mode0_values(text)
        require(fst.is_file() and 0 < fst.stat().st_size < TRACE_LIMIT, 'trace missing or truncated')
        expected = set(json.loads((HERE / 'required-signals.json').read_text())['canonical_names_verbatim'])
        new_report = audit(fst, 'scoped', output, converter, analyzer)
        # The retained old200 trace was read to clean EOF already. Reuse its
        # hash-bound report/events rather than decompressing it a second time.
        shutil.copy2(baseline['report']['path'], output / 'old200-audit.json')
        shutil.copy2(baseline['events']['path'], output / 'old200-events.jsonl')
        compare_own200_audit(new_report, output / 'scoped-events.jsonl', expected,
                            baseline, baseline_report)
        # Require no unrequested variables, including unused alias names.
        converter_process = subprocess.Popen([converter, str(fst)], stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, text=True)
        scopes, variables = [], []
        try:
            for line in converter_process.stdout:
                words = line.split()
                if words[:1] == ['$scope']: scopes.append(words[2])
                elif words[:1] == ['$upscope']: scopes.pop()
                elif words[:1] == ['$var']: variables.append('.'.join(scopes + [words[4]]))
                elif words[:1] == ['$enddefinitions']: break
            require(len(variables) == 105 and set(variables) == expected,
                    'scoped FST has missing/extra/duplicate variable declarations')
        finally:
            converter_process.stdout.close()
            if converter_process.poll() is None: converter_process.terminate()
            try: converter_process.wait(timeout=10)
            except subprocess.TimeoutExpired: converter_process.kill(); converter_process.wait()
            converter_process.stderr.close()
        state.update(state='pass-no-data-reuse-admission', complete_ring_cycles=EXPECTED_CYCLES,
                     required_signal_count=105, old_report=rec(output / 'old200-audit.json'),
                     scoped_report=rec(output / 'scoped-audit.json'),
                     old_events=rec(output / 'old200-events.jsonl'), scoped_events=rec(output / 'scoped-events.jsonl'),
                     accepted_event_streams_byte_identical=True,
                     original_model_still_unchanged=(sha(OLD / 'model' / PREFIX) == MODEL_SHA))
        require(state['original_model_still_unchanged'], 'original durable model changed')
        print(json.dumps({'state':state['state'], 'manifest':str(manifest),
                          'trace_bytes':fst.stat().st_size, 'old_trace_bytes':Path(mode['fst']['path']).stat().st_size,
                          'events_sha256':state['scoped_events']['sha256']}, indent=2))
    except BaseException as error:
        state.update(state='failed', error=repr(error))
        raise
    finally:
        save(manifest, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands_parser = parser.add_subparsers(dest='command', required=True)
    b = commands_parser.add_parser('build')
    b.add_argument('--original', type=Path, default=Path('/dev/shm/zp-linux-resume-capacity-20261120/burst-off200-obj'))
    b.add_argument('--output', type=Path, required=True)
    v = commands_parser.add_parser('validate-mode0')
    v.add_argument('--build', type=Path, required=True, help='new scoped build evidence/build.json')
    v.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    (build if args.command == 'build' else validate)(args)


if __name__ == '__main__':
    main()
