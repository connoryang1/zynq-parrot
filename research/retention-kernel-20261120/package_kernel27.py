#!/usr/bin/env python3
"""Verify and splice the linked retention kernel without contacting a board.

The accepted NBF supplies preserved firmware/collateral. The linked ELF and
embedded rootfs are independently checked before reversible payload replacement.
"""
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'linux-tests'))
from extract_linux_kernel_nbf import extract
from splice_linux_kernel_nbf import MEMORY_COMMANDS, parse_line, splice

OUT = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/kernel27')
SOURCE = OUT.parent / 'linux-prefix32-futex-usersyscall-shell.nbf'
EXPECTED_SOURCE = 'ef50be197b458b512f82ed8a9deccc0bdfcfadba760ccd119d67e46837501cf4'
PREFIX = '/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux-'
BASE = 0x80200000
SIZE = 24034304


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path):
    return {'path': str(path.resolve()), 'sha256': sha(path), 'bytes': path.stat().st_size}


def nonkernel_digest(path):
    digest, count = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for raw in stream:
            command, address, data = parse_line(raw.decode('ascii'))
            width = MEMORY_COMMANDS.get(command)
            if width and address < BASE + SIZE and address + width > BASE:
                continue
            digest.update(raw)
            count += 1
    return {'records': count, 'ordered_bytes_sha256': digest.hexdigest()}


def csr_gate(elf):
    # nm's typed/size-qualified functions avoid attributing an instruction to
    # an unrelated nearest local label. Objdump decodes compressed alignment.
    symbols = subprocess.check_output([PREFIX + 'nm', '-S', '-n', '--defined-only', str(elf)], text=True)
    (HERE / 'linked-symbols.txt').write_text(symbols)
    functions = []
    for address, size, kind, name in re.findall(r'^([0-9a-fA-F]+) ([0-9a-fA-F]+) ([tT]) (\S+)$', symbols, re.M):
        if int(size, 16):
            functions.append((int(address, 16), int(size, 16), name))
    instruction = re.compile(r'^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{4,8})\s+(.*)$')
    command = [PREFIX + 'objdump', '-d', str(elf)]
    process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    matches, pending = [], None
    for line in process.stdout:
        match = instruction.match(line)
        if not match:
            continue
        address, word, asm = int(match[1], 16), int(match[2], 16), match[3]
        if pending is not None:
            pending['next_instruction'] = {'address': hex(address), 'word': hex(word), 'asm': asm}
            pending = None
        if len(match[2]) != 8 or word & 0x7f != 0x73 or not (word >> 12) & 7 or word >> 20 != 0x5c1:
            continue
        owners = [name for start, size, name in functions if start <= address < start + size]
        row = {'address': hex(address), 'word': hex(word), 'asm': asm, 'functions': owners,
               'funct3': (word >> 12) & 7, 'rd': (word >> 7) & 31, 'rs1': (word >> 15) & 31}
        matches.append(row)
        pending = row
    stderr = process.stderr.read()
    if process.wait():
        raise RuntimeError('linked ELF disassembly failed: ' + stderr)
    result = {'command': command, 'scope': 'all executable ELF sections; includes 2-byte instruction alignment',
              'matches': matches}
    (HERE / 'linked-csr5c1.json').write_text(json.dumps(result, indent=2) + '\n')
    if len(matches) != 2:
        raise RuntimeError('expected exactly two executable CSR 0x5c1 uses')
    reads = [row for row in matches if row['word'] == '0x5c102773'
             and 'bp_icache_retention_probe' in row['functions']]
    writes = [row for row in matches if row['word'] == '0x5c199073'
              and '__do_sys_prctl' in row['functions']]
    if len(reads) != 1 or len(writes) != 1 or writes[0].get('next_instruction', {}).get('word') != '0x100f':
        raise RuntimeError('linked CSR uses differ from the reviewed probe/control with following fence.i')
    return result


