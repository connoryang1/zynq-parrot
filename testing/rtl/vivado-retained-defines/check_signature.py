#!/usr/bin/env python3
"""Check all synthesized macro bits across packaged-IP child synthesis."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def signature(text):
    # Accept only direct, uniquely driven constant outputs from the real
    # synthesis netlist. Named constant nets must have their primitive drivers.
    for primitive, pin, name in (('GND', 'G', 'const0'), ('VCC', 'P', 'const1')):
        pattern = rf'\b{primitive}\s+\S+\s*\(\.{pin}\(\\<{name}>\s*\)\);'
        if len(re.findall(pattern, text)) != 1:
            raise ValueError('missing or ambiguous constant primitive: '+name)
    pattern = r'\bOBUF\s+\\[^\n]+\s*\(\.I\(\\<const([01])>\s*\),\s*\.O\((\w+)\[(\d+)\]\)\);'
    rows = re.findall(pattern, text)
    bits = {}
    ports = set()
    for value, port, bit in rows:
        bit = int(bit)
        if bit in bits:
            raise ValueError('duplicate synthesized output bit')
        bits[bit] = int(value)
        ports.add(port)
    if set(bits) != set(range(192)) or len(ports) != 1:
        raise ValueError('expected exactly192 constant output bits on one port')
    value = sum(v << b for b, v in bits.items())
    return [(value >> (32 * b)) & 0xffffffff for b in range(5, -1, -1)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('probe', type=Path)
    args = ap.parse_args()
    results = {}
    for arm, expected in (('positive', [1, 1280, 1280, 256, 1, 200]), ('negative', [0, 64, 64, 64, 0, 0])):
        path = args.probe / (arm+'_signature.v')
        blob = path.read_bytes()
        actual = signature(blob.decode())
        if actual != expected:
            raise ValueError(f'{arm} actual={actual}, expected={expected}')
        results[arm] = dict(path=str(path), sha256=hashlib.sha256(blob).hexdigest(), actual=actual)
    print(json.dumps(dict(state='PASS actual nested packaged-IP constants, launched child synthesis; no full-design fit claim', arms=results), indent=2))


if __name__ == '__main__':
    main()
