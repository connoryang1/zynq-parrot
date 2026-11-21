#!/usr/bin/env python3
"""Archive and independently rebuild scoped and legacy benchmark ELFs offline."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LINUX = ROOT / 'linux-tests'
CC = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux-gcc')
READELF = CC.with_name('riscv64-linux-readelf')
EXTERNAL = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120')
VARIANTS = (
    ('scheduler_pipe_hint_benchmark_dynamic', 'pipe-hint-benchmark-dynamic', False),
    ('scheduler_pipe_hint_benchmark_zlib_dynamic', 'pipe-hint-benchmark-zlib-dynamic', True),
    ('scheduler_pipe_hint_benchmark_retention_dynamic', 'pipe-hint-benchmark-retention-dynamic', True),
    ('icache_retention_probe_dynamic', 'icache-retention-probe-dynamic', False),
    ('scheduler_pipe_hint_benchmark_resources_dynamic', 'pipe-hint-benchmark-resources-dynamic', True),
    ('scheduler_pipe_hint_benchmark_retention_resources_dynamic', 'pipe-hint-benchmark-retention-resources-dynamic', True),
    ('scheduler_pipe_hint_benchmark_plain_resources_dynamic', 'pipe-hint-benchmark-plain-resources-dynamic', False),
    ('scheduler_pipe_hint_benchmark_plain_scoped_resources_dynamic', 'pipe-hint-benchmark-plain-scoped-resources-dynamic', False),
    ('scheduler_pipe_hint_benchmark_zlib_scoped_resources_dynamic', 'pipe-hint-benchmark-zlib-scoped-resources-dynamic', True),
)
EXPECTED_SCOPED = (
    '8e64b984180436ffc15504ee6f47fe678aaedec3e6a7fedbeba68b75825f14bb',
    '079f974d671908f6aa922122f6901b3123cf16ec244be25e3432b4df500b465b',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(path):
    return dict(path=str(path.resolve()), bytes=path.stat().st_size, sha256=sha(path))


def main():
    out = HERE / 'compiled'
    out.mkdir()  # Refuse accidental evidence replacement.
    (out / 'source').mkdir()
    (out / 'reference').mkdir()
    source_names = ('scheduler_pipe_hint_benchmark.c', 'resume_workload.h',
                    'icache_retention_probe.c', 'Makefile')
    sources = {}
    for name in source_names:
        shutil.copy2(LINUX / name, out / 'source' / name)
        sources[name] = identity(out / 'source' / name)
    references = {}
    for name, _, _ in VARIANTS:
        shutil.copy2(LINUX / 'out' / name, out / 'reference' / name)
        references[name] = identity(out / 'reference' / name)
    for (name, _, _), expected in zip(VARIANTS[-2:], EXPECTED_SCOPED):
        assert references[name]['sha256'] == expected, name

    command = ['make', '--no-print-directory', '-C', str(LINUX),
               'OUT=' + str(out / 'rebuilt'), 'BP_LINUX_DYNAMIC_CC=' + str(CC)]
    command += [target for _, target, _ in VARIANTS]
    dry_run = subprocess.run(command[:1] + ['-n'] + command[1:],
                             text=True, capture_output=True, timeout=30)
    (out / 'compile-dry-run.stdout').write_text(dry_run.stdout)
    (out / 'compile-dry-run.stderr').write_text(dry_run.stderr)
    dry_run.check_returncode()
    run = subprocess.run(command, text=True, capture_output=True, timeout=120)
    (out / 'compile.stdout').write_text(run.stdout)
    (out / 'compile.stderr').write_text(run.stderr)
    (out / 'compile-command.json').write_text(json.dumps(command, indent=2) + '\n')
    run.check_returncode()
    version = subprocess.check_output([str(CC), '--version'], text=True, timeout=10)
    (out / 'compiler-version.txt').write_text(version)
    rebuilt = {}
    for name, _, zlib in VARIANTS:
        binary = out / 'rebuilt' / name
        assert sha(binary) == references[name]['sha256'], name + ' is not byte reproducible'
        report = subprocess.check_output([str(READELF), '-h', '-l', '-d', '-A', '-n', str(binary)],
                                         text=True, timeout=15)
        report_path = out / (name + '.readelf.txt')
        report_path.write_text(report)
        assert 'RISC-V' in report and 'EXEC (Executable file)' in report, name
        needed = re.findall(r'\(NEEDED\).*Shared library: \[([^\]]+)\]', report)
        assert ('libz.so.1' in needed) == zlib, (name, needed)
        rebuilt[name] = dict(**identity(binary), needed=needed, readelf=identity(report_path),
                             equals_reference=True, default_scope_off=name not in [v[0] for v in VARIANTS[-2:]])
    transfers = {}
    for flavor, (name, _, _) in zip(('plain', 'zlib'), VARIANTS[-2:]):
        source = EXTERNAL / ('workload-' + flavor + '-scoped-resources-gzip.transfer')
        target = out / source.name
        shutil.copy2(source, target)
        chunks = re.findall(r"^echo '([A-Za-z0-9+/=]+)' >> /tmp/[^ ]+\.b64$", target.read_text(), re.M)
        assert chunks, target
        payload = gzip.decompress(base64.b64decode(''.join(chunks), validate=True))
        assert payload == (out / 'rebuilt' / name).read_bytes(), target
        transfers[flavor] = dict(**identity(target), payload_sha256=hashlib.sha256(payload).hexdigest(),
                                commands=len(target.read_text().splitlines()))
    assert all(sha(LINUX / name) == value['sha256'] for name, value in sources.items())
    assert all(sha(LINUX / 'out' / name) == value['sha256'] for name, value in references.items())
    manifest = dict(state='rv64-byte-reproduced-offline; physical acceptance pending',
                    source=sources, compiler=identity(CC), compiler_real=identity(CC.with_name('riscv64-linux-gcc.br_real')),
                    readelf_tool=identity(READELF), command=command, compile_exit_code=run.returncode,
                    compile_stdout=identity(out / 'compile.stdout'), compile_stderr=identity(out / 'compile.stderr'),
                    dry_run=identity(out / 'compile-dry-run.stdout'), references=references, rebuilt=rebuilt,
                    legacy_default_binary_reproductions=7, scoped_binary_reproductions=2, transfers=transfers,
                    shared_sdk_mutations=False, board_actions=False,
                    drain_scope='scope-v1 reported prefix-controller bits only; not all UCE/memory responses')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(state=manifest['state'], legacy_reproductions=7,
                         scoped_reproductions=2, transfers=transfers), indent=2))


if __name__ == '__main__':
    main()
