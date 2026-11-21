#!/usr/bin/env python3
"""Limit the verified embedded pair through existing FDT bootargs padding.

No kernel, rootfs, memory node or host runner is changed. The memory bound
is a Linux boot policy; FPGA enforcement and the SIG11 cause remain unproved.
"""
import hashlib
import importlib.util
from itertools import zip_longest
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARTIFACTS = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120')
OUT = ARTIFACTS / 'embedded46-workloads'
EMBEDDED = ROOT / 'research/embedded-workloads-20261120'
EMBEDDED_MANIFEST_SHA = 'a043486bb4e43823dad9415499ed0132f6ecc6758a01f2139cc53a0cad7208ac'
HELPER = ROOT / 'codex-skills/bp-fpga-synthesis/scripts/make_linux_shell_nbf.py'
KERNEL = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/build/linux-6.6')
OPENSBI = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/opensbi')
BASE, RAM_BYTES, OWNED_BYTES = 0x80000000, 64 * 1024 * 1024, 46 * 1024 * 1024
DTB_ADDRESS, NEXT_ARG1 = 0x80016000, 0x82200000
PAYLOAD_BASE, PAYLOAD_BYTES = 0x80200000, 24034304
FDT_MAGIC = b'\xd0\x0d\xfe\xed'
sys.path.insert(0, str(ROOT / 'linux-tests'))
from splice_linux_kernel_nbf import MEMORY_COMMANDS, parse_line


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path):
    return dict(path=str(path.resolve()), sha256=sha(path), bytes=path.stat().st_size)


def reconstruct(path):
    """Replay ordered DRAM writes at their actual NBF widths, including overrides."""
    image = bytearray(RAM_BYTES)
    high = BASE
    with path.open() as source:
        for line in source:
            command, address, data = parse_line(line)
            width = MEMORY_COMMANDS.get(command)
            if not width or address < BASE:
                continue
            if address + width > BASE + RAM_BYTES:
                raise ValueError('NBF DRAM write exceeds the advertised memory window')
            image[address - BASE:address - BASE + width] = data.to_bytes(width, 'little')
            high = max(high, address + width)
    return image, high


