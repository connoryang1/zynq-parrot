#!/usr/bin/env python3
"""Attribute a measured benchmark window using architectural retirements.

The tool streams ``fst2vcd`` output, selects the final ordered begin/end-PC
pair, and reports core-clock cycles, retired instructions, idle retirement
slots, and symbol-level instruction counts.  It samples stable values before
each ``be.clk_i`` rising edge, matching the repository's other trace tools.
"""

import argparse
from collections import Counter
import json
import subprocess
import sys

from cache_overlap_vcd import EvidenceError, rising_edges
from prefetch_overlap_vcd import read_header


SIGNALS = {
    'clock': 'be.clk_i',
    'commit_v': 'be.calculator.commit_pkt_cast_o.instret',
    'commit_pc': 'be.calculator.commit_pkt_cast_o.pc',
    'commit_thread': 'be.retire_thread_id_lo',
}


def symbols(elf):
    if elf is None:
        return []
    output = subprocess.check_output(
        ['riscv64-unknown-elf-nm', '-n', '-C', elf], text=True)
    result = []
    for line in output.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[1].lower() in ('t', 'w'):
            result.append((int(fields[0], 16), fields[2]))
    return result


def symbol_for(pc, ordered):
    match = None
    for address, name in ordered:
        if address > pc:
            break
        match = name
    return match or '<unknown>'


def analyze(stream, begin_pc, end_pc, elf=None, expected_windows=None):
    if begin_pc == end_pc:
        raise EvidenceError('begin and end PCs must differ')
    selected, timescale = read_header(stream, SIGNALS)
    ordered_symbols = symbols(elf)
    active = None
    windows = []

    for _, timestamp, values in rising_edges(stream, selected):
        commit_v = values.get('commit_v')
        if commit_v not in (0, 1):
            raise EvidenceError('unknown or nonbinary commit valid')
        pc = values.get('commit_pc') if commit_v else None
        if commit_v and pc is None:
            raise EvidenceError('unknown committed PC')

        if commit_v and pc == begin_pc:
            if active is not None:
                raise EvidenceError('begin PC committed before prior window ended')
            active = dict(begin_timestamp=timestamp, core_cycles=0,
                          retired=0, by_pc=Counter(), by_thread=Counter())
            continue
        if active is None:
            if commit_v and pc == end_pc:
                raise EvidenceError('end PC committed without a begin PC')
            continue

        active['core_cycles'] += 1
        if commit_v and pc == end_pc:
            active['end_timestamp'] = timestamp
            active['no_retirement_cycles'] = active['core_cycles'] - active['retired']
            active['ipc'] = active['retired'] / active['core_cycles']
            by_symbol = Counter()
            for retired_pc, count in active.pop('by_pc').items():
                by_symbol[symbol_for(retired_pc, ordered_symbols)] += count
            active['by_symbol'] = dict(by_symbol.most_common())
            active['by_thread'] = {
                str(thread): count for thread, count in sorted(active['by_thread'].items())
            }
            windows.append(active)
            active = None
        elif commit_v:
            active['retired'] += 1
            active['by_pc'][pc] += 1
            thread = values.get('commit_thread')
            if thread is None:
                raise EvidenceError('unknown retirement thread')
            active['by_thread'][thread] += 1

    if active is not None:
        raise EvidenceError('trace ended inside a measured window')
    if not windows:
        raise EvidenceError('no complete begin/end-PC windows')
    if expected_windows is not None and len(windows) != expected_windows:
        raise EvidenceError(
            'expected %d windows, observed %d' % (expected_windows, len(windows)))
    return dict(verdict='valid_retirement_windows', timescale=timescale,
                begin_pc=begin_pc, end_pc=end_pc, window_count=len(windows),
                sampling='stable values before be.clk_i rising edges; boundary instructions excluded',
                signals={key: value[1] for key, value in selected.items()},
                measured=windows[-1], windows=windows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--begin-pc', required=True, type=lambda value: int(value, 0))
    parser.add_argument('--end-pc', required=True, type=lambda value: int(value, 0))
    parser.add_argument('--elf')
    parser.add_argument('--expected-windows', type=int)
    args = parser.parse_args()
    try:
        report = analyze(sys.stdin, args.begin_pc, args.end_pc,
                         args.elf, args.expected_windows)
    except (EvidenceError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps(dict(verdict='invalid_trace', error=str(error))))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