def main():
    generated = [OUT / name for name in ('old-kernel-from-ef50.bin', 'linux-prefix32-retention27-shell.nbf',
                                        'reverse-to-ef50.nbf', 'new-kernel-extracted.bin', 'package-manifest.json')]
    if any(path.exists() for path in generated):
        raise SystemExit('refusing to overwrite package evidence')
    state = json.loads((HERE / 'manifest.json').read_text())
    if state['state'] != 'link-complete' or state['link']['exit_code'] != 0:
        raise SystemExit('linked kernel gate is not complete')
    if state['canonical_before'] != state['canonical_after']:
        raise SystemExit('canonical SDK hash drift')
    linked = HERE / 'link-vmlinux'
    stripped, binary = OUT / 'vmlinux-stripped', OUT / 'vmlinux.bin'
    if sha(linked) != state['link']['artifacts']['vmlinux']['sha256'] or binary.stat().st_size != SIZE:
        raise SystemExit('linked ELF identity or payload size mismatch')
    if sha(SOURCE) != EXPECTED_SOURCE:
        raise SystemExit('source NBF is not exact accepted ef50 image')
    if sha(HERE / 'input-.config') != state['canonical_before']['.config']:
        raise SystemExit('archived configuration mismatch')
    rootfs = gzip.decompress((HERE / 'link-usr_initramfs_inc_data').read_bytes())
    rootfs_sha = hashlib.sha256(rootfs).hexdigest()
    if rootfs_sha != state['rootfs_sha256']:
        raise SystemExit('linked embedded rootfs changed')
    patch = ROOT / 'linux-tests/kernel-patches/0027-blackparrot-icache-retention-control.patch'
    if sha(patch) != state['patch_sha256']:
        raise SystemExit('source patch differs from linked gate')
    with tempfile.TemporaryDirectory(prefix='conversion-verification-', dir=str(OUT)) as directory:
        temp = Path(directory)
        commands = [[PREFIX + 'strip', '-o', str(temp / 'vmlinux-stripped'), str(linked)],
                    [PREFIX + 'objcopy', '-O', 'binary', str(temp / 'vmlinux-stripped'), str(temp / 'vmlinux.bin')]]
        for command in commands:
            subprocess.run(command, check=True)
        if sha(temp / 'vmlinux-stripped') != sha(stripped) or sha(temp / 'vmlinux.bin') != sha(binary):
            raise SystemExit('SDK strip/objcopy reconstruction differs from supplied binary')
    print('Verified exact linked ELF conversion, rootfs, config and source patch.', flush=True)
    csr = csr_gate(linked)
    print('Verified exactly reviewed probe/control CSR uses in executable ELF.', flush=True)
    old, candidate, reverse, extracted, manifest = generated
    extraction = extract(SOURCE, old, SIZE, BASE)
    forward = splice(SOURCE, old, binary, candidate, BASE)
    print('Forward-spliced exact new payload while preserving firmware/collateral.', flush=True)
    reverse_summary = splice(candidate, binary, old, reverse, BASE)
    if sha(reverse) != EXPECTED_SOURCE or reverse.read_bytes() != SOURCE.read_bytes():
        raise SystemExit('reverse splice did not reconstruct source byte-for-byte')
    extract(candidate, extracted, SIZE, BASE)
    if sha(extracted) != sha(binary):
        raise SystemExit('candidate NBF does not reconstruct exact new payload')
    preserved = nonkernel_digest(SOURCE)
    if nonkernel_digest(candidate) != preserved:
        raise SystemExit('nonkernel collateral records changed')
    scanner = ROOT / 'codex-skills/bp-fpga-synthesis/scripts/check_nbf_csr_collisions.sh'
    scanner_command = [str(scanner), str(SOURCE), '5c1']
    checked = subprocess.run(scanner_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (HERE / 'baseline-nbf-csr5c1.log').write_text(checked.stdout)
    if checked.returncode:
        raise SystemExit('accepted baseline contains a 4-byte-aligned CSR collision')
    result = {'state': 'offline-package-verified',
              'scope': 'reversible offline kernel replacement; no boot, old-hardware fallback or performance acceptance',
              'source_nbf': artifact(SOURCE), 'candidate_nbf': artifact(candidate),
              'old_payload': artifact(old), 'new_payload': artifact(binary),
              'candidate_extracted_payload': artifact(extracted), 'reverse_nbf': artifact(reverse),
              'linked_elf': artifact(linked), 'stripped_elf': artifact(stripped),
              'configuration': artifact(HERE / 'input-.config'), 'source_patch': artifact(patch),
              'build_manifest': artifact(HERE / 'manifest.json'), 'object_review': artifact(HERE / 'object-review.json'),
              'conversion_commands': commands, 'config_rootfs_unchanged': True,
              'embedded_rootfs_cpio_sha256': rootfs_sha, 'compressed_rootfs': artifact(HERE / 'link-usr_initramfs_inc_data'),
              'extraction': extraction, 'forward_splice': forward, 'reverse_splice': reverse_summary,
              'preserved_nonkernel_collateral': preserved, 'csr5c1_executable_uses': csr,
              'baseline_csr_scan': {'command': scanner_command, 'result': 'PASS',
                                    'scope': '32-bit words at 4-byte-aligned NBF positions only; not complete RVC instruction coverage'},
              'qualification': 'Preserved shared-prefix table is byte-identical; this does not establish its usefulness for the new kernel.'}
    rendered = json.dumps(result, indent=2) + '\n'
    manifest.write_text(rendered)
    (HERE / 'package-manifest.json').write_text(rendered)
    print('Verified forward/reverse package: ' + str(candidate), flush=True)
    print('CANDIDATE_SHA256=' + sha(candidate), flush=True)


if __name__ == '__main__':
    main()
