#!/usr/bin/env python3
"""Extract load/switch events directly from selected signals in a closed FST.

This is the faster equivalent of fst2vcd TRACE | load_switch_vcd_events.py.
The first run builds a selective reader against Verilator's installed fstapi;
later runs reuse a content-addressed helper in ignored logs/fst-tools-cache/.
All flags after TRACE are passed to the existing event analyzer unchanged.
"""
import argparse
import ast
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def build_reader(root):
    candidates = [root / 'install/share/verilator/include/gtkwave']
    if os.environ.get('VERILATOR_ROOT'):
        candidates.append(Path(os.environ['VERILATOR_ROOT']) / 'include/gtkwave')
    verilator = shutil.which('verilator')
    if verilator:
        candidates.append(Path(verilator).resolve().parent.parent / 'share/verilator/include/gtkwave')
    names = ['fstapi.c', 'fstapi.h', 'fst_config.h', 'fastlz.c', 'fastlz.h', 'lz4.c', 'lz4.h', 'wavealloca.h']
    fst_dir = next((path for path in candidates if all((path / name).is_file() for name in names)), None)
    if fst_dir is None:
        raise RuntimeError('Missing Verilator fstapi sources: install Verilator under install/ or set VERILATOR_ROOT to its share/verilator directory.')
    cc, cxx = shutil.which('gcc'), shutil.which('g++')
    if not cc or not cxx:
        raise RuntimeError('Building the selective FST reader requires gcc and g++ (plus zlib development headers/library).')
    source = root / 'tools/filtered_fst.cpp'
    digest = hashlib.sha256(source.read_bytes())
    digest.update(Path(__file__).read_bytes())
    digest.update(Path(__file__).read_bytes())  # Includes compiler flags/cache protocol.
    for name in names:
        digest.update((fst_dir / name).read_bytes())
    for compiler in (cc, cxx):
        digest.update(subprocess.check_output([compiler, '--version']))
    cache = root / 'logs/fst-tools-cache'
    cache.mkdir(parents=True, exist_ok=True)
    binary = cache / ('filtered-fst-' + digest.hexdigest()[:20])
    with (cache / 'build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if binary.is_file() and os.access(binary, os.X_OK):
            return binary
        with tempfile.TemporaryDirectory(prefix='build-', dir=cache) as temporary:
            work = Path(temporary)
            objects = []
            for name in ('fstapi', 'fastlz', 'lz4'):
                obj = work / (name + '.o')
                subprocess.run([cc, '-O2', '-DFST_CONFIG_INCLUDE="fst_config.h"', '-I', str(fst_dir),
                                '-c', str(fst_dir / (name + '.c')), '-o', str(obj)], check=True,
                               stdout=sys.stderr)
                objects.append(str(obj))
            output = work / 'filtered-fst'
            subprocess.run([cxx, '-O2', '-I', str(fst_dir), str(source), *objects,
                            '-lz', '-lpthread', '-o', str(output)], check=True, stdout=sys.stderr)
            os.replace(output, binary)
    return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     epilog='Analyzer flags include --pc HEX (repeatable), --min-cycle N, and --period N.')
    parser.add_argument('fst', type=Path, help='Closed, complete FST waveform to read')
    args, flags = parser.parse_known_args()
    if not args.fst.is_file():
        parser.error('FST file does not exist: ' + str(args.fst))
    root = Path(__file__).resolve().parent.parent
    analyzer = root / 'tools/load_switch_vcd_events.py'
    tree = ast.parse(analyzer.read_text())
    # Read only the literal watch dictionary, without importing executable CLI code.
    watch = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'watch' for target in node.targets))
    binary = build_reader(root)
    decoder = subprocess.Popen([str(binary), str(args.fst), *watch.values()], stdout=subprocess.PIPE)
    try:
        result = subprocess.run([sys.executable, str(analyzer), *flags], stdin=decoder.stdout)
        decoder.stdout.close()
        reader_rc = decoder.wait()
        return result.returncode or (1 if reader_rc else 0)
    finally:
        if decoder.poll() is None:
            decoder.terminate()
            decoder.wait()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        sys.exit('Selective FST extraction failed: ' + str(error))