def parse_fdt(blob):
    """Strict FDT v17 header, reserve-map, token and property-bounds parser."""
    if len(blob) < 40:
        raise ValueError('truncated FDT header')
    magic, total, structure, strings, reserve, version, compatible, cpu, string_size, struct_size = struct.unpack_from('>10I', blob)
    if (magic != 0xd00dfeed or version != 17 or compatible > 17 or not 40 <= total <= len(blob)
            or structure % 4 or reserve % 8 or structure < 40 or strings < 40 or reserve < 40
            or structure + struct_size > total or strings + string_size > total
            or not (structure + struct_size <= strings or strings + string_size <= structure)):
        raise ValueError('invalid FDT header/ranges')
    reservations, cursor = [], reserve
    while True:
        if cursor + 16 > total:
            raise ValueError('unterminated FDT reserve map')
        address, size = struct.unpack_from('>QQ', blob, cursor)
        cursor += 16
        if not address and not size:
            break
        reservations.append(dict(address=hex(address), bytes=size))
    if not (cursor <= structure or reserve >= structure + struct_size):
        raise ValueError('reserve map overlaps structure')
    if not (cursor <= strings or reserve >= strings + string_size):
        raise ValueError('reserve map overlaps strings')
    properties, nodes, stack = [], [], []
    offset, end, finished = structure, structure + struct_size, False
    while offset < end:
        token = struct.unpack_from('>I', blob, offset)[0]
        offset += 4
        if token == 1:
            zero = blob.find(b'\0', offset, end)
            if zero < 0:
                raise ValueError('unterminated FDT node')
            name = blob[offset:zero].decode('ascii')
            if '/' in name or (not stack and (name or nodes)):
                raise ValueError('invalid FDT root/node name')
            stack.append(name)
            path = '/' + '/'.join(stack[1:])
            if path in nodes:
                raise ValueError('duplicate FDT node')
            nodes.append(path)
            offset = (zero + 4) & ~3
        elif token == 2:
            if not stack:
                raise ValueError('unbalanced FDT end node')
            stack.pop()
        elif token == 3:
            if not stack or offset + 8 > end:
                raise ValueError('invalid FDT property placement')
            size, name_offset = struct.unpack_from('>II', blob, offset)
            offset += 8
            if name_offset >= string_size or offset + size > end:
                raise ValueError('FDT property exceeds its block')
            zero = blob.find(b'\0', strings + name_offset, strings + string_size)
            if zero < 0:
                raise ValueError('unterminated FDT property name')
            name = blob[strings + name_offset:zero].decode('ascii')
            path = '/' + '/'.join(stack[1:])
            if any(p['node'] == path and p['name'] == name for p in properties):
                raise ValueError('duplicate FDT property')
            properties.append(dict(node=path, name=name, offset=offset, bytes=size, data=blob[offset:offset + size]))
            offset = (offset + size + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            if stack or not nodes:
                raise ValueError('FDT ends with unclosed nodes')
            if any(blob[offset:end]):
                raise ValueError('nonzero data follows FDT end token')
            finished = True
            break
        else:
            raise ValueError('unknown FDT token')
        if offset > end:
            raise ValueError('FDT alignment exceeds structure block')
    if not finished:
        raise ValueError('missing FDT end token')
    return dict(total=total, structure=structure, strings=strings, reserve=reserve,
                version=version, boot_cpu=cpu, reservations=reservations, nodes=nodes, properties=properties)


def inventory(image):
    candidates, valid, offset = [], [], 0
    while True:
        offset = image.find(FDT_MAGIC, offset)
        if offset < 0:
            break
        try:
            tree = parse_fdt(bytes(image[offset:]))
        except (ValueError, struct.error, UnicodeError) as error:
            candidates.append(dict(address=hex(BASE + offset), valid=False, reason=str(error)))
        else:
            candidates.append(dict(address=hex(BASE + offset), valid=True, bytes=tree['total']))
            valid.append((BASE + offset, tree))
        offset += 1
    return candidates, valid


def bootarg_edit(tree):
    matches = [p for p in tree['properties'] if p['node'] in ('/chosen', '/chosen@0') and p['name'] == 'bootargs']
    if len(matches) != 1:
        raise ValueError('expected one chosen bootargs property')
    prop = matches[0]
    data = prop['data']
    if not data.endswith(b'\0') or b'\0' in data[:-1]:
        raise ValueError('bootargs must have one final NUL')
    old = data[:-1]
    prefix = b'console=hvc0 loglevel=8 rdinit=/bin/sh'
    if old != prefix + b' ' * 10:
        raise ValueError('bootargs differ from the exact reviewed padded shell command')
    capped = prefix + b' mem=46M'
    new = capped + b' ' * (len(old) - len(capped))
    if len(new) != len(old) or len(capped) > len(old):
        raise ValueError('mem=46M does not fit existing property padding')
    return prop, old, new


def source_proofs():
    paths = [KERNEL / name for name in ('arch/riscv/mm/init.c', 'arch/riscv/kernel/setup.c',
                                      'mm/memblock.c', 'lib/cmdline.c')]
    paths += [OPENSBI / name for name in ('firmware/fw_base.S', 'firmware/fw_payload.S',
                                         'platform/generic/blackparrot/objects.mk')]
    proofs = []
    for index, source in enumerate(paths):
        target = OUT / 'source-proof' / (str(index) + '-' + source.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        proofs.append(dict(source=record(source), snapshot=record(target)))
    init = paths[0].read_text()
    for expression in ('early_param("mem", early_mem)', 'size = memparse(p, &p) & PAGE_MASK;',
                       'memory_limit = min_t(u64, size, memory_limit);',
                       'memblock_enforce_memory_limit(memory_limit);',
                       'end = __pa(PAGE_OFFSET) + memory_limit;'):
        if expression not in init:
            raise ValueError('Linux memory-limit source contract differs')
    setup = paths[1].read_text()
    if setup.index('parse_early_param();') > setup.index('paging_init();'):
        raise ValueError('early memory argument is parsed after paging initialization')
    memblock = paths[2].read_text()
    if ('max_addr = __find_max_addr(limit);' not in memblock
            or 'memblock_remove_range(&memblock.memory, max_addr,' not in memblock):
        raise ValueError('memblock memory-cap enforcement differs')
    if 'FW_PAYLOAD_FDT_ADDR=0x82200000' not in paths[-1].read_text():
        raise ValueError('OpenSBI FDT destination differs from accepted boot evidence')
    if 'lla\ta1, fw_fdt_bin' not in paths[-3].read_text() or '_fdt_reloc_again:' not in paths[-3].read_text():
        raise ValueError('OpenSBI embedded-FDT relocation source differs')
    return proofs


def main():
    if OUT.exists() or (HERE / 'manifest.json').exists():
        raise SystemExit('refusing to overwrite embedded46 evidence')
    source_manifest = EMBEDDED / 'manifest.json'
    if sha(source_manifest) != EMBEDDED_MANIFEST_SHA:
        raise SystemExit('verified embedded source pair manifest differs')
    embedded = json.loads(source_manifest.read_text())
    accepted_log = ARTIFACTS / 'session1/0-scan32-futex-early.log'
    boot_text = accepted_log.read_text().replace('\r', '')
    if 'Domain0 Next Arg1         : 0x0000000082200000' not in boot_text:
        raise SystemExit('accepted boot evidence does not bind runtime FDT argument')
    OUT.mkdir()
    proofs = source_proofs()
    arms, inventories, old_memory, new_memory = {}, {}, {}, {}
    for label in ('baseline', 'control'):
        source = Path(embedded['arms'][label]['nbf']['path'])
        if sha(source) != embedded['arms'][label]['nbf']['sha256']:
            raise RuntimeError('embedded source NBF changed')
        before, highest = reconstruct(source)
        candidates, trees = inventory(before)
        if len(trees) != 1 or trees[0][0] != DTB_ADDRESS:
            raise RuntimeError('loaded DTB inventory differs from unique firmware source')
        address, tree = trees[0]
        prop, old, new = bootarg_edit(tree)
        root_props = {p['name']: p['data'] for p in tree['properties'] if p['node'] == '/'}
        if struct.unpack('>I', root_props['#address-cells'])[0] != 2 or struct.unpack('>I', root_props['#size-cells'])[0] != 2:
            raise RuntimeError('unexpected root address/size cell geometry')
        memories = [p for p in tree['properties'] if p['name'] == 'reg'
                    and any(t['node'] == p['node'] and t['name'] == 'device_type' and t['data'] == b'memory\0'
                            for t in tree['properties'])]
        if len(memories) != 1 or struct.unpack('>QQ', memories[0]['data']) != (BASE, RAM_BYTES):
            raise RuntimeError('advertised single 64MiB memory bank differs')
        target = OUT / ('linux-prefix32-embedded46-' + label + '-shell.nbf')
        command = [sys.executable, str(HELPER), str(source), str(target), '--old', old.decode('ascii'), '--new', new.decode('ascii')]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (OUT / (label + '-helper.log')).write_text(result.stdout + result.stderr)
        expected_address = address + prop['offset']
        if result.returncode or f'bootargs address: 0x{expected_address:x}' not in result.stdout:
            raise RuntimeError('maintained shell-NBF helper did not patch the parsed property')
        after, _ = reconstruct(target)
        differences = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        expected = [address - BASE + prop['offset'] + i for i, (a, b) in enumerate(zip(old, new)) if a != b]
        if differences != expected:
            raise RuntimeError('nominal memory changes outside expected bootarg data')
        parsed_after = parse_fdt(bytes(after[address - BASE:]))
        new_prop, _new_old, _new_new = prop, old, new
        observed = [p for p in parsed_after['properties'] if p['node'] == prop['node'] and p['name'] == 'bootargs'][0]
        if observed['data'] != new + b'\0' or tree['total'] != parsed_after['total']:
            raise RuntimeError('FDT size or property contract changed')
        start, end = address - BASE, address - BASE + tree['total']
        if before[:start] != after[:start] or before[end:] != after[end:]:
            raise RuntimeError('bytes outside FDT changed')
        pstart = PAYLOAD_BASE - BASE
        payload = bytes(after[pstart:pstart + PAYLOAD_BYTES])
        if hashlib.sha256(payload).hexdigest() != embedded['arms'][label]['payload']['sha256']:
            raise RuntimeError('Linux kernel/rootfs payload changed')
        source_lines, target_lines = source.read_bytes().splitlines(keepends=True), target.read_bytes().splitlines(keepends=True)
        helper_module = load_helper()
        unfreeze = [i for i, line in enumerate(source_lines) if line.strip().decode() == helper_module.UNFREEZE]
        insert = unfreeze[-1]
        count = len(target_lines) - len(source_lines)
        if count <= 0 or target_lines[:insert] != source_lines[:insert] or target_lines[insert + count:] != source_lines[insert:]:
            raise RuntimeError('helper modified original NBF lines')
        block = target_lines[insert:insert + count]
        for raw in block:
            c, a, _ = parse_line(raw.decode())
            if c != 3 or a % 8 or not (address <= a and a + 8 <= address + tree['total']):
                raise RuntimeError('inserted record is not an aligned write inside this FDT')
        reverse = OUT / (label + '-reverse.nbf')
        reverse.write_bytes(b''.join(target_lines[:insert] + target_lines[insert + count:]))
        if reverse.read_bytes() != source.read_bytes():
            raise RuntimeError('removing exact appended patch does not reverse byte-exactly')
        restored = bytearray(after)
        restored[address - BASE + prop['offset']:address - BASE + prop['offset'] + len(old)] = old
        if restored != before:
            raise RuntimeError('bootarg byte reversal does not reconstruct nominal source memory')
        dtb_old, dtb_new = OUT / (label + '-original.dtb'), OUT / (label + '-mem46.dtb')
        dtb_old.write_bytes(before[start:end])
        dtb_new.write_bytes(after[start:end])
        inventories[label] = candidates
        old_memory[label], new_memory[label] = before, after
        arms[label] = dict(source_nbf=record(source), nbf=record(target), reverse=record(reverse),
                           original_dtb=record(dtb_old), capped_dtb=record(dtb_new),
                           helper_command=command, helper_log=record(OUT / (label + '-helper.log')),
                           inserted_records=[line.decode().rstrip() for line in block], insertion_line=insert + 1,
                           changed_physical_bytes=[hex(BASE + i) for i in differences],
                           outside_fdt_unchanged=True, all_original_nbf_records_unchanged=True,
                           kernel_payload_sha256=hashlib.sha256(payload).hexdigest(),
                           highest_loaded_dram_end=hex(highest),
                           bootargs_property=dict(node=prop['node'], offset=prop['offset'], bytes=prop['bytes'],
                                                  physical=hex(expected_address), original=old.decode(), capped=new.decode()),
                           fdt_total_size=tree['total'], unchanged_memory_reg=memories[0]['data'].hex(),
                           unchanged_reservations=tree['reservations'])
    a, b = [Path(arms[label]['nbf']['path']).open('rb') for label in ('baseline', 'control')]
    with a, b:
        pair = [dict(line=i, original=x.decode() if x else None, control=y.decode() if y else None)
                for i, (x, y) in enumerate(zip_longest(a, b), 1) if x != y]
    expected_record = dict(line=1075385, original='03_0000000080a13fe8_1073e0f77de3471d\n',
                           control='03_0000000080a13fe8_1073e0f77de34721\n')
    if pair != [expected_record]:
        raise RuntimeError('capped pair differs beyond mode14 instruction record')
    diffs = [i for i, (a, b) in enumerate(zip(new_memory['baseline'], new_memory['control'])) if a != b]
    if diffs != [0xa13fe8]:
        raise RuntimeError('capped nominal memory pair differs beyond one instruction byte')
    modes = Path(embedded['all_modes']['path'])
    if sha(modes) != embedded['all_modes']['sha256']:
        raise RuntimeError('reviewed mode14 semantics proof changed')
    for label in arms:
        if sha(Path(arms[label]['source_nbf']['path'])) != embedded['arms'][label]['nbf']['sha256']:
            raise RuntimeError('source image changed')
    manifest = dict(state='embedded46-pair-offline-verified', image_pair='embedded46',
                    scope='FDT bootarg allocation bound only; no board/kernel build or SIG11 causality claim',
                    source_embedded_manifest=record(source_manifest), helper=record(HELPER),
                    accepted_boot_evidence=record(accepted_log), dtb_inventory=inventories,
                    active_fdt=dict(embedded_physical=hex(DTB_ADDRESS), firmware_offset='0x16000',
                                    runtime_next_arg1=hex(NEXT_ARG1),
                                    relationship='Only NBF-loaded DTB is firmware source; unchanged OpenSBI copies its totalsize bytes to next_arg1 before Linux.'),
                    source_proof=proofs, arms=arms,
                    source_nbf=arms['baseline']['nbf'], candidate_nbf=arms['control']['nbf'],
                    changed_modes=[14], all_modes=record(modes), sole_nbf_difference=pair[0],
                    reverse_nbf_byte_exact=True, source_inputs_unchanged=True,
                    rootfs_cpio_sha256=embedded['embedded_cpio']['sha256'],
                    expected_bound=dict(mem_arg='mem=46M', bytes=OWNED_BYTES, base=hex(BASE),
                                        ram_end_exclusive=hex(BASE + OWNED_BYTES), expected_dma32_end=hex(BASE + OWNED_BYTES - 1),
                                        maximum_normal_ram_offset=hex(OWNED_BYTES - 1),
                                        runtime_gate='Require Linux Memory limited to46MB and DMA32 ending82dfffff before workload acceptance.'),
                    limits=['Memory node remains64MiB; Linux early parameter enforces46MiB ordinary RAM.',
                            'No observed SIG11 cause has been established by this offline change.',
                            'Old uncapped original/embedded results cannot be pooled with embedded46.'], driver=record(Path(__file__)))
    rendered = json.dumps(manifest, indent=2) + '\n'
    (HERE / 'manifest.json').write_text(rendered)
    (OUT / 'manifest.json').write_text(rendered)
    print('EMBEDDED46_OFFLINE_PASS')
    for label in arms:
        print(label.upper() + '_NBF_SHA256=' + arms[label]['nbf']['sha256'])


def load_helper():
    spec = importlib.util.spec_from_file_location('maintained_shell_nbf', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == '__main__':
    main()
