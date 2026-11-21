#!/usr/bin/env python3
"""Recheck capped images, load-write ownership and complete FDT buffer bounds."""
import hashlib
import json
from pathlib import Path
import struct

import build_pair as gate


def load_write_bound(path):
    count, maximum, separate = 0, gate.BASE, 0
    with path.open() as source:
        for line in source:
            command, address, data = gate.parse_line(line)
            width = gate.MEMORY_COMMANDS.get(command)
            if width and address < gate.BASE + gate.RAM_BYTES and address + width > gate.BASE:
                if address < gate.BASE or address + width > gate.BASE + gate.OWNED_BYTES:
                    raise ValueError('DDR load write, including its tail, exceeds the owned46MiB buffer')
                if not 0 <= data < 1 << (width * 8):
                    raise ValueError('DDR load data exceeds its actual NBF width')
                count += 1
                maximum = max(maximum, address + width)
            else:
                separate += 1
    if not count:
        raise ValueError('NBF contains no advertised-DDR writes')
    return dict(ddr_write_count=count, separate_config_or_mmio_records=separate,
                maximum_load_end_exclusive=hex(maximum), maximum_load_offset=hex(maximum - gate.BASE - 1),
                allocation_bytes=gate.OWNED_BYTES, all_write_tails_within_allocation=True)


def verify_records(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            path = Path(value['path'])
            assert gate.sha(path) == value['sha256'], str(path)
            assert path.stat().st_size == value['bytes'], str(path)
        for child in value.values():
            verify_records(child)
    elif isinstance(value, list):
        for child in value:
            verify_records(child)


def main():
    manifest_path = gate.HERE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    assert manifest['state'] == 'embedded46-pair-offline-verified'
    verify_records(manifest)
    assert manifest_path.read_bytes() == (gate.OUT / 'manifest.json').read_bytes()
    bounds, kernel_hashes = {}, {}
    for label in ('baseline', 'control'):
        arm = manifest['arms'][label]
        source, target = Path(arm['source_nbf']['path']), Path(arm['nbf']['path'])
        bounds[label] = dict(source=load_write_bound(source), capped=load_write_bound(target))
        old, _ = gate.reconstruct(source)
        new, _ = gate.reconstruct(target)
        old_dtb = Path(arm['original_dtb']['path']).read_bytes()
        new_dtb = Path(arm['capped_dtb']['path']).read_bytes()
        a, b = gate.parse_fdt(old_dtb), gate.parse_fdt(new_dtb)
        assert len(old_dtb) == len(new_dtb) == 1209
        old_prop, old_value, new_value = gate.bootarg_edit(a)
        start = old_prop['offset']
        assert old_dtb[:start] == new_dtb[:start]
        assert old_dtb[start + old_prop['bytes']:] == new_dtb[start + old_prop['bytes']:]
        assert new_dtb[start:start + old_prop['bytes']] == new_value + b'\0'
        assert a['nodes'] == b['nodes'] and a['reservations'] == b['reservations']
        for left, right in zip(a['properties'], b['properties']):
            if left['name'] == 'bootargs' and left['node'] in ('/chosen', '/chosen@0'):
                assert left['bytes'] == right['bytes'] == 49
            else:
                assert left == right
        differences = [i for i, (x, y) in enumerate(zip(old, new)) if x != y]
        expected = [gate.DTB_ADDRESS - gate.BASE + start + i
                    for i, (x, y) in enumerate(zip(old_value, new_value)) if x != y]
        assert differences == expected and len(differences) == 7
        begin = gate.PAYLOAD_BASE - gate.BASE
        assert old[begin:begin + gate.PAYLOAD_BYTES] == new[begin:begin + gate.PAYLOAD_BYTES]
        kernel_hashes[label] = hashlib.sha256(new[begin:begin + gate.PAYLOAD_BYTES]).hexdigest()
        assert kernel_hashes[label] == arm['kernel_payload_sha256']
        assert Path(arm['reverse']['path']).read_bytes() == source.read_bytes()
        declared, copied = a['total'], (a['total'] + 7) & ~7
        assert gate.BASE <= gate.DTB_ADDRESS and gate.DTB_ADDRESS + copied <= gate.BASE + gate.OWNED_BYTES
        assert gate.BASE <= gate.NEXT_ARG1 and gate.NEXT_ARG1 + copied <= gate.BASE + gate.OWNED_BYTES
        bounds[label]['fdt'] = dict(declared_bytes=declared, copied_buffer_bytes=copied,
                                    source_begin=hex(gate.DTB_ADDRESS), source_end=hex(gate.DTB_ADDRESS + copied),
                                    runtime_begin=hex(gate.NEXT_ARG1), runtime_end=hex(gate.NEXT_ARG1 + copied),
                                    entire_initial_fdt_and_rounded_copy_fit=True)
    baseline, control = [Path(manifest['arms'][label]['nbf']['path']).read_bytes() for label in ('baseline', 'control')]
    assert len(baseline) == len(control)
    differences = [dict(offset=hex(i), original=hex(x), control=hex(y))
                   for i, (x, y) in enumerate(zip(baseline, control)) if x != y]
    assert differences == [dict(offset='0x25f22ba', original='0x31', control='0x32'),
                           dict(offset='0x25f22bb', original='0x64', control='0x31')]
    result = dict(state='PASS', scope='offline allocation-policy proof; runtime boot gates still required',
                  manifest=gate.record(manifest_path), verifier=gate.record(Path(__file__)),
                  ddr_load_and_fdt_bounds=bounds, all_kernel_payloads_unchanged=kernel_hashes,
                  full_nbf_ascii_pair_differences=differences, changed_modes=[14],
                  all_changes_only_existing_bootargs_ascii_padding=True,
                  fdt_property_length_total_size_memory_reg_and_other_properties_unchanged=True,
                  original_and_embedded_rootfs_unchanged=True, reverse_nbf_byte_exact=True,
                  expected_dma32_end='0x82dfffff', expected_memory_total_kib=47104,
                  expected_runner_allocation_bytes=48234496,
                  runtime_limits='Source intent is not a runtime proof. Require actual46MB notice,47104K total,DMA32end82dfffff and48234496-byte owned allocation before performance acceptance.')
    rendered = json.dumps(result, indent=2) + '\n'
    (gate.HERE / 'verification.json').write_text(rendered)
    (gate.OUT / 'verification.json').write_text(rendered)
    print('EMBEDDED46_INDEPENDENT_VERIFICATION_PASS')


if __name__ == '__main__':
    main()
