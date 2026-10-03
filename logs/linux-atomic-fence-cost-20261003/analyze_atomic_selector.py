#!/usr/bin/env python3
import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def analyze(name, physical, label, expected_state, pass_marker):
    text = (HERE / name).read_text(errors='replace').replace('\r', '')
    row_pattern = re.compile(
        rf'Atomic {label} sample/mode/cycles/x100-per-op/ok/observed/'
        r'complete/word/source: (0x[0-9a-f]+) (fence|aqrl) '
        r'(0x[0-9a-f]+) (0x[0-9a-f]+) (0x[0-9a-f]+) '
        r'(0x[0-9a-f]+) (0x[0-9a-f]+) (0x[0-9a-f]+) (0x[0-9a-f]+)')
    rows = []
    for match in row_pattern.finditer(text):
        rows.append((int(match[1], 16), match[2],
                     *[int(value, 16) for value in match.groups()[2:]]))
    result = {'parseable_rows': len(rows), 'modes': {}}
    for mode in ('aqrl', 'fence'):
        selected = [row for row in rows if row[1] == mode and row[0] > 0]
        per_op = [row[3] / 100 for row in selected]
        aggregate = [row[2] for row in selected]
        result['modes'][mode] = {
            'steady_samples': len(selected),
            'median_cycles_per_operation': statistics.median(per_op),
            'range_cycles_per_operation': [min(per_op), max(per_op)],
            'median_aggregate_cycles': statistics.median(aggregate),
            'range_aggregate_cycles': [min(aggregate), max(aggregate)],
            'all_rows_correct': all(row[4:] == expected_state
                                    for row in selected),
        }
    result['fence_delta_cycles_per_operation'] = round((
        result['modes']['fence']['median_cycles_per_operation']
        - result['modes']['aqrl']['median_cycles_per_operation']), 2)
    result['custom_pass'] = pass_marker in text
    result['core_pass'] = ('CORE[0] PASS' if physical else 'CORE PASS') in text
    return result


def analyze_multiready(name, physical, peer):
    text = (HERE / name).read_text(errors='replace').replace('\r', '')
    row_pattern = re.compile(
        r'Atomic multiready sample/peer/cycles/x100-per-op/ok/observed/'
        r'complete/word/source/ring-sc/peer-sc: '
        + ' '.join([r'(0x[0-9a-f]+)'] * 11))
    rows = [[int(value, 16) for value in match.groups()]
            for match in row_pattern.finditer(text)]
    steady = [row for row in rows if row[0] > 0]
    per_op = [row[3] / 100 for row in steady]
    aggregate = [row[2] for row in steady]
    expected_word = (1 << peer) | 8
    return {
        'parseable_rows': len(rows),
        'steady_samples': len(steady),
        'median_cycles_per_operation': statistics.median(per_op),
        'range_cycles_per_operation': [min(per_op), max(per_op)],
        'median_aggregate_cycles': statistics.median(aggregate),
        'range_aggregate_cycles': [min(aggregate), max(aggregate)],
        'all_rows_correct': all(
            row[1] == peer
            and row[4:] == [1, peer, 1, expected_word, 0, 0, 0]
            for row in rows),
        'spectator_bit_preserved': all(row[7] & 8 for row in rows),
        'total_sc_failures': sum(row[9] + row[10] for row in rows),
        'custom_pass': '[BSG-PASS] atomic multiready selector' in text,
        'core_pass': ('CORE[0] PASS' if physical else 'CORE PASS') in text,
    }


def analyze_roundrobin(name, physical):
    text = (HERE / name).read_text(errors='replace').replace('\r', '')
    row_pattern = re.compile(
        r'Atomic roundrobin sample/cycles/x100-per-op/ok/ready/complete/'
        r'source/sc0/sc1/sc3: ' + ' '.join([r'(0x[0-9a-f]+)'] * 10))
    rows = [[int(value, 16) for value in match.groups()]
            for match in row_pattern.finditer(text)]
    steady = [row for row in rows if row[0] > 0]
    per_op = [row[2] / 100 for row in steady]
    aggregate = [row[1] for row in steady]
    return {
        'parseable_rows': len(rows),
        'steady_samples': len(steady),
        'median_cycles_per_operation': statistics.median(per_op),
        'range_cycles_per_operation': [min(per_op), max(per_op)],
        'median_aggregate_cycles': statistics.median(aggregate),
        'range_aggregate_cycles': [min(aggregate), max(aggregate)],
        'all_rows_correct': all(
            row[3:] == [1, 0xa, 0xa, 0, 0, 0, 0] for row in rows),
        'all_three_contexts_completed': all(
            row[5] == 0xa and row[6] == 0 for row in rows),
        'total_sc_failures': sum(row[7] + row[8] + row[9]
                                 for row in rows),
        'custom_pass': '[BSG-PASS] atomic roundrobin selector' in text,
        'core_pass': ('CORE[0] PASS' if physical else 'CORE PASS') in text,
    }


