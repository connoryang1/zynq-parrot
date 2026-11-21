#!/usr/bin/env python3
"""Embed unchanged workload files into a new, fixed-span matched Linux pair.

Only the obsolete smoke member is replaced inside the original archive.
These images are restricted to the interactive rdinit=/bin/sh workflow.
"""
import gzip
import hashlib
import importlib.util
from itertools import zip_longest
import json
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARTIFACTS = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120')
OUT = ARTIFACTS / 'embedded-workloads'
FEASIBILITY = ROOT / 'research/embedded-workload-feasibility-20261120/reproduce_feasibility.py'
FEASIBILITY_SHA = 'e3a64b598f2c740e37347dabf85464434e0972bb7cbfab21759734bcc9c79afe'
SOURCE_PROOF = ROOT / 'research/embedded-workload-feasibility-20261120/feasibility.json'
SDK_KERNEL = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/build/linux-6.6')
CPIO = ARTIFACTS / 'kernel27/accepted-rootfs.cpio'
GZIP = ARTIFACTS / 'kernel27/accepted-rootfs.cpio.gz'
CPIO_SHA = 'e2f7dbc4d02d0ae99bb66832fe94b4882e19d7c95acd2cc0521299ff6aa73f50'
GZIP_SHA = '0fbebeabd9fb4e152c0f79efe19f7275d08fd5956c97f0f022f829221735b5cf'
SMOKE = 'usr/bin/ctxtsw_user_smoke'
SMOKE_SHA = '1f8676bdc62331a7790f61aa0496f5ee76ff92fc411e803ec6184d9bab5160a5'
STUB = b'#!/bin/sh\nexit 1\n'
OFFSET, SPAN, PAYLOAD_SIZE = 0xc126b0, 3303052, 24034304
MODE_OFFSET, MODE_VMA = 0x813fe8, 0xffffffff80813fe8
PREFIX = '/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux-'
sys.path.insert(0, str(ROOT / 'linux-tests'))
from extract_linux_kernel_nbf import extract
from splice_linux_kernel_nbf import MEMORY_COMMANDS, parse_line, splice


def digest(data):
    return hashlib.sha256(data).hexdigest()


def record(path):
    return dict(path=str(path.resolve()), sha256=digest(path.read_bytes()), bytes=path.stat().st_size)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entries(archive):
    """Parse aligned newc records, including concatenated archives and NULs."""
    offset = 0
    while offset < len(archive):
        if archive[offset] == 0:
            offset += 1
            continue
        if offset % 4 or archive[offset:offset + 6] not in (b'070701', b'070702'):
            raise ValueError('unaligned or invalid newc header')
        if offset + 110 > len(archive):
            raise ValueError('truncated newc header')
        try:
            fields = [int(archive[offset + 6 + i * 8:offset + 14 + i * 8], 16) for i in range(13)]
        except ValueError as error:
            raise ValueError('nonhex newc field') from error
        namesize, size = fields[11], fields[6]
        name_end = offset + 110 + namesize
        if not namesize or name_end > len(archive) or archive[name_end - 1] != 0:
            raise ValueError('invalid newc pathname')
        encoded = archive[offset + 110:name_end - 1]
        if b'\0' in encoded:
            raise ValueError('embedded NUL in newc pathname')
        name = encoded.decode('utf-8')
        if name.startswith('/') or '..' in name.split('/'):
            raise ValueError('unsafe newc pathname')
        body = (name_end + 3) & ~3
        end = (body + size + 3) & ~3
        if end > len(archive):
            raise ValueError('truncated newc body')
        data = archive[body:body + size]
        if archive[offset:offset + 6] == b'070702' and sum(data) & 0xffffffff != fields[12]:
            raise ValueError('newc CRC mismatch')
        yield dict(name=name, fields=fields, start=offset, body=body, end=end, data=data)
        offset = end


