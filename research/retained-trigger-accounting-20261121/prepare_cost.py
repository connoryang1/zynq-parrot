#!/usr/bin/env python3
"""Validate distinct no-control-baseline programs without running an RV target."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SDK = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot')
CC = SDK / 'host/bin/riscv64-linux-gcc'
READELF = SDK / 'host/opt/ext-toolchain/bin/riscv64-buildroot-linux-gnu-readelf'


def bind(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_source(old, regex):
    text = old.read_text()
    text = text.replace('whole cells price control, polling and both process lifecycles.',
        'enabled cells pay retained activation/cleanup; disabled cells issue no\n * retained-control writes. Other observer overhead remains matched.')
    prefix = 'RESUME_RETAINED29_REGEX_' if regex else 'RESUME_RETAINED29_'
    text = text.replace(prefix, prefix + 'COST_')
    replacements = {
        'if (submit(selected) || poll_control(selected, &raw))':
            'if ((enabled && submit(selected)) || poll_control(selected, &raw))',
        'source_off() || submit(0) || replay_idle(&replay_after)':
            'source_off() || (enabled && submit(0)) || replay_idle(&replay_after)',
        'version=29 mode=cell activation=before-allocation cleanup=mode0 busy=uce_client_backend matched_lifecycle=1 advisory_source=none':
            'version=29-cost mode=cell activation=before-allocation cleanup=mode0 busy=uce_client_backend matched_lifecycle=1 advisory_source=none baseline=mode0-no-retained-control',
        'reset_raw=0x%016" PRIx64 " busy_scope=uce_client_backend\\n", repeat, order, enabled, selected, active, reset);':
            'reset_raw=0x%016" PRIx64 " busy_scope=uce_client_backend retained_control_writes=%u\\n", repeat, order, enabled, selected, active, reset, enabled ? 2U : 0U);'
    }
    for before, after in replacements.items():
        assert text.count(before) == 1, before
        text = text.replace(before, after)
    return text


def main():
    out = HERE / 'prepared-cost01'
    assert not out.exists(), 'preserve previous preparation'
    out.mkdir()
    commands = []
    record = dict(state='PREPARING no RV target or board execution', commands=commands)

    def run(label, argv, cwd=ROOT):
        result = subprocess.run(list(map(str, argv)), cwd=cwd, capture_output=True, text=True, timeout=120)
        path = out / (label + '.log')
        path.write_text(result.stdout + result.stderr)
        commands.append(dict(label=label, argv=list(map(str, argv)), cwd=str(cwd),
                             returncode=result.returncode, log=bind(path)))
        assert result.returncode == 0, label
        return result.stdout + result.stderr

    try:
        sys.path.insert(0, str(ROOT / 'linux-tests'))
        import retained29_application_protocol as protocol
        frozen = protocol.source_hashes()
        record['legacy_sources_before'] = frozen
        for regex in (False, True):
            old_name = 'scheduler_retained29_regex_benchmark.c' if regex else 'scheduler_retained29_benchmark.c'
            name = old_name.replace('_benchmark', '_cost_benchmark')
            assert (ROOT / 'linux-tests' / name).read_text() == expected_source(ROOT / 'linux-tests' / old_name, regex)
        record['derivation'] = 'Exactly two conditional retained-control calls plus distinct labels/scope/declared-write telemetry; old workload/process/resource/check/cleanup code preserved.'
        run('host-tests', ['python3', '-B', '-m', 'unittest', '-v', 'test_retained29_cost_benchmark'], ROOT / 'linux-tests')
        helper = load(ROOT / 'research/regex-natural-demand-20261121/prepare.py', 'cost_runtime_helper')
        members = helper.accepted_members()
        sysroot = Path(run('compiler-sysroot', [CC, '-print-sysroot']).strip())
        libc = SDK / 'target/lib/libc.so.6'
        loader = SDK / 'target/lib/ld-linux-riscv64-lp64d.so.1'
        for name, path in [('libc.so.6', libc), ('ld-linux-riscv64-lp64d.so.1', loader)]:
            assert bind(path)['sha256'] == members['lib/' + name]['sha256']
            assert helper.allocated_sections(path) == helper.allocated_sections(sysroot / 'lib' / name)
        symbols = run('accepted-runtime-symbols', [READELF, '-Ws', libc, loader])
        emitter = load(ROOT / 'linux-tests/emit_resume_transfer.py', 'cost_transfer')
        programs = {}
        for regex in (False, True):
            kind = 'regex' if regex else 'plain'
            name = 'scheduler_retained29_regex_cost_benchmark.c' if regex else 'scheduler_retained29_cost_benchmark.c'
            binary = out / ('retained29-cost-' + kind)
            run(kind + '-compile', [CC, '-O2', '-Wall', '-Wextra', '-Werror', '-march=rv64imafdc_zicsr_zifencei',
                '-mabi=lp64d', '-no-pie', '-std=c11', '-o', binary, ROOT / 'linux-tests' / name])
            dynamic = run(kind + '-readelf', [READELF, '-h', '-l', '-d', '-Ws', binary])
            needed = re.findall(r'Shared library: \[(.*?)\]', dynamic)
            assert needed == ['libc.so.6', 'ld-linux-riscv64-lp64d.so.1']
            assert 'ELF64' in dynamic and 'RISC-V' in dynamic and 'EXEC (Executable file)' in dynamic
            assert '/lib/ld-linux-riscv64-lp64d.so.1' in dynamic
            required = sorted(set(re.findall(r'\bUND\s+(\S+@GLIBC_\S+)', dynamic)))
            for symbol in required:
                assert symbol in symbols or symbol.replace('@', '@@', 1) in symbols, symbol
            if regex:
                assert all(name + '@GLIBC_2.27' in required for name in ('regcomp', 'regexec', 'regfree'))
            transfer = emitter.commands(binary)
            encoded = ''.join(re.fullmatch(r"echo '([^']+)' >> .*", line)[1]
                              for line in transfer if line.startswith('echo '))
            assert gzip.decompress(base64.b64decode(encoded, validate=True)) == binary.read_bytes()
            path = out / (kind + '.transfer')
            path.write_text('\n'.join(transfer) + '\n')
            programs[kind] = dict(elf=bind(binary), transfer=bind(path), needed=needed, versioned_imports=required)
        assert frozen == protocol.source_hashes(), 'legacy frozen source changed'
        sources = ['linux-tests/scheduler_retained29_cost_benchmark.c',
                   'linux-tests/scheduler_retained29_regex_cost_benchmark.c',
                   'linux-tests/test_retained29_cost_benchmark.py',
                   'linux-tests/resume_workload.h', 'linux-tests/retained29_regex_workload.h']
        snapshots = []
        for name in sources:
            source = ROOT / name
            path = out / 'source' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, path)
            snapshots.append(dict(original=bind(source), snapshot=bind(path)))
        record.update(state='PASS host syscall/lifecycle/fault checks and RV64 accepted-runtime link/transfer preparation; no RV/FPGA run',
                      programs=programs, sources=snapshots, legacy_sources_after=protocol.source_hashes(),
                      preparer=bind(__file__), compiler=bind(CC), libc=bind(libc), loader=bind(loader),
                      scope='Disabled cells issue0 retained writes; enabled pay2 insideWHOLE. Shared telemetry/measurement overhead remains. Source-none is extra retained capacity, not advisory prefetch effectiveness.',
                      admission='UNLAUNCHABLE: existing application supervisor accepts old markers/ELFs only; new versioned protocol/physical binding remains required.')
    except BaseException as error:
        record.update(state='FAIL preparation preserved; no target execution', error=repr(error))
        raise
    finally:
        (out / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
        print(record['state'])


if __name__ == '__main__':
    main()