nonresident = {
    'simulator': analyze('sim-run-accepted.log', False, 'fence',
                         (1, 2, 1, 4, 0),
                         '[BSG-PASS] atomic fence cost'),
    'fpga': analyze('physical-baremetal.log', True, 'fence',
                    (1, 2, 1, 4, 0),
                    '[BSG-PASS] atomic fence cost'),
}
resident = {
    'simulator': analyze('resident-sim-run.log', False, 'resident',
                         (1, 1, 1, 2, 0),
                         '[BSG-PASS] atomic resident selector'),
    'fpga': analyze('resident-physical.log', True, 'resident',
                    (1, 1, 1, 2, 0),
                    '[BSG-PASS] atomic resident selector'),
}
direct = json.loads(
    (HERE.parent / 'linux-dynamic-context-target-20261003' / 'analysis.json')
    .read_text())['median_cycles_per_handoff']
atomic_resident = resident['fpga']['modes']['aqrl'][
    'median_cycles_per_operation']
atomic_nonresident = nonresident['fpga']['modes']['aqrl'][
    'median_cycles_per_operation']
multiready = {
    'resident': {
        'simulator': analyze_multiready(
            'multiready-resident-sim-run.log', False, 1),
        'fpga': analyze_multiready(
            'multiready-resident-physical.log', True, 1),
    },
    'nonresident': {
        'simulator': analyze_multiready(
            'multiready-nonresident-sim-run.log', False, 2),
        'fpga': analyze_multiready(
            'multiready-nonresident-physical.log', True, 2),
    },
}
multiready_resident = multiready['resident']['fpga'][
    'median_cycles_per_operation']
multiready_nonresident = multiready['nonresident']['fpga'][
    'median_cycles_per_operation']
roundrobin = {
    'simulator': analyze_roundrobin('roundrobin-sim-run.log', False),
    'fpga': analyze_roundrobin('roundrobin-physical.log', True),
}
roundrobin_fpga = roundrobin['fpga']['median_cycles_per_operation']
report = {
    'nonresident': nonresident,
    'resident': resident,
    'multiready': multiready,
    'roundrobin_three_context': roundrobin,
    'expected_fpga_rows': 32,
    'derived_fpga_cycles': {
        'atomic_residency_penalty': round(
            atomic_nonresident - atomic_resident, 2),
        'direct_register_residency_penalty': round(
            direct['register_nonresident'] - direct['register_resident'], 2),
        'ready_selection_over_direct_resident': round(
            atomic_resident - direct['register_resident'], 2),
        'ready_selection_over_direct_nonresident': round(
            atomic_nonresident - direct['register_nonresident'], 2),
        'multiready_over_mailbox_resident': round(
            multiready_resident - atomic_resident, 2),
        'multiready_over_mailbox_nonresident': round(
            multiready_nonresident - atomic_nonresident, 2),
        'multiready_over_direct_resident': round(
            multiready_resident - direct['register_resident'], 2),
        'multiready_over_direct_nonresident': round(
            multiready_nonresident - direct['register_nonresident'], 2),
        'multiready_residency_penalty': round(
            multiready_nonresident - multiready_resident, 2),
        'roundrobin_over_fixed_priority_nonresident': round(
            roundrobin_fpga - multiready_nonresident, 2),
        'roundrobin_time_us_at_18mhz': round(roundrobin_fpga / 18, 3),
        'linux_handoff_to_roundrobin_speedup_range': [
            round(5496 / roundrobin_fpga, 1),
            round(5595 / roundrobin_fpga, 1),
        ],
    },
}
for kind in ('resident', 'nonresident'):
    fpga = report[kind]['fpga']
    assert fpga['parseable_rows'] == report['expected_fpga_rows']
    assert fpga['custom_pass'] and fpga['core_pass']
    assert all(mode['all_rows_correct'] for mode in fpga['modes'].values())
    multi = report['multiready'][kind]['fpga']
    assert multi['parseable_rows'] == 16
    assert multi['custom_pass'] and multi['core_pass']
    assert multi['all_rows_correct'] and multi['spectator_bit_preserved']
    assert multi['total_sc_failures'] == 0
for platform in ('simulator', 'fpga'):
    fair = report['roundrobin_three_context'][platform]
    assert fair['custom_pass'] and fair['core_pass']
    assert fair['all_rows_correct'] and fair['all_three_contexts_completed']
    assert fair['total_sc_failures'] == 0
assert report['roundrobin_three_context']['fpga']['parseable_rows'] == 16
print(json.dumps(report, indent=2, sort_keys=True))
