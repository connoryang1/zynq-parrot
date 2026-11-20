#!/usr/bin/env python3
"""Conservatively inspect baseline kernel/firmware bytes at every halfword.

Potential CSR encodings in data are reported too. This scan does not silently
whitelist a match or treat skipped NBF writes as observed runtime DRAM bytes.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'linux-tests'))
from splice_linux_kernel_nbf import MEMORY_COMMANDS, parse_line

OUT = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/kernel27')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scan(data, base):
    matches = []
    for offset in range(0, len(data) - 3, 2):
        if data[offset] & 0x7f != 0x73:
            continue
        word = struct.unpack_from('<I', data, offset)[0]
        if (word >> 12) & 7 and word >> 20 == 0x5c1:
            matches.append({'offset': hex(offset), 'address': hex(base + offset),
                            'word': '0x{:08x}'.format(word), 'funct3': (word >> 12) & 7,
                            'rd': (word >> 7) & 31, 'rs1': (word >> 15) & 31,
                            'classification': 'unclassified potential encoding; not automatically executable or safe'})
    return matches


def main():
    package = json.loads((HERE / 'package-manifest.json').read_text())
    source = Path(package['source_nbf']['path'])
    source_bytes = source.read_bytes()
    if sha(source_bytes) != package['source_nbf']['sha256']:
        raise SystemExit('source NBF identity mismatch')
    kernel = Path(package['old_payload']['path']).read_bytes()
    if sha(kernel) != package['old_payload']['sha256']:
        raise SystemExit('old kernel identity mismatch')
    base, size = 0x80000000, 0x200000
    firmware, written = bytearray(size), bytearray(size)
    widths, overwrites = {}, []
    for index, raw in enumerate(source_bytes.splitlines(), 1):
        command, address, value = parse_line(raw.decode('ascii'))
        width = MEMORY_COMMANDS.get(command)
        if not width or address >= base + size or address + width <= base:
            continue
        if not (base <= address and address + width <= base + size) or address % width:
            raise ValueError('unaligned or crossing firmware write at NBF line {}'.format(index))
        offset = address - base
        replacement = value.to_bytes(8, 'little')[:width]
        if any(written[offset:offset + width]):
            overwrites.append({'line': index, 'address': hex(address), 'width': width,
                               'previous_bytes_hex': bytes(firmware[offset:offset + width]).hex(),
                               'new_bytes_hex': replacement.hex(),
                               'policy': 'apply in source NBF order and retain explicit overwrite evidence'})
        firmware[offset:offset + width] = replacement
        written[offset:offset + width] = b'\x01' * width
        widths[str(width)] = widths.get(str(width), 0) + 1
    raw = bytes(firmware)
    memory_path = OUT / 'baseline-firmware-memory-80000000-80200000.bin'
    if memory_path.exists():
        raise SystemExit('refusing to overwrite firmware evidence')
    memory_path.write_bytes(raw)
    kernel_matches, firmware_matches = scan(kernel, 0x80200000), scan(raw, base)
    result = {'scope': 'complete reconstructed baseline byte windows at every two-byte boundary, including cross-record boundaries',
              'predicate': 'little-endian 32-bit word: opcode low7=0x73, funct3 nonzero, csr high12=0x5c1',
              'alignment': 2, 'source_nbf_sha256': sha(source_bytes),
              'kernel': {'path': package['old_payload']['path'], 'base': '0x80200000', 'bytes': len(kernel),
                         'sha256': sha(kernel), 'matches': kernel_matches},
              'firmware': {'path': str(memory_path), 'base': hex(base), 'end_exclusive': hex(base + size),
                           'bytes': size, 'sha256': sha(raw), 'written_bytes': sum(written),
                           'nbf_records_by_width_bytes': widths,
                           'ordered_overwrites': overwrites,
                           'unwritten_bytes': 'zero-filled nominal reconstruction; not a statement about arbitrary stale runtime DRAM',
                           'matches': firmware_matches},
              'other_memory': 'not scanned; no completeness claim outside the two named windows',
              'result': 'NO_ENCODINGS_IN_RECONSTRUCTED_WINDOWS' if not kernel_matches and not firmware_matches else 'REVIEW_REQUIRED'}
    rendered = json.dumps(result, indent=2) + '\n'
    (HERE / 'baseline-halfword-csr5c1.json').write_text(rendered)
    (OUT / 'baseline-halfword-csr5c1.json').write_text(rendered)
    print('kernel matches={} firmware matches={} result={}'.format(len(kernel_matches), len(firmware_matches), result['result']))
    for label, matches in (('kernel', kernel_matches), ('firmware', firmware_matches)):
        for match in matches:
            print(label, json.dumps(match))


if __name__ == '__main__':
    main()
