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
report = {
    'nonresident': nonresident,
    'resident': resident,
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
    },
}
for kind in ('resident', 'nonresident'):
    fpga = report[kind]['fpga']
    assert fpga['parseable_rows'] == report['expected_fpga_rows']
    assert fpga['custom_pass'] and fpga['core_pass']
    assert all(mode['all_rows_correct'] for mode in fpga['modes'].values())
print(json.dumps(report, indent=2, sort_keys=True))