def build_archive(original, payloads, member):
    """Preserve original records and add only the reviewed smoke replacement."""
    old = list(entries(original))
    names = [row['name'] for row in old]
    if len(set(names)) != len(names) or names.count('TRAILER!!!') != 1:
        raise ValueError('original archive has duplicate names or unexpected trailers')
    selected = [row for row in old if row['name'] == SMOKE]
    if len(selected) != 1:
        raise ValueError('obsolete smoke member is not unique')
    selected = selected[0]
    if (digest(selected['data']) != SMOKE_SHA or not stat.S_ISREG(selected['fields'][1])
            or selected['fields'][4] != 1 or original[selected['start']:selected['start'] + 6] != b'070701'):
        raise ValueError('obsolete smoke identity/type/link contract differs')
    header = bytearray(original[selected['start']:selected['body']])
    header[54:62] = ('%08x' % len(STUB)).encode()
    replacement = bytes(header) + STUB + b'\0' * (-len(STUB) % 4)
    replaced = original[:selected['start']] + replacement + original[selected['end']:]
    new_original = list(entries(replaced))
    if len(old) != len(new_original):
        raise ValueError('replacement changes original member count')
    preservation = []
    for before, after in zip(old, new_original):
        if before['name'] != after['name']:
            raise ValueError('replacement changes member order')
        expected = list(before['fields'])
        if before['name'] == SMOKE:
            expected[6] = len(STUB)
            if after['fields'] != expected or after['data'] != STUB:
                raise ValueError('stub replacement changed other metadata')
        elif (before['fields'] != after['fields'] or before['data'] != after['data']
              or original[before['start']:before['end']] != replaced[after['start']:after['end']]):
            raise ValueError('another original newc member changed')
        preservation.append(dict(name=before['name'], original_fields=before['fields'],
                                 resulting_fields=after['fields'],
                                 original_raw_sha256=digest(original[before['start']:before['end']]),
                                 resulting_raw_sha256=digest(replaced[after['start']:after['end']]),
                                 changed=before['name'] == SMOKE))
    parent_names = ('opt', 'opt/bp-resume')
    original_by_name = {row['name']: row for row in old}
    appendix = b''
    inode = 1
    for parent in parent_names:
        if parent in original_by_name:
            if not stat.S_ISDIR(original_by_name[parent]['fields'][1]):
                raise ValueError('embedded parent is not a directory')
        else:
            appendix += member(parent, b'', inode, 0o040755)
            inode += 1
    for destination, data in payloads:
        if destination not in ('plain', 'plain_resources', 'probe', 'zlib', 'libz.so.1'):
            raise ValueError('unexpected embedded payload name')
        path = 'opt/bp-resume/' + destination
        if path in original_by_name:
            raise ValueError('embedded destination already exists')
        appendix += member(path, data, inode, 0o100755)
        inode += 1
    if [name for name, _ in payloads] != ['plain', 'plain_resources', 'probe', 'zlib', 'libz.so.1']:
        raise ValueError('payload set/order differs from reviewed five files')
    appendix += member('TRAILER!!!', b'', 20, 0)
    archive = replaced + appendix
    appended = list(entries(appendix))
    mapping = {row['name']: row for row in appended}
    for name, data in payloads:
        row = mapping['opt/bp-resume/' + name]
        if row['data'] != data or row['fields'][1] != 0o100755 or row['fields'][2:6] != [0, 0, 1, 0]:
            raise ValueError('embedded payload bytes or deterministic metadata differ')
    final_names = {row['name'] for row in entries(archive) if stat.S_ISDIR(row['fields'][1])}
    if not set(parent_names) <= final_names:
        raise ValueError('embedded parent directory is missing')
    return archive, appendix, preservation


def compress_fixed(archive):
    compressed = gzip.compress(archive, compresslevel=9, mtime=0)
    if compressed != gzip.compress(archive, compresslevel=9, mtime=0):
        raise ValueError('gzip encoding is not deterministic')
    if len(compressed) > SPAN:
        raise ValueError('embedded archive exceeds the fixed compressed span')
    padded = compressed + b'\0' * (SPAN - len(compressed))
    check = zlib.decompressobj(31)
    decoded = check.decompress(padded) + check.flush()
    if decoded != archive or not check.eof or check.unused_data != b'\0' * (SPAN - len(compressed)):
        raise ValueError('gzip/padding stream contract failed')
    crc, size = struct.unpack('<II', compressed[-8:])
    if crc != zlib.crc32(archive) & 0xffffffff or size != len(archive) & 0xffffffff:
        raise ValueError('gzip CRC/ISIZE differs')
    if gzip.decompress(padded) != archive:
        raise ValueError('independent gzip roundtrip failed')
    return padded, dict(gzip_bytes=len(compressed), padding_bytes=SPAN - len(compressed),
                        span_bytes=len(padded), crc32=hex(crc), isize=size,
                        gzip_sha256=digest(compressed), padded_sha256=digest(padded))


