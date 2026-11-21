#!/usr/bin/env python3
"""Clean isolated traced unit gate for the shared full-line retained store."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RTL = ROOT/'import/black-parrot/bp_common/src/v/bp_retained_line_store.sv'
TB = HERE/'retained_line_store_tb.sv'
WRAPPER = HERE/'retained_line_store_wrapper.sv'
DRIVER = HERE/'driver.cpp'


def artifact(path):
    path = Path(path).resolve()
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def limit_file_size():
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024, 64*1024*1024))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--i-lines', type=int, default=93)
    parser.add_argument('--d-lines', type=int, default=131)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--clock-mode', choices=('both','inverted','different-periods'), default='both')
    parser.add_argument('--verilator', type=Path, default=Path('/home/coyang/zynq-parrot/install/bin/verilator'))
    args = parser.parse_args()
    if min(args.i_lines, args.d_lines) < 0 or max(args.i_lines, args.d_lines) > 16384:
        parser.error('unit gate bounds: zero through16384 actual full-line slots per side')
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    record = dict(state='running', i_lines=args.i_lines, d_lines=args.d_lines,
                  scope='Directed backend unit correctness; no full-core, synthesis, unique-capacity or performance claim.',
                  sources={p.name:artifact(p) for p in (RTL, WRAPPER, DRIVER, Path(__file__))}, commands=[])
    free = shutil.disk_usage(output).free; record['free_bytes_before_build'] = free
    if free < 160*1024*1024:
        raise RuntimeError('insufficient local headroom; root should run this isolated gate in host RAM')
    (output/'source').mkdir()
    for path in (RTL, WRAPPER, DRIVER, Path(__file__)): shutil.copyfile(path, output/'source'/path.name)

    def run(label, argv, cwd, timeout):
        command = dict(label=label, argv=list(map(str,argv)), cwd=str(cwd), timeout_seconds=timeout)
        record['commands'].append(command); started = time.monotonic()
        with (output/(label+'.log')).open('wb') as log:
            result = subprocess.run(command['argv'], cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=timeout, preexec_fn=limit_file_size)
        command.update(returncode=result.returncode, elapsed_seconds=time.monotonic()-started,
                       log=artifact(output/(label+'.log')))
        if result.returncode: raise RuntimeError(label+' failed: '+str(result.returncode))

    try:
        run('version', [args.verilator,'--version'], output, 10)
        run('build', [args.verilator,'--cc','--exe','--build','--trace-fst','--assert','-Wall',
              '--top-module','retained_line_store_wrapper',
              '-GI_LINES='+str(args.i_lines),'-GD_LINES='+str(args.d_lines),
              '-CFLAGS','-std=c++14','-j','2','--Mdir',output/'obj',RTL,WRAPPER,DRIVER], output, 300)
        executable = output/'obj/Vretained_line_store_wrapper'
        record['clock_results'] = []
        for mode in (('inverted','different-periods') if args.clock_mode == 'both' else (args.clock_mode,)):
            runtime = output/mode; runtime.mkdir()
            run('run-'+mode, [executable]+(['different-periods'] if mode=='different-periods' else []), runtime, 120)
            text = (output/('run-'+mode+'.log')).read_text()
            expected = f'RETAINED_LINE_STORE_PASS I={args.i_lines} D={args.d_lines} clock={mode}'
            assert text.count(expected) == 1 and text.count('RETAINED_TEST_EXIT_CLEAN') == 1, 'missing exact unit completion'
            rows = re.findall(r'^RETAINED_COUNTS lane=(\d) queries=(\d+) responses=(\d+) inserts=(\d+) terminals=(\d+) published=(\d+)$',text,re.M)
            assert len(rows) == 2 and {row[0] for row in rows} == {'0','1'}
            for row in rows: assert int(row[1]) == int(row[2]) and int(row[3]) == int(row[4])
            record['clock_results'].append(dict(clock_mode=mode, counts=rows, fst=artifact(runtime/'retained-line-store.fst')))
        for name,binding in record['sources'].items():
            current = {p.name:p for p in (RTL,WRAPPER,DRIVER,Path(__file__))}[name]
            assert artifact(current) == binding, 'source changed during directed gate'
        record.update(state='PASS-directed-shared-retained-full-lines', executable=artifact(executable))
    except BaseException as error:
        record.update(state='FAIL-preserved-no-result', error=repr(error)); raise
    finally:
        (output/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
        print(output,record['state'])


if __name__ == '__main__': main()
