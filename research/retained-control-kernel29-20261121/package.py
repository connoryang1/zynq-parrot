#!/usr/bin/env python3
"""Verify the actual linked ABI and replace only the bounded c7 kernel payload."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

import build

HERE, ROOT = build.HERE, build.ROOT
OUT = build.EXTERNAL / 'package'
OLD_PACKAGE = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/kernel27-accepted-rootfs')
SOURCE = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/retention-kernel46-20261120/linux-prefix32-retention27-accepted-rootfs-mem46-shell.nbf')
SOURCE_SHA = 'a1fbac904a8604939ee55b0c91ca2812cc9b9451220a7a53df97cfd88acf97d5'
BASE, SIZE, MASK64 = 0x80200000, 24034304, (1 << 64) - 1
sys.path.insert(0, str(ROOT / 'linux-tests'))
from extract_linux_kernel_nbf import extract
from splice_linux_kernel_nbf import MEMORY_COMMANDS, parse_line, splice
sys.path.insert(0, str(ROOT / 'research/embedded46-20261120'))
import build_pair as memory_gate
from verify_pair import load_write_bound


def save(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2) + '\n')


def sections(path):
    raw = path.read_bytes()
    assert raw[:6] == b'\x7fELF\x02\x01'
    offset = struct.unpack_from('<Q', raw, 40)[0]
    size, count, string_index = struct.unpack_from('<HHH', raw, 58)
    rows = [struct.unpack_from('<IIQQQQIIQQ', raw, offset + n * size) for n in range(count)]
    string_section = rows[string_index]
    strings = raw[string_section[4]:string_section[4] + string_section[5]]
    return [dict(name=strings[r[0]:].split(b'\0', 1)[0].decode(), flags=r[2], address=r[3],
                 bytes=r[5], data=raw[r[4]:r[4] + r[5]]) for r in rows]


def scan_elf(path, label):
    nm = subprocess.check_output([build.PREFIX + 'nm', '-S', '-n', '--defined-only', path], text=True)
    (HERE / (label + '-symbols.log')).write_text(nm)
    functions = [(int(a, 16), int(s, 16), n) for a, s, n in
                 re.findall(r'^([0-9a-fA-F]+) ([0-9a-fA-F]+) [tT] (\S+)$', nm, re.M)]
    command = [build.PREFIX + 'objdump', '-d', path]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    pattern = re.compile(r'^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{4,8})\s+(.*)$')
    instructions, matches, pending = {}, [], None
    for line in process.stdout:
        match = pattern.match(line)
        if not match:
            continue
        address, encoded, asm = int(match[1], 16), match[2], match[3]
        word = int(encoded, 16)
        instructions[address] = len(encoded) // 2
        if pending is not None:
            pending['next_instruction'] = dict(address=hex(address), word=hex(word), asm=asm)
            pending = None
        if len(encoded) != 8 or word & 0x7f != 0x73 or not (word >> 12) & 7 or word >> 20 not in (0x5c1, 0x5c2):
            continue
        row = dict(address=hex(address), word=hex(word), asm=asm, csr=hex(word >> 20),
                   funct3=(word >> 12) & 7, rd=(word >> 7) & 31, rs1=(word >> 15) & 31,
                   functions=[name for start, length, name in functions if start <= address < start + length])
        matches.append(row)
        pending = row
    stderr = process.stderr.read()
    assert process.wait() == 0, stderr
    executable_potentials = []
    actual = {int(row['address'], 16) for row in matches}
    for section in sections(path):
        if not section['flags'] & 4:
            continue
        data = section['data']
        for offset in range(0, len(data) - 3, 2):
            if data[offset] & 0x7f != 0x73:
                continue
            word = struct.unpack_from('<I', data, offset)[0]
            if (word >> 12) & 7 and word >> 20 in (0x5c1, 0x5c2):
                address = section['address'] + offset
                classification = ('decoded CSR instruction' if address in actual else
                                  'inside preceding decoded 32-bit instruction' if instructions.get(address - 2) == 4 else
                                  'UNCLASSIFIED potential encoding')
                executable_potentials.append(dict(address=hex(address), word=hex(word),
                                                  section=section['name'], classification=classification))
                assert not classification.startswith('UNCLASSIFIED'), executable_potentials[-1]
    result = dict(elf=build.record(path), command=list(map(str, command)),
                  scope='decoded executable ELF sections and every-halfword executable-section potential encodings',
                  matches=matches, executable_potentials=executable_potentials)
    save(label + '-csr-review.json', result)
    return result


def nonkernel(path):
    digest, count = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for raw in stream:
            command, address, _ = parse_line(raw.decode('ascii'))
            width = MEMORY_COMMANDS.get(command)
            if width and address < BASE + SIZE and address + width > BASE:
                continue
            digest.update(raw)
            count += 1
    return dict(records=count, ordered_bytes_sha256=digest.hexdigest())


def main():
    if OUT.exists() or (HERE / 'package-manifest.json').exists():
        raise RuntimeError('refusing to overwrite new29 package')
    state = json.loads((HERE / 'build-manifest.json').read_text())
    assert state['state'] == 'build-complete'
    assert build.sha(SOURCE) == SOURCE_SHA
    linked = build.TREE / 'vmlinux'
    assert build.record(linked) == state['artifacts']['vmlinux']
    assert build.snapshot(build.CANONICAL) == state['canonical_before']
    assert build.snapshot(build.OLD) == state['accepted_tree_before']
    old_review = scan_elf(build.OLD / 'vmlinux', 'accepted27')
    assert not [row for row in old_review['matches'] if row['csr'] == '0x5c2']
    new_review = scan_elf(linked, 'new29')
    symbols = (HERE / 'new29-symbols.log').read_text()
    start = int(re.search(r'^([0-9a-fA-F]+) (?:[0-9a-fA-F]+ )?[tT] _start$', symbols, re.M)[1], 16)
    end = int(re.search(r'^([0-9a-fA-F]+) (?:[0-9a-fA-F]+ )?[bB] _end$', symbols, re.M)[1], 16)
    physical_end = BASE + end - start
    assert BASE < physical_end <= memory_gate.NEXT_ARG1
    assert physical_end <= memory_gate.BASE + memory_gate.OWNED_BYTES
    probes, controls = {}, {}
    for csr, prefix in (('0x5c1', 'bp_icache_retention'), ('0x5c2', 'bp_retained')):
        uses = [row for row in new_review['matches'] if row['csr'] == csr]
        reads = [row for row in uses if row['funct3'] == 2 and row['rs1'] == 0 and row['rd'] != 0
                 and prefix + '_probe' in row['functions']]
        writes = [row for row in uses if row['funct3'] == 1 and row['rd'] == 0 and row['rs1'] != 0
                  and any(name == '__do_sys_prctl' or name == prefix + '_control' for name in row['functions'])]
        assert len(uses) == 2 and len(reads) == len(writes) == 1, uses
        assert (writes[0]['next_instruction']['word'] == '0x100f') == (csr == '0x5c1')
        probes[csr], controls[csr] = reads[0], writes[0]
    extable = next(s for s in sections(linked) if s['name'] == '__ex_table')
    assert extable['bytes'] % 12 == 0
    exceptions = []
    for csr, probe in probes.items():
        pc, entries = int(probe['address'], 16), []
        for offset in range(0, extable['bytes'], 12):
            relative, fix, kind, registers = struct.unpack_from('<iiHH', extable['data'], offset)
            fault = (extable['address'] + offset + relative) & MASK64
            if fault == pc:
                target = (extable['address'] + offset + 4 + fix) & MASK64
                err, zero = registers & 31, (registers >> 5) & 31
                assert kind == 3 and target == pc + 4 and err and zero and err != zero
                assert zero == probe['rd'] and registers >> 10 == 0
                entries.append(dict(csr=csr, fault_pc=hex(pc), fixup_pc=hex(target), type=kind,
                                    error_register=err, zero_register=zero, encoded_data=hex(registers)))
        assert len(entries) == 1, csr
        exceptions += entries
    save('linked-exception-review.json', dict(entries=exceptions, table_bytes=extable['bytes'],
         scope='actual linked fault/fixup addresses, type3 and distinct nonzero registers for both optional probes'))
    OUT.mkdir()
    stripped, binary = OUT / 'vmlinux-stripped', OUT / 'vmlinux.bin'
    conversions = [[build.PREFIX + 'strip', '-o', stripped, linked],
                   [build.PREFIX + 'objcopy', '-O', 'binary', stripped, binary]]
    for command in conversions:
        subprocess.run(list(map(str, command)), check=True)
    assert binary.stat().st_size == SIZE, 'kernel window changed; re-audit packaging rather than padding silently'
    blob = (build.TREE / 'usr/initramfs_inc_data').read_bytes()
    image = binary.read_bytes()
    assert image.count(blob) == 1
    rootfs_offset = image.find(blob)
    assert build.sha(build.TREE / 'usr/initramfs_inc_data') == '0fbebeabd9fb4e152c0f79efe19f7275d08fd5956c97f0f022f829221735b5cf'
    plain = gzip.decompress(blob)
    assert plain == build.CPIO.read_bytes() and hashlib.sha256(plain).hexdigest() == state['rootfs']['sha256']
    old_binary = OLD_PACKAGE / 'vmlinux.bin'
    assert build.sha(old_binary) == '64f993713e1d7d5fcae57c26e42b32369d0bccfa0235635dd0b0010871f57435'
    candidate = OUT / 'linux-retained-control29-accepted-rootfs-mem46-shell.nbf'
    forward = splice(SOURCE, old_binary, binary, candidate, BASE)
    reverse = OUT / 'reverse-to-c7-mem46.nbf'
    backward = splice(candidate, binary, old_binary, reverse, BASE)
    assert reverse.read_bytes() == SOURCE.read_bytes()
    extracted = OUT / 'candidate-extracted.bin'
    extract(candidate, extracted, SIZE, BASE)
    assert extracted.read_bytes() == image
    preserved = nonkernel(SOURCE)
    assert nonkernel(candidate) == preserved
    original, _ = memory_gate.reconstruct(SOURCE)
    current, _ = memory_gate.reconstruct(candidate)
    assert original[:BASE - memory_gate.BASE] == current[:BASE - memory_gate.BASE]
    assert original[BASE - memory_gate.BASE + SIZE:] == current[BASE - memory_gate.BASE + SIZE:]
    _, trees = memory_gate.inventory(current)
    assert len(trees) == 1 and trees[0][0] == memory_gate.DTB_ADDRESS
    tree = trees[0][1]
    bootargs = next(p for p in tree['properties'] if p['node'] == '/chosen' and p['name'] == 'bootargs')
    assert bootargs['data'] == b'console=hvc0 loglevel=8 rdinit=/bin/sh mem=46M  \0'
    assert bootargs['bytes'] == 49 and tree['total'] == 1209
    rounded = (tree['total'] + 7) & ~7
    assert memory_gate.DTB_ADDRESS + rounded <= memory_gate.BASE + memory_gate.OWNED_BYTES
    assert memory_gate.NEXT_ARG1 + rounded <= memory_gate.BASE + memory_gate.OWNED_BYTES
    # Preserved firmware bytes must not acquire an unguarded optional CSR use.
    firmware = bytes(current[:BASE - memory_gate.BASE])
    firmware_encodings = []
    for offset in range(0, len(firmware) - 3, 2):
        if firmware[offset] & 0x7f != 0x73:
            continue
        word = struct.unpack_from('<I', firmware, offset)[0]
        if (word >> 12) & 7 and word >> 20 in (0x5c1, 0x5c2):
            firmware_encodings.append(dict(address=hex(memory_gate.BASE + offset), word=hex(word)))
    assert not firmware_encodings, firmware_encodings
    bounds = load_write_bound(candidate)
    result = dict(state='offline-linked-0029-bounded46-NBF-verified; target pending',
        build_manifest=build.record(HERE / 'build-manifest.json'), package_script=build.record(Path(__file__)),
        source_nbf=build.record(SOURCE), candidate=build.record(candidate),
        linked_elf=build.record(linked), stripped_elf=build.record(stripped), binary=build.record(binary),
        conversions=[list(map(str, command)) for command in conversions],
        extracted=build.record(extracted), exact_reverse=build.record(reverse), forward=forward, backward=backward,
        identical_nonkernel_records=preserved, accepted27_csr_scan=build.record(HERE / 'accepted27-csr-review.json'),
        new29_csr_scan=build.record(HERE / 'new29-csr-review.json'), linked_optional_probe_entries=exceptions,
        unchanged_firmware_halfword_scan=dict(base=hex(memory_gate.BASE), bytes=len(firmware),
             sha256=hashlib.sha256(firmware).hexdigest(), optional_csr_encodings=firmware_encodings,
             unwritten_bytes='nominal zero-fill; not an arbitrary stale-DRAM claim'),
        rootfs=dict(compressed=build.record(build.TREE / 'usr/initramfs_inc_data'),
             kernel_offset=hex(rootfs_offset), cpio_sha256=hashlib.sha256(plain).hexdigest(),
             cpio_bytes=len(plain), exact_accepted_compressed_and_uncompressed=True),
        bootargs=dict(bytes=bootargs['bytes'], data=bootargs['data'].rstrip(b'\0').decode()),
        load_bound=bounds, dtb_bounds=dict(source=hex(memory_gate.DTB_ADDRESS),
             runtime_destination=hex(memory_gate.NEXT_ARG1), declared_bytes=tree['total'], rounded_bytes=rounded,
             owned_end_exclusive=hex(memory_gate.BASE + memory_gate.OWNED_BYTES)),
        kernel_runtime_extent=dict(virtual_start=hex(start), virtual_end=hex(end),
             physical_start=hex(BASE), physical_end_exclusive=hex(physical_end),
             includes_linked_bss=True, fits_before_fdt_destination_and_owned_end=True),
        helpers=[build.record(ROOT / name) for name in ('linux-tests/splice_linux_kernel_nbf.py',
             'linux-tests/extract_linux_kernel_nbf.py', 'research/embedded46-20261120/build_pair.py',
             'research/embedded46-20261120/verify_pair.py')],
        expected_runtime=dict(allocation_bytes=48234496, memory_kib=47104,
             memory_notice='Memory limited to 46MB', dma32_last_byte='0x82dfffff', next_arg1='0x82200000'),
        limits=['New kernel/image baseline; no target boot, absent/present capability or performance acceptance',
             '0028 omitted; historical mode14 includes early wake and scheduler selection sites',
             'Old prefix-table bytes preserved, usefulness for relocated new kernel unproven',
             'Busy is a UCE/client/backend snapshot, not global lower-memory drain',
             'Physical eligibility requires independent complete runtime/probe/integrity gate'])
    save('package-manifest.json', result)
    (OUT / 'package-manifest.json').write_text((HERE / 'package-manifest.json').read_text())
    print('PACKAGE_PASS ' + str(candidate), flush=True)
    print('NBF_SHA256=' + build.sha(candidate), flush=True)


if __name__ == '__main__':
    main()