def sections(elf):
    if elf[:6] != b'\x7fELF\x02\x01':
        raise ValueError('expected little-endian ELF64')
    table = struct.unpack_from('<Q', elf, 40)[0]
    stride, count, strings = struct.unpack_from('<HHH', elf, 58)
    rows = [struct.unpack_from('<IIQQQQIIQQ', elf, table + i * stride) for i in range(count)]
    string_data = elf[rows[strings][4]:rows[strings][4] + rows[strings][5]]
    return [dict(name=string_data[row[0]:].split(b'\0', 1)[0].decode(), kind=row[1], flags=row[2],
                 vma=row[3], offset=row[4], size=row[5]) for row in rows]


def replace_span(old, padded, offset=OFFSET):
    if old[offset:offset + SPAN] != GZIP.read_bytes():
        raise ValueError('original rootfs span does not match the accepted gzip')
    new = old[:offset] + padded + old[offset + SPAN:]
    if len(new) != len(old) or old[:offset] != new[:offset] or old[offset + SPAN:] != new[offset + SPAN:]:
        raise ValueError('bytes outside compressed rootfs changed')
    return new


def outside_kernel(path):
    hashed, count = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for raw in stream:
            command, address, _data = parse_line(raw.decode('ascii'))
            width = MEMORY_COMMANDS.get(command)
            if width and address < 0x80200000 + PAYLOAD_SIZE and address + width > 0x80200000:
                continue
            hashed.update(raw)
            count += 1
    return dict(records=count, ordered_bytes_sha256=hashed.hexdigest())


def pair_difference(baseline, control):
    differing = []
    with baseline.open('rb') as a, control.open('rb') as b:
        for number, (old, new) in enumerate(zip_longest(a, b), 1):
            if old != new:
                differing.append(dict(line=number, original=old.decode() if old else None,
                                      control=new.decode() if new else None))
    expected = dict(line=1075385, original='03_0000000080a13fe8_1073e0f77de3471d\n',
                    control='03_0000000080a13fe8_1073e0f77de34721\n')
    if differing != [expected]:
        raise ValueError('embedded NBF pair differs outside the mode14 instruction record')
    return differing[0]


