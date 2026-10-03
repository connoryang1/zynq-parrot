#!/usr/bin/env python3
import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROW = re.compile(
    r'Atomic fence sample/mode/cycles/x100-per-op/ok/observed/complete/'
    r'word/source: (0x[0-9a-f]+) (fence|aqrl) '
    r'(0x[0-9a-f]+) (0x[0-9a-f]+) (0x[0-9a-f]+) '
    r'(0x[0-9a-f]+) (0x[0-9a-f]+) (0x[0-9a-f]+) (0x[0-9a-f]+)')


def analyze(name, physical):
    text = (HERE / name).read_text(errors='replace').replace('\r', '')
    rows = []
    for match in ROW.finditer(text):
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
            'all_rows_correct': all(row[4:] == (1, 2, 1, 4, 0)
                                    for row in selected),
        }
    result['fence_delta_cycles_per_operation'] = round((
        result['modes']['fence']['median_cycles_per_operation']
        - result['modes']['aqrl']['median_cycles_per_operation']), 2)
    result['custom_pass'] = '[BSG-PASS] atomic fence cost' in text
    result['core_pass'] = ('CORE[0] PASS' if physical else 'CORE PASS') in text
    return result


report = {
    'simulator': analyze('sim-run-accepted.log', False),
    'fpga': analyze('physical-baremetal.log', True),
    'expected_fpga_rows': 32,
}
assert report['fpga']['parseable_rows'] == report['expected_fpga_rows']
assert report['fpga']['custom_pass'] and report['fpga']['core_pass']
assert all(mode['all_rows_correct']
           for mode in report['fpga']['modes'].values())
print(json.dumps(report, indent=2, sort_keys=True))
