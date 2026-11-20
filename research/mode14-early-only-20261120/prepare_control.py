#!/usr/bin/env python3
"""Prepare an exact-old-image mode-14 causal control without board access.

Only the scheduler bound instruction changes. This is separate from rebuilding
the newer retention-ABI source stack with patch 0028.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'linux-tests'))
from extract_linux_kernel_nbf import extract
from patch_nbf_memory_records import patch

ARTIFACT_ROOT = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120')
OUT = ARTIFACT_ROOT / 'mode14-early-only-control'
SOURCE = ARTIFACT_ROOT / 'linux-prefix32-futex-usersyscall-shell.nbf'
OLD_ELF = ARTIFACT_ROOT / 'kernel27/oldstripped.elf'
SOURCE_SHA = 'ef50be197b458b512f82ed8a9deccc0bdfcfadba760ccd119d67e46837501cf4'
ELF_SHA = '0792746ba2caf6b2370d923319187f62243c8a0262c876c19a18e2946257d4a3'
PAYLOAD_SHA = 'bf0318e848701a99a58a27436861f88d43340245071c036788488e58dcf7be6d'
PREFIX = '/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux-'
PAYLOAD_SIZE = 24034304
OFFSET = 0x813fe8
VMA = 0xffffffff80813fe8
PHYSICAL = 0x80a13fe8


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path):
    return dict(path=str(path.resolve()), sha256=sha(path), bytes=path.stat().st_size)


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def compressed_immediate(word, rd, kind):
    if word & 0xe003 != kind or (word >> 7) & 31 != rd:
        raise ValueError('unexpected compressed instruction/register')
    return signed(((word >> 2) & 31) | (((word >> 12) & 1) << 5), 6)


def branch(word, pc, kind, rs1, rs2, target):
    immediate = (((word >> 31) & 1) << 12) | (((word >> 7) & 1) << 11)
    immediate |= (((word >> 25) & 63) << 5) | (((word >> 8) & 15) << 1)
    if (word & 127 != 0x63 or (word >> 12) & 7 != kind
            or (word >> 15) & 31 != rs1 or (word >> 20) & 31 != rs2
            or pc + signed(immediate, 13) != target):
        raise ValueError('unexpected scheduler branch')


def selected_mode_triggers(payload):
    """Decode the exact old branch/constant skeleton, then evaluate all bytes."""
    def word(offset):
        return struct.unpack_from('<I', payload, offset)[0]

    def half(offset):
        return struct.unpack_from('<H', payload, offset)[0]

    branch(word(0x813e00), 0x813e00, 1, 14, 0, 0x813fd8)
    low_bound = compressed_immediate(half(0x813fd8), 14, 0x4001)
    branch(word(0x813fda), 0x813fda, 0, 15, 14, 0x814210)
    branch(word(0x813fde), 0x813fde, 7, 14, 15, 0x8141f4)
    subtract = compressed_immediate(half(0x813fe2), 15, 0x2001)
    if word(0x813fe4) != 0x0ff7f793:  # andi a5,a5,255
        raise ValueError('unexpected mode truncation')
    high_bound = compressed_immediate(half(OFFSET), 14, 0x4001)
    branch(word(0x813fea), 0x813fea, 7, 14, 15, 0x813e04)
    branch(word(0x8141f6), 0x8141f6, 0, 15, 14, 0x813e04)
    excluded_low = compressed_immediate(half(0x8141f4), 14, 0x4001)
    if word(0x813fee) != 0x5c001073 or word(0x8141fa) != 0x5c001073:
        raise ValueError('scheduler trigger instruction changed')
    if word(0x813e04) != 0x0709b703:  # ld a4,112(s3), kills bound value
        raise ValueError('a4 is not overwritten at the common join')
    if (low_bound, subtract, excluded_low) != (4, -6, 1):
        raise ValueError('unexpected scheduler predicate constants')
    return [bool(mode and mode != low_bound
                 and ((mode != excluded_low) if mode <= low_bound
                      else ((mode + subtract) & 255) > high_bound))
            for mode in range(256)]


def elf_offset(elf, address):
    """Bind a VMA to an actual executable ELF64 section before patching."""
    if elf[:6] != b'\x7fELF\x02\x01':
        raise ValueError('expected little-endian ELF64')
    table = struct.unpack_from('<Q', elf, 40)[0]
    stride, count = struct.unpack_from('<HH', elf, 58)
    matches = []
    for index in range(count):
        section = struct.unpack_from('<IIQQQQIIQQ', elf, table + index * stride)
        _name, kind, flags, base, offset, size = section[:6]
        if kind == 1 and flags & 4 and base <= address and address + 2 <= base + size:
            matches.append(offset + address - base)
    if len(matches) != 1:
        raise ValueError('instruction is not in exactly one executable section')
    return matches[0]


def change_instruction(data, offset):
    if data[offset:offset + 2] != b'\x1d\x47':
        raise ValueError('expected exact old li a4,7 bytes')
    result = bytearray(data)
    result[offset:offset + 2] = b'\x21\x47'
    differences = [index for index, (old, new) in enumerate(zip(data, result)) if old != new]
    if len(data) != len(result) or differences != [offset]:
        raise ValueError('whole-file difference is not exactly the reviewed byte')
    return bytes(result)


def main():
    if OUT.exists() or (HERE / 'manifest.json').exists():
        raise SystemExit('refusing to overwrite causal-control evidence')
    if sha(SOURCE) != SOURCE_SHA or sha(OLD_ELF) != ELF_SHA:
        raise SystemExit('accepted old image/ELF identity mismatch')
    OUT.mkdir()
    old_binary = OUT / 'old-reconstructed.bin'
    conversion = [PREFIX + 'objcopy', '-O', 'binary', str(OLD_ELF), str(old_binary)]
    subprocess.run(conversion, check=True)
    if sha(old_binary) != PAYLOAD_SHA or old_binary.stat().st_size != PAYLOAD_SIZE:
        raise RuntimeError('old ELF is not byte-bound to accepted payload')
    old = old_binary.read_bytes()
    new = change_instruction(old, OFFSET)
    binary = OUT / 'mode14-early-only.bin'
    binary.write_bytes(new)
    old_elf_bytes = OLD_ELF.read_bytes()
    file_offset = elf_offset(old_elf_bytes, VMA)
    elf = OUT / 'mode14-early-only.elf'
    elf.write_bytes(change_instruction(old_elf_bytes, file_offset))
    converted = OUT / 'control-from-elf.bin'
    new_conversion = [PREFIX + 'objcopy', '-O', 'binary', str(elf), str(converted)]
    subprocess.run(new_conversion, check=True)
    if converted.read_bytes() != new:
        raise RuntimeError('modified ELF conversion differs from exact one-byte control')
    before, after = selected_mode_triggers(old), selected_mode_triggers(new)
    old_modes = [mode for mode in range(256) if before[mode]]
    new_modes = [mode for mode in range(256) if after[mode]]
    if old_modes != [2, 3, 5] + list(range(14, 256)):
        raise RuntimeError('decoded old predicate differs from independently expected modes')
    if new_modes != [2, 3, 5] + list(range(15, 256)):
        raise RuntimeError('control changes another mode')
    proof = [dict(mode=mode, original_trigger=before[mode], control_trigger=after[mode])
             for mode in range(256)]
    proof_path = OUT / 'all-256-mode-proof.json'
    proof_path.write_text(json.dumps(proof, indent=2) + '\n')
    alternatives = []
    for index in range(143):
        entry = 0xf45438 + 16 * index
        relative, _alt, _vendor, length, _patch = struct.unpack_from('<iiHHI', old, entry)
        target = entry + relative
        if target < OFFSET + 2 and target + length > OFFSET:
            alternatives.append(index)
    if alternatives:
        raise RuntimeError('runtime alternatives overlap the patched instruction')
    word_offset = OFFSET & ~7
    old_word = int.from_bytes(old[word_offset:word_offset + 8], 'little')
    new_word = int.from_bytes(new[word_offset:word_offset + 8], 'little')
    source_bytes = SOURCE.read_bytes()
    lines = source_bytes.decode('ascii').splitlines()
    address = 0x80200000 + word_offset
    patched_lines = patch(lines, [(address, old_word, new_word)])
    candidate = OUT / 'linux-prefix32-mode14-early-only-shell.nbf'
    candidate.write_text('\n'.join(patched_lines) + '\n', encoding='ascii')
    reverse = '\n'.join(patch(patched_lines, [(address, new_word, old_word)])) + '\n'
    if reverse.encode('ascii') != source_bytes:
        raise RuntimeError('reverse record patch is not byte-exact original NBF')
    reversed_nbf = OUT / 'reverse-to-ef50.nbf'
    reversed_nbf.write_text(reverse, encoding='ascii')
    changed_lines = [i for i, pair in enumerate(zip(lines, patched_lines)) if pair[0] != pair[1]]
    if len(changed_lines) != 1 or len(patched_lines) != len(lines):
        raise RuntimeError('NBF changed outside its single instruction-bearing record')
    extracted = OUT / 'control-extracted.bin'
    extract(candidate, extracted, PAYLOAD_SIZE)
    if extracted.read_bytes() != new:
        raise RuntimeError('candidate does not reconstruct the exact one-byte payload')
    blob = ARTIFACT_ROOT / 'kernel27/accepted-rootfs.cpio.gz'
    gzip_bytes = blob.read_bytes()
    if (old[0xc126b0:0xc126b0 + len(gzip_bytes)] != gzip_bytes
            or new[0xc126b0:0xc126b0 + len(gzip_bytes)] != gzip_bytes):
        raise RuntimeError('accepted rootfs blob changed')
    disassemblies = []
    for name, image in (('original', OLD_ELF), ('control', elf)):
        for label, start, end in (('predicate', 0xffffffff80813fd8, 0xffffffff80814000),
                                  ('join', 0xffffffff80813df2, 0xffffffff80813e1a)):
            command = [PREFIX + 'objdump', '-d', '--start-address=' + hex(start),
                       '--stop-address=' + hex(end), str(image)]
            path = OUT / (name + '-' + label + '.disassembly.txt')
            path.write_text(subprocess.check_output(command, text=True))
            disassemblies.append(dict(command=command, artifact=record(path)))
    if sha(SOURCE) != SOURCE_SHA or sha(OLD_ELF) != ELF_SHA:
        raise RuntimeError('accepted inputs changed')
    line = changed_lines[0]
    result = dict(
        state='offline-causal-control-verified', scope='no board execution or performance acceptance',
        source_nbf=record(SOURCE), original_elf=record(OLD_ELF), original_payload=record(old_binary),
        candidate_nbf=record(candidate), reverse_nbf=record(reversed_nbf),
        control_elf=record(elf), control_payload=record(binary),
        converted_control_payload=record(converted), reextracted_payload=record(extracted),
        conversion_commands=[conversion, new_conversion],
        instruction=dict(vma=hex(VMA), physical=hex(PHYSICAL), payload_offset=hex(OFFSET),
                         elf_offset=hex(file_offset), old_halfword='0x471d', new_halfword='0x4721',
                         old_byte='0x1d', new_byte='0x21', binary_changed_bytes=1, elf_changed_bytes=1,
                         meaning='li a4,7 -> li a4,8; excludes mode14 from the late selection trigger'),
        nbf_changed_record=dict(line=line + 1, original=lines[line], control=patched_lines[line]),
    )
    result.update(
        all_modes=record(proof_path), changed_modes=[14], alternatives_checked=143,
        alternatives_overlaps=alternatives, disassemblies=disassemblies,
        a4_lifetime='Both paths join at 0xffffffff80813e04, which overwrites a4 with ld a4,112(s3) before any use.',
        reverse_nbf_byte_exact=True, accepted_rootfs_gzip=record(blob),
        rootfs_offset='0xc126b0', original_inputs_unchanged=True,
        source_patch=record(ROOT / 'linux-tests/kernel-patches/0028-blackparrot-mode14-early-only.patch'),
        source_patch_scope='Separate newer source stack: 0026 -> 0027 -> 0028; control NBF retains the old ABI without 0027.',
        driver=record(Path(__file__)),
        interpretation='Historical mode14 effects measure early-entry plus scheduler-selection replay. This image removes only the latter; complete-execution comparison remains required.')
    rendered = json.dumps(result, indent=2) + '\n'
    (HERE / 'manifest.json').write_text(rendered)
    (OUT / 'manifest.json').write_text(rendered)
    print('OFFLINE_CONTROL_PASS ' + str(candidate))
    print('CANDIDATE_SHA256=' + sha(candidate))


if __name__ == '__main__':
    main()
