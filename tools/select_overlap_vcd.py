#!/usr/bin/env python3
"""Stream only the VCD signals needed by the prefetch overlap validator.

The full FST is still decoded, but ripgrep filters unrelated value changes in
native code before the transaction validator parses them in Python.  The VCD
header is retained intact so signal identity and timescale checks stay strict.
"""

import argparse
import subprocess
import sys

from prefetch_overlap_vcd import OPTIONAL_UCE_SIGNALS, read_header, signal_names


def escape_regex_code(code):
    return ''.join('\\' + char if char in '.+*?^$()[]{}|\\' else char
                   for char in code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fst')
    parser.add_argument('--uce-prefix', default='dcache_uce')
    parser.add_argument('--axi-prefix', default='axi_mem')
    args = parser.parse_args()

    source = subprocess.Popen(['fst2vcd', args.fst], stdout=subprocess.PIPE,
                              bufsize=0)
    assert source.stdout is not None
    header = []
    for line in source.stdout:
        header.append(line)
        if b'$enddefinitions' in line:
            break
    else:
        source.wait()
        raise RuntimeError('FST conversion omitted VCD enddefinitions')

    selected, _ = read_header(
        (line.decode('ascii') for line in header),
        signal_names(args.uce_prefix, args.axi_prefix, True),
        optional=OPTIONAL_UCE_SIGNALS)
    codes = sorted({code for code, _ in selected.values()})
    alternatives = '|'.join(escape_regex_code(code) for code in codes)
    pattern = (r'^(?:#[0-9]+$|[bB][01xXzZ]+ (?:' + alternatives
               + r')$|[01xXzZ](?:' + alternatives + r')$)')

    output = sys.stdout.buffer
    output.write(b''.join(header))
    output.flush()
    select = subprocess.run(['rg', '--no-line-number', '--no-filename',
                             '-e', pattern], stdin=source.stdout,
                            stdout=output, check=False)
    source_rc = source.wait()
    if source_rc or select.returncode:
        raise RuntimeError('VCD conversion/filter failed: fst2vcd=%d rg=%d'
                           % (source_rc, select.returncode))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print('invalid filtered VCD: %s' % error, file=sys.stderr)
        sys.exit(2)