def main():
    if OUT.exists() or (HERE / 'manifest.json').exists():
        raise SystemExit('refusing to overwrite embedded-pair evidence')
    if digest(FEASIBILITY.read_bytes()) != FEASIBILITY_SHA:
        raise SystemExit('reviewed feasibility generator differs')
    feasibility = load_module(FEASIBILITY, 'reviewed_feasibility')
    mode = load_module(ROOT / 'research/mode14-early-only-20261120/prepare_control.py', 'reviewed_mode14')
    review = json.loads((ROOT / 'research/mode14-early-only-20261120/manifest.json').read_text())
    if digest((ROOT / 'research/mode14-early-only-20261120/manifest.json').read_bytes()) != 'f5040dc8b5dfd919c7cb446d0e4aa05e5c4704a2b5c705b62f90e9acc3d9067b':
        raise SystemExit('original mode14 review manifest differs')
    original, old_gzip = CPIO.read_bytes(), GZIP.read_bytes()
    if digest(original) != CPIO_SHA or digest(old_gzip) != GZIP_SHA or len(old_gzip) != SPAN:
        raise SystemExit('accepted rootfs input identity mismatch')
    payloads, payload_records = [], []
    for name, source, expected in feasibility.PAYLOADS:
        data = source.read_bytes()
        if digest(data) != expected:
            raise SystemExit('payload differs: ' + str(source))
        payloads.append((name, data))
        payload_records.append(dict(destination='opt/bp-resume/' + name, **record(source)))
    proof = json.loads(SOURCE_PROOF.read_text())
    source_records = []
    for item in proof['primary_actual_linux_source']:
        source = Path(item['path'])
        if digest(source.read_bytes()) != item['sha256']:
            raise SystemExit('primary Linux format/padding source differs: ' + str(source))
        source_records.append(item)
    OUT.mkdir()
    archive, appendix, preservation = build_archive(original, payloads, feasibility.member)
    padded, compression = compress_fixed(archive)
    (OUT / 'embedded-rootfs.cpio').write_bytes(archive)
    (OUT / 'embedded-appendix.cpio').write_bytes(appendix)
    (OUT / 'embedded-rootfs.cpio.gz.padded').write_bytes(padded)
    (OUT / 'cpio-preservation.json').write_text(json.dumps(preservation, indent=2) + '\n')
    for item in source_records:
        source = Path(item['path'])
        target = OUT / 'linux-source-proof' / source.relative_to(SDK_KERNEL)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        item['snapshot'] = record(target)
    cpio = shutil.which('cpio')
    if not cpio:
        raise RuntimeError('host cpio is required for independent appendix extraction')
    for name, data in payloads:
        command = [cpio, '-i', '--to-stdout', '--quiet', 'opt/bp-resume/' + name]
        result = subprocess.run(command, input=appendix, capture_output=True, timeout=10)
        if result.returncode or result.stdout != data:
            raise RuntimeError('host cpio cannot reconstruct exact payload ' + name)
    arms = {}
    for label, nbf_key, elf_key, payload_key in (
            ('baseline', 'source_nbf', 'original_elf', 'original_payload'),
            ('control', 'candidate_nbf', 'control_elf', 'control_payload')):
        source_nbf, source_elf, source_payload = [Path(review[key]['path']) for key in (nbf_key, elf_key, payload_key)]
        for key, path in ((nbf_key, source_nbf), (elf_key, source_elf), (payload_key, source_payload)):
            if digest(path.read_bytes()) != review[key]['sha256']:
                raise RuntimeError('source arm identity changed: ' + key)
        old_binary, old_elf = source_payload.read_bytes(), source_elf.read_bytes()
        binary = replace_span(old_binary, padded)
        if len(binary) != PAYLOAD_SIZE:
            raise RuntimeError('payload length changed')
        rows = sections(old_elf)
        matching = [row for row in rows if row['kind'] == 1 and row['flags'] & 2
                    and row['vma'] <= 0xffffffff80000000 + OFFSET
                    and 0xffffffff80000000 + OFFSET + SPAN <= row['vma'] + row['size']]
        if len(matching) != 1 or matching[0]['flags'] & 4:
            raise RuntimeError('rootfs is not in exactly one nonexecutable allocated section')
        section = matching[0]
        file_offset = section['offset'] + 0xffffffff80000000 + OFFSET - section['vma']
        new_elf = replace_span(old_elf, padded, file_offset)
        exec_proof = []
        for row in rows:
            if row['flags'] & 4 and row['kind'] == 1:
                start, end = row['offset'], row['offset'] + row['size']
                if old_elf[start:end] != new_elf[start:end]:
                    raise RuntimeError('an executable section changed during embedding')
                exec_proof.append(dict(section=row['name'], bytes=row['size'], sha256=digest(old_elf[start:end])))
        elf, payload = OUT / (label + '.elf'), OUT / (label + '.bin')
        elf.write_bytes(new_elf)
        payload.write_bytes(binary)
        converted = OUT / (label + '-from-elf.bin')
        command = [PREFIX + 'objcopy', '-O', 'binary', str(elf), str(converted)]
        subprocess.run(command, check=True)
        if converted.read_bytes() != binary:
            raise RuntimeError('embedded ELF conversion differs from payload')
        nbf = OUT / ('linux-prefix32-embedded-' + label + '-shell.nbf')
        print('Splicing embedded ' + label + ' arm', flush=True)
        forward = splice(source_nbf, source_payload, payload, nbf)
        reverse = OUT / (label + '-reverse.nbf')
        splice(nbf, payload, source_payload, reverse)
        if reverse.read_bytes() != source_nbf.read_bytes():
            raise RuntimeError('reverse splice does not reconstruct exact source arm')
        extracted = OUT / (label + '-extracted.bin')
        extract(nbf, extracted, PAYLOAD_SIZE)
        if extracted.read_bytes() != binary:
            raise RuntimeError('embedded NBF payload reconstruction differs')
        nonkernel = outside_kernel(source_nbf)
        if outside_kernel(nbf) != nonkernel:
            raise RuntimeError('nonkernel NBF records changed')
        trailing_word = (OFFSET + SPAN) & ~7
        if binary[OFFSET + SPAN:trailing_word + 8] != old_binary[OFFSET + SPAN:trailing_word + 8]:
            raise RuntimeError('outside bytes in final partial NBF word changed')
        arms[label] = dict(source_nbf=record(source_nbf), source_elf=record(source_elf),
                           source_payload=record(source_payload), nbf=record(nbf), elf=record(elf),
                           payload=record(payload), converted=record(converted), extracted=record(extracted),
                           reverse=record(reverse), objcopy_command=command, forward_splice=forward,
                           nonkernel_records=nonkernel, executable_sections_unchanged=exec_proof,
                           rootfs_elf_offset=hex(file_offset), final_partial_word_outside_bytes=binary[OFFSET + SPAN:trailing_word + 8].hex(),
                           outside_rootfs_prefix_sha256=digest(binary[:OFFSET]),
                           outside_rootfs_suffix_sha256=digest(binary[OFFSET + SPAN:]))
    a, b = Path(arms['baseline']['payload']['path']).read_bytes(), Path(arms['control']['payload']['path']).read_bytes()
    differences = [i for i, pair in enumerate(zip(a, b)) if pair[0] != pair[1]]
    if differences != [MODE_OFFSET] or (a[MODE_OFFSET], b[MODE_OFFSET]) != (0x1d, 0x21):
        raise RuntimeError('embedded payload pair is not the one-byte mode14 control')
    elf_a, elf_b = [Path(arms[label]['elf']['path']).read_bytes() for label in ('baseline', 'control')]
    elf_difference = [i for i, pair in enumerate(zip(elf_a, elf_b)) if pair[0] != pair[1]]
    if len(elf_a) != len(elf_b) or elf_difference != [0x814fe8]:
        raise RuntimeError('embedded ELF pair differs beyond the mode14 byte')
    before, after = mode.selected_mode_triggers(a), mode.selected_mode_triggers(b)
    if [i for i in range(256) if before[i] != after[i]] != [14]:
        raise RuntimeError('embedded pair changes another mode')
    modes = OUT / 'all-256-mode-proof.json'
    modes.write_text(json.dumps([dict(mode=i, original_trigger=before[i], control_trigger=after[i]) for i in range(256)], indent=2) + '\n')
    pair_record = pair_difference(Path(arms['baseline']['nbf']['path']), Path(arms['control']['nbf']['path']))
    if digest(CPIO.read_bytes()) != CPIO_SHA or digest(GZIP.read_bytes()) != GZIP_SHA:
        raise RuntimeError('accepted rootfs inputs changed')
    manifest = dict(state='embedded-pair-offline-verified', image_pair='embedded',
                    scope='New rootfs baseline; interactive rdinit=/bin/sh only; no board or performance acceptance',
                    original_cpio=record(CPIO), original_gzip=record(GZIP),
                    feasibility_generator=record(FEASIBILITY), feasibility_source_proof=record(SOURCE_PROOF),
                    embedded_cpio=record(OUT / 'embedded-rootfs.cpio'), appendix=record(OUT / 'embedded-appendix.cpio'),
                    padded_gzip=record(OUT / 'embedded-rootfs.cpio.gz.padded'), compression=compression,
                    cpio_preservation=record(OUT / 'cpio-preservation.json'), payloads=payload_records,
                    obsolete_smoke=dict(name=SMOKE, original_sha256=SMOKE_SHA, stub=STUB.decode(), stub_sha256=digest(STUB)),
                    fixed_span=dict(offset=hex(OFFSET), bytes=SPAN, end_exclusive=hex(OFFSET + SPAN)),
                    primary_linux_source=source_records, arms=arms,
                    source_nbf=arms['baseline']['nbf'], candidate_nbf=arms['control']['nbf'],
                    changed_modes=[14], all_modes=record(modes), sole_nbf_difference=pair_record,
                    reverse_nbf_byte_exact=True, source_inputs_unchanged=True,
                    kernel_pair_differences=[dict(offset=hex(MODE_OFFSET), original='0x1d', control='0x21')],
                    elf_pair_differences=[dict(offset='0x814fe8', original='0x1d', control='0x21')],
                    runtime_library='Copy or use opt/bp-resume/libz.so.1 with explicit LD_LIBRARY_PATH; embedded files do not alter the system library.',
                    limits=['Cannot pool with original e2f7 rootfs measurements.',
                            'Legacy /sbin/init auto-smoke workflow is intentionally unsupported; the stub exits 1.',
                            'Linux source confirms concatenated newc, gzip termination and NUL padding behavior; runtime boot still requires a reserved-board gate.'],
                    environment=dict(python=sys.version, zlib=zlib.ZLIB_RUNTIME_VERSION), driver=record(Path(__file__)))
    rendered = json.dumps(manifest, indent=2) + '\n'
    (HERE / 'manifest.json').write_text(rendered)
    (OUT / 'manifest.json').write_text(rendered)
    print('EMBEDDED_PAIR_OFFLINE_PASS', flush=True)
    for label in arms:
        print(label.upper() + '_NBF_SHA256=' + arms[label]['nbf']['sha256'], flush=True)


if __name__ == '__main__':
    main()
