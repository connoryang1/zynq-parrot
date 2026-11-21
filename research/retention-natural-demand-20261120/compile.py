#!/usr/bin/env python3
"""Build one plain retention/resource/scope ELF from frozen reviewed inputs."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE = ROOT/'research/complete-policy-scope-20261120/compiled'
SOURCE_SHA = 'b242d76a3bc5fb754ea92a6167ede622397e19630c7b9e5a415715deb085378e'


def record(path):
    path = Path(path)
    return dict(path=str(path.resolve()), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def command(args, output):
    run = subprocess.run(args, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    output.write_bytes(run.stdout)
    if run.returncode:
        raise RuntimeError(f'command failed {run.returncode}: {args}')
    return args


def main():
    if (HERE/'manifest.json').exists() or (HERE/'program').exists():
        raise SystemExit('refusing to overwrite retained build')
    tests = {}
    for name, count in (('combined',4),('retention',7),('resource',8),('workload',12)):
        p = HERE/(name+'-host-tests.log')
        text = p.read_text()
        assert f'Ran {count} tests' in text and text.rstrip().endswith('OK')
        tests[name] = dict(passed=count, log=record(p))
    archived = json.loads((ARCHIVE/'manifest.json').read_text())
    dry = Path(archived['dry_run']['path'])
    assert record(dry)['sha256'] == archived['dry_run']['sha256']
    lines = [line for line in dry.read_text().splitlines() if
        '/scheduler_pipe_hint_benchmark_plain_scoped_resources_dynamic ' in line]
    assert len(lines) == 1
    original = shlex.split(lines[0])
    assert original.pop() == '>&2'
    assert original[-1] == 'scheduler_pipe_hint_benchmark.c'
    assert '-DBP_RESUME_RESOURCE_STATS=1' in original and '-DBP_RESUME_COMPLETE_POLICY_SCOPE=1' in original
    assert not any('ZLIB' in arg or arg == '-lz' for arg in original)
    source = ROOT/'linux-tests/scheduler_pipe_hint_benchmark.c'
    assert record(source)['sha256'] == archived['source'][source.name]['sha256'] == SOURCE_SHA
    assert record(ROOT/'linux-tests/resume_workload.h')['sha256'] == archived['source']['resume_workload.h']['sha256']
    for name in ('compiler','compiler_real','readelf_tool'):
        assert record(archived[name]['path'])['sha256'] == archived[name]['sha256']
    (HERE/'source').mkdir()
    (HERE/'program').mkdir()
    snapshots = {}
    for name in ('scheduler_pipe_hint_benchmark.c','resume_workload.h','emit_resume_transfer.py',
                 'test_resume_complete_policy_scope.py','test_resume_retention_protocol.py',
                 'test_resume_resource_accounting.py','test_resume_workload.py'):
        p = ROOT/'linux-tests'/name
        shutil.copyfile(p, HERE/'source'/name)
        snapshots[name] = dict(original=record(p), snapshot=record(HERE/'source'/name))
    elf = HERE/'program/scheduler_pipe_hint_benchmark_plain_retention_resources_scoped_dynamic'
    actual = list(original)
    actual[actual.index('-o')+1] = str(elf)
    actual[-1] = str(HERE/'source/scheduler_pipe_hint_benchmark.c')
    actual.insert(actual.index('-o'), '-DBP_RESUME_RETENTION=1')
    command(actual, HERE/'compile.log')
    command([actual[0],'--version'], HERE/'compiler-version.log')
    reader = archived['readelf_tool']['path']
    command([reader,'-W','-h','-l','-d','-s',str(elf)], HERE/'readelf.log')
    readelf = (HERE/'readelf.log').read_text()
    assert 'Class:                             ELF64' in readelf and 'RISC-V' in readelf
    assert 'Type:                              EXEC' in readelf
    needed = re.findall(r'\(NEEDED\).*?\[(.*?)\]', readelf)
    assert needed and not any('libz' in name for name in needed)
    assert 'zlibVersion' not in readelf and 'deflateInit_' not in readelf
    loader = re.search(r'Requesting program interpreter: ([^\]]+)', readelf)[1]
    assert loader == '/lib/ld-linux-riscv64-lp64d.so.1'
    transfer = HERE/'plain-retention-resources-scoped.transfer'
    emit_command = [sys.executable, str(ROOT/'linux-tests/emit_resume_transfer.py'),str(elf)]
    command(emit_command, transfer)
    sys.path.insert(0, str(ROOT/'linux-tests'))
    from run_scheduler_pipe_hint import validate_transfer
    validate_transfer(transfer, record(elf)['sha256'])
    commands = transfer.read_text().splitlines()
    payload = ''.join(re.fullmatch(r"echo '([A-Za-z0-9+/=]+)' >> /tmp/scheduler_pipe_hint_benchmark_dynamic.b64", line)[1]
                      for line in commands[1:-3])
    compressed = base64.b64decode(payload, validate=True)
    assert gzip.decompress(compressed) == elf.read_bytes()
    assert compressed == gzip.compress(elf.read_bytes(), mtime=0)
    text = source.read_text().splitlines()
    ranges = [(360,391),(393,410),(423,523),(839,879),(889,913)]
    proof = dict(source_sha256=SOURCE_SHA, excerpts=[dict(first_line=a,last_line=z,
        text='\n'.join(f'{i} {text[i-1]}' for i in range(a,z+1))) for a,z in ranges],
        entry_precondition='Fresh boot and successful prior probe must leave global retention mode0 before first cell setup. retention_initialize clears taskmode but does not itself reset a stale global policy before first allocation.',
        task_boundary='Scope initializes taskmode0 and drains reported prefix bits before output; retention policies never arm mode14 or emit per-wake hints.',
        cell_boundary='Both arms set/check global mode at start; finish reads/checks then resets global0/readback before scope task0/prefix cleanup, ending SELF+CHILDREN rusage, WHOLE timestamp and all reporting.',
        limits='Prefix-controller drain only, not all UCE/memory requests. No kernel/board timing or performance evidence.')
    (HERE/'boundary-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    for pair in snapshots.values():
        assert record(pair['original']['path']) == pair['original']
    manifest = dict(state='plain-retention-resource-scope-elf-host-verified-no-target-run',
        purpose='Future natural scan/lookup/parse/chase functional review on bounded c7 kernel and capable retention hardware; root preregisters matrix separately',
        archived_compile_manifest=record(ARCHIVE/'manifest.json'), archived_dry_run=record(dry),
        archived_plain_command=original, compile_command=actual,
        difference='Same archived plain scoped flags; add only BP_RESUME_RETENTION=1 and use new output/frozen source paths. Resource/scope remain1; ZLIB absent.',
        source=snapshots, compiler=archived['compiler'], compiler_real=archived['compiler_real'],
        readelf_tool=archived['readelf_tool'], compiler_version=record(HERE/'compiler-version.log'),
        elf=record(elf), dynamic_loader=loader, needed=needed, readelf=record(HERE/'readelf.log'),
        compile_log=record(HERE/'compile.log'), transfer=record(transfer), emit_command=emit_command,
        transfer_commands=len(commands), gzip_payload_bytes=len(compressed),
        transfer_validation='Maintained strict parser accepts; exact offline base64+gzip reconstruction and deterministic gzip bytes match ELF',
        build_source=record(Path(__file__)), combined_test_source=record(HERE/'test_combined_protocol.py'),
        boundary_proof=record(HERE/'boundary-proof.json'), host_tests=tests, total_host_tests_passed=31,
        sources_unchanged_after_build=True, makefile_edits=0, sdk_writes=0, old_elf_overwrites=0,
        target_execution=False, board_actions=False, claims_excluded=['FPGA result','benefit','speedup','capability-present runtime success'])
    (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('state','elf','needed','transfer','transfer_commands','total_host_tests_passed')},indent=2))


if __name__=='__main__':
    main()
