#!/usr/bin/env python3
"""Independently recheck embedded archive preservation and matched image bytes."""
import gzip
import json
from pathlib import Path
import struct
import zlib

import build_pair as gate


def verify_records(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            path = Path(value['path'])
            assert gate.digest(path.read_bytes()) == value['sha256'], str(path)
            if 'bytes' in value:
                assert path.stat().st_size == value['bytes'], str(path)
        for child in value.values():
            verify_records(child)
    elif isinstance(value, list):
        for child in value:
            verify_records(child)


def differences(a, b):
    assert len(a) == len(b)
    return [dict(offset=hex(i), original=hex(x), control=hex(y))
            for i, (x, y) in enumerate(zip(a, b)) if x != y]


def main():
    manifest_path = gate.HERE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    assert manifest['state'] == 'embedded-pair-offline-verified'
    verify_records(manifest)
    assert manifest_path.read_bytes() == (gate.OUT / 'manifest.json').read_bytes()
    original = gate.CPIO.read_bytes()
    archive = Path(manifest['embedded_cpio']['path']).read_bytes()
    appendix = Path(manifest['appendix']['path']).read_bytes()
    # Use the earlier feasibility parser, independent of the builder parser.
    feasibility = gate.load_module(gate.FEASIBILITY, 'independent_newc_reader')
    before, after = list(feasibility.entries(original)), list(feasibility.entries(archive))
    assert len(before) == 419 and len(after) > len(before)
    changed = []
    for old, new in zip(before, after):
        name, fields, header, body, end, data = old
        new_name, new_fields, new_header, new_body, new_end, new_data = new
        assert name == new_name
        if name == gate.SMOKE:
            changed.append(name)
            expected = list(fields)
            expected[6] = len(gate.STUB)
            assert new_fields == expected and new_data == gate.STUB
            expected_header = bytearray(original[header:body])
            expected_header[54:62] = ('%08x' % len(gate.STUB)).encode()
            assert archive[new_header:new_body] == bytes(expected_header)
        else:
            assert fields == new_fields and data == new_data
            assert original[header:end] == archive[new_header:new_end]
    assert changed == [gate.SMOKE]
    appended = {row[0]: row for row in feasibility.entries(appendix)}
    for item in manifest['payloads']:
        assert appended[item['destination']][5] == Path(item['path']).read_bytes()
    padded = Path(manifest['padded_gzip']['path']).read_bytes()
    decoder = zlib.decompressobj(31)
    decoded = decoder.decompress(padded) + decoder.flush()
    assert decoder.eof and decoded == archive and gzip.decompress(padded) == archive
    consumed = len(padded) - len(decoder.unused_data)
    assert decoder.unused_data == b'\0' * (gate.SPAN - consumed)
    crc, size = struct.unpack('<II', padded[consumed - 8:consumed])
    assert crc == zlib.crc32(archive) & 0xffffffff and size == len(archive)
    assert consumed == manifest['compression']['gzip_bytes'] and len(padded) == gate.SPAN
    payloads, elfs = [], []
    for label in ('baseline', 'control'):
        arm = manifest['arms'][label]
        old, new = [Path(arm[key]['path']).read_bytes() for key in ('source_payload', 'payload')]
        assert len(new) == len(old) == gate.PAYLOAD_SIZE
        assert new[gate.OFFSET:gate.OFFSET + gate.SPAN] == padded
        assert old[:gate.OFFSET] == new[:gate.OFFSET]
        assert old[gate.OFFSET + gate.SPAN:] == new[gate.OFFSET + gate.SPAN:]
        for key in ('converted', 'extracted'):
            assert Path(arm[key]['path']).read_bytes() == new
        assert Path(arm['reverse']['path']).read_bytes() == Path(arm['source_nbf']['path']).read_bytes()
        assert gate.outside_kernel(Path(arm['nbf']['path'])) == gate.outside_kernel(Path(arm['source_nbf']['path']))
        old_elf, new_elf = [Path(arm[key]['path']).read_bytes() for key in ('source_elf', 'elf')]
        offset = int(arm['rootfs_elf_offset'], 16)
        assert len(old_elf) == len(new_elf)
        assert old_elf[:offset] == new_elf[:offset] and old_elf[offset + gate.SPAN:] == new_elf[offset + gate.SPAN:]
        assert new_elf[offset:offset + gate.SPAN] == padded
        for row in gate.sections(old_elf):
            if row['kind'] == 1 and row['flags'] & 4:
                begin, end = row['offset'], row['offset'] + row['size']
                assert old_elf[begin:end] == new_elf[begin:end]
        payloads.append(new)
        elfs.append(new_elf)
    binary_diff = differences(*payloads)
    elf_diff = differences(*elfs)
    assert binary_diff == [dict(offset='0x813fe8', original='0x1d', control='0x21')]
    assert elf_diff == [dict(offset='0x814fe8', original='0x1d', control='0x21')]
    pair = gate.pair_difference(Path(manifest['source_nbf']['path']), Path(manifest['candidate_nbf']['path']))
    result = dict(state='PASS', scope='offline only; new rootfs baseline, no board/performance acceptance',
                  manifest=gate.record(manifest_path), verifier=gate.record(Path(__file__)),
                  full_payload_differences=binary_diff, full_elf_differences=elf_diff,
                  sole_nbf_difference=pair, changed_modes=[14],
                  original_cpio_members=419, only_changed_original_member=gate.SMOKE,
                  all_other_original_raw_records_and_metadata_exact=True,
                  embedded_payloads_byte_exact=True, gzip_crc_isize_nul_padding_verified=True,
                  both_elf_objcopy_and_nbf_extractions_exact=True,
                  both_reverse_nbf_byte_exact=True, both_nonkernel_record_streams_unchanged=True,
                  both_executable_section_sets_unchanged_during_embedding=True,
                  original_accepted_inputs_unchanged=True)
    rendered = json.dumps(result, indent=2) + '\n'
    (gate.HERE / 'verification.json').write_text(rendered)
    (gate.OUT / 'verification.json').write_text(rendered)
    print('EMBEDDED_PAIR_INDEPENDENT_VERIFICATION_PASS')


if __name__ == '__main__':
    main()
