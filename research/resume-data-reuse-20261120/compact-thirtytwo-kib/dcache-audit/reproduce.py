#!/usr/bin/env python3
"""Audit the closed 32KiB FST; fresh output only, no target execution."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

CASE = Path(__file__).resolve().parent.parent
ROOT = CASE.parents[2]
FROZEN = CASE.parent/'dcache-observability/analyzer'


def bind(p):
    p = Path(p)
    return dict(path=str(p.resolve()), bytes=p.stat().st_size,
                sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assert not (out/'manifest.json').exists() and not (out/'analysis.json').exists(), 'fresh output required'
    session = json.loads((CASE/'session.json').read_text())
    assert session['state'] == 'pass'
    pairs = []
    (out/'source').mkdir(exist_ok=True)
    for name in ('analyze_resume_data_reuse_vcd.py', 'cache_overlap_vcd.py',
                 'test_analyze_resume_data_reuse_vcd.py'):
        a, b = bind(FROZEN/name), bind(ROOT/'tools'/name)
        assert a['sha256'] == b['sha256']
        shutil.copyfile(FROZEN/name, out/'source'/name)
        pairs.append(dict(frozen=a, current=b, retained=bind(out/'source'/name), byte_identical=True))
    inputs = {k: bind(p) for k, p in dict(session=CASE/'session.json', metadata=CASE/'trace-metadata.json',
        fst=CASE/'runtime/dump.fst', elf=CASE/'program/benchmark.riscv',
        model=session['model']['path'], log=CASE/'runtime/run.log',
        runtime_nbf=CASE/'runtime/prog.nbf', checker=CASE/'source/testing/check_run.py',
        guest_observations=CASE/'guest-observations.json', frozen_runner=CASE/'runner.py',
        parser_import_helper=ROOT/'linux-tests/patch_nbf_memory_records.py').items()}
    for key, expected in [('fst', session['stopped_fst']), ('elf', session['program']['elf']),
                          ('model', session['model']), ('runtime_nbf', session['runtime_nbf'])]:
        assert inputs[key]['sha256'] == expected['sha256']
    converter = shutil.which('fst2vcd')
    command = [converter, inputs['fst']['path']]
    analyzer = [sys.executable, '-B', str(out/'source/analyze_resume_data_reuse_vcd.py'),
        '--metadata', inputs['metadata']['path'], '--output', str(out/'analysis.json'),
        '--events', str(out/'events.jsonl')]
    checker = [sys.executable, '-B', inputs['checker']['path'], inputs['log']['path'],
               '--exit-code', str(session['exit_code'])]
    transcript = Path(inputs['log']['path']).read_text()
    marker = '[BSG-PASS] checked nonresident data reuse ring lookup'
    assert transcript.count(marker) == 1 and transcript.index(marker) < transcript.index('CORE PASS')
    sys.path.insert(0, str(ROOT/'linux-tests'))
    spec = importlib.util.spec_from_file_location('frozen_case_runner', CASE/'runner.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert runner.compact_guest_observations(transcript, 32) == json.loads((CASE/'guest-observations.json').read_text())
    assert json.loads((CASE/'trace-metadata.json').read_text())['expected_target_loads_by_context'] == {
        str(c): runner.expected_target_loads(32, c) for c in range(4)}
    test_command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(out/'source'),
                    '-p', 'test_analyze_resume_data_reuse_vcd.py', '-v']
    started = time.monotonic()
    with (out/'converter.stderr').open('wb') as cerr, (out/'analysis.log').open('wb') as log:
        convert = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=cerr)
        audit = subprocess.Popen(analyzer, stdin=convert.stdout, stdout=log, stderr=subprocess.STDOUT)
        convert.stdout.close()
        audit_rc = audit.wait()
        convert_rc = convert.wait()
    with (out/'acceptance.log').open('wb') as log:
        checker_rc = subprocess.run(checker, stdout=log, stderr=subprocess.STDOUT).returncode
    with (out/'host-tests.log').open('wb') as log:
        tests_rc = subprocess.run(test_command, stdout=log, stderr=subprocess.STDOUT).returncode
    final = {k: bind(v['path']) for k, v in inputs.items()}
    assert final == inputs, 'input changed during audit'
    manifest = dict(state='passed' if audit_rc == convert_rc == checker_rc == tests_rc == 0 else 'failed',
        scope='Fixed-execution conditional address coverage only; no speedup/prefetch/FPGA projection',
        source_pairs=pairs, inputs=inputs, inputs_unchanged_after_analysis=True,
        converter_binary=bind(converter), converter_argv=command, analyzer_argv=analyzer,
        checker_argv=checker, host_tests_argv=test_command, analyzer_returncode=audit_rc,
        complete_custom_guest_parser_recheck=True, independent_metadata_load_generator_recheck=True,
        converter_returncode=convert_rc, maintained_checker_returncode=checker_rc,
        host_tests_returncode=tests_rc, complete_converter_eof=convert_rc == audit_rc == 0,
        elapsed_seconds=time.monotonic()-started,
        artifacts={p.name: bind(p) for p in out.iterdir() if p.is_file() and p.name != 'manifest.json'})
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({k: manifest[k] for k in ('state', 'elapsed_seconds', 'analyzer_returncode',
        'converter_returncode', 'maintained_checker_returncode', 'host_tests_returncode')}, indent=2))
    return 0 if manifest['state'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
