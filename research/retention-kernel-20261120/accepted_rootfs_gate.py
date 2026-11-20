#!/usr/bin/env python3
"""Relink and package the retention kernel with the exact accepted rootfs.

The link phase needs the host RAM namespace; package uses durable artifacts
only. Original prepared-SDK-rootfs diagnostics and SDK inputs stay unchanged.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EVIDENCE = HERE / 'accepted-rootfs'
TREE = Path('/dev/shm/zp-linux-resume-capacity-20261120/linux-retention-kernel')
INPUTS = TREE.parent / 'linux-retention-accepted-inputs'
ORIGINAL_INPUTS = TREE.parent / 'linux-retention-inputs'
ARTIFACT_ROOT = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120')
OUT = ARTIFACT_ROOT / 'kernel27-accepted-rootfs'
CPIO = ARTIFACT_ROOT / 'kernel27/accepted-rootfs.cpio'
EXPECTED_CPIO = 'e2f7dbc4d02d0ae99bb66832fe94b4882e19d7c95acd2cc0521299ff6aa73f50'
SOURCE = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/build/linux-6.6')
PREFIX = '/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux-'


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def record(path):
    return {'path': str(path.resolve()), 'sha256': sha(path), 'bytes': path.stat().st_size}


def save(state):
    (EVIDENCE / 'manifest.json').write_text(json.dumps(state, indent=2) + '\n')


def canonical_hashes(original):
    return {name: sha(SOURCE / name) for name in original['canonical_before']}


def preserved_diagnostics():
    names = ('manifest.json', 'package-manifest.json', 'link-vmlinux', 'link-System.map',
             'link-usr_initramfs_inc_data', 'input-.config', 'input-kernel_sys.c')
    return {name: sha(HERE / name) for name in names}


def link():
    if not TREE.is_dir():
        raise SystemExit('host RAM kernel tree unavailable in this namespace; no build started')
    if EVIDENCE.exists() or INPUTS.exists():
        raise SystemExit('refusing to overwrite accepted-rootfs evidence or input directory')
    original = json.loads((HERE / 'manifest.json').read_text())
    if canonical_hashes(original) != original['canonical_before']:
        raise SystemExit('canonical source drift')
    if sha(CPIO) != EXPECTED_CPIO or sha(TREE / '.config') != original['canonical_before']['.config']:
        raise SystemExit('accepted input or existing kernel config mismatch')
    for name in ('kernel/sys.c', 'fs/pipe.c', 'include/uapi/linux/prctl.h'):
        if sha(TREE / name) != original['normalized_sources'][name]:
            raise SystemExit('prepared patched kernel source changed: ' + name)
    previous_rootfs = sha(ORIGINAL_INPUTS / 'rootfs.cpio')
    if previous_rootfs != original['rootfs_sha256']:
        raise SystemExit('original diagnostic rootfs input drift')
    uts = (TREE / 'include/generated/utsversion.h').read_text()
    compiler = (TREE / 'include/generated/compile.h').read_text()
    version_file = (TREE / '.version').read_text().strip()
    banner = re.search(r'^#define UTS_VERSION "(.*)"$', uts, re.M)
    number = re.search(r'^#(\d+) ', banner[1] if banner else '')
    timestamp = re.search(r'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+.*$', banner[1] if banner else '')
    if not number or not timestamp or not version_file.isdigit():
        raise SystemExit('cannot safely preserve existing UTS version/timestamp')
    EVIDENCE.mkdir()
    INPUTS.mkdir()
    (INPUTS / 'tmp').mkdir()
    shutil.copyfile(CPIO, INPUTS / 'rootfs.cpio')
    if sha(INPUTS / 'rootfs.cpio') != EXPECTED_CPIO:
        raise SystemExit('accepted CPIO copy mismatch')
    env = os.environ.copy()
    for key in ('KBUILD_OUTPUT', 'KBUILD_SRC', 'MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES'):
        env.pop(key, None)
    chosen = {'ARCH': 'riscv', 'CROSS_COMPILE': PREFIX, 'BR_BINARIES_DIR': str(INPUTS),
              'TMPDIR': str(INPUTS / 'tmp'), 'CCACHE_DISABLE': '1',
              'KBUILD_BUILD_VERSION': number[1], 'KBUILD_BUILD_TIMESTAMP': timestamp[0]}
    for macro, key in (('LINUX_COMPILE_BY', 'KBUILD_BUILD_USER'), ('LINUX_COMPILE_HOST', 'KBUILD_BUILD_HOST')):
        value = re.search(r'^#define ' + macro + r'\s+"(.*)"$', compiler, re.M)
        if value:
            chosen[key] = value[1]
    env.update(chosen)
    state = {'state': 'link-running', 'scope': 'offline relink with exact accepted rootfs; no boot/performance acceptance',
             'infrastructure': 'default subagent /dev/shm namespace is private; root executes host-RAM link, not a source failure',
             'old_diagnostic_manifest': record(HERE / 'manifest.json'),
             'preserved_diagnostic_hashes': preserved_diagnostics(), 'original_input_rootfs_sha256': previous_rootfs,
             'canonical_before': original['canonical_before'], 'accepted_cpio': record(CPIO),
             'ram_inputs': str(INPUTS), 'env': chosen, 'uts_before': uts, 'version_file_before': version_file,
             'config_before_sha256': sha(TREE / '.config'), 'patched_source_before_sha256': sha(TREE / 'kernel/sys.c')}
    (EVIDENCE / 'utsversion-before.h').write_text(uts)
    (EVIDENCE / 'compile-before.h').write_text(compiler)
    command = ['make', '-C', str(TREE), '-j8', 'ARCH=riscv', 'CROSS_COMPILE=' + PREFIX, 'V=1', 'vmlinux']
    state['command'] = command
    save(state)
    print('Linking with accepted CPIO; prior diagnostic evidence preserved.', flush=True)
    started = time.time()
    try:
        with (EVIDENCE / 'accepted-build.log').open('w') as output:
            result = subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT)
        state.update(exit_code=result.returncode, seconds=time.time() - started)
        if result.returncode:
            raise RuntimeError('accepted-rootfs kernel link failed; see accepted-build.log')
        state['canonical_after'] = canonical_hashes(original)
        if state['canonical_after'] != state['canonical_before'] or preserved_diagnostics() != state['preserved_diagnostic_hashes']:
            raise RuntimeError('canonical input or preserved diagnostic changed')
        if sha(ORIGINAL_INPUTS / 'rootfs.cpio') != previous_rootfs:
            raise RuntimeError('original ac6 input changed')
        if sha(TREE / '.config') != state['config_before_sha256'] or sha(TREE / 'kernel/sys.c') != state['patched_source_before_sha256']:
            raise RuntimeError('kernel configuration or patched source changed')
        state['uts_after'] = (TREE / 'include/generated/utsversion.h').read_text()
        state['version_file_after'] = (TREE / '.version').read_text().strip()
        if state['uts_after'] != uts:
            raise RuntimeError('UTS banner unexpectedly changed despite preserved build identity')
        state['artifacts'] = {}
        for source, target in (('vmlinux', 'accepted-vmlinux'), ('System.map', 'accepted-System.map'),
                               ('usr/initramfs_inc_data', 'accepted-initramfs_inc_data'),
                               ('usr/.initramfs_inc_data.cmd', 'accepted-initramfs.cmd'),
                               ('.config', 'accepted-config'), ('kernel/sys.c', 'accepted-kernel_sys.c'),
                               ('kernel/sys.o', 'accepted-kernel_sys.o'), ('kernel/.sys.o.cmd', 'accepted-sys.o.cmd')):
            shutil.copyfile(TREE / source, EVIDENCE / target)
            state['artifacts'][source] = record(EVIDENCE / target)
        plain = gzip.decompress((EVIDENCE / 'accepted-initramfs_inc_data').read_bytes())
        state['decompressed_cpio_sha256'] = hashlib.sha256(plain).hexdigest()
        state['decompressed_cpio_bytes'] = len(plain)
        if state['decompressed_cpio_sha256'] != EXPECTED_CPIO or plain != CPIO.read_bytes():
            raise RuntimeError('linked rootfs is not byte-identical to accepted CPIO')
        state['compressed_matches_original'] = sha(EVIDENCE / 'accepted-initramfs_inc_data') == sha(CPIO.with_suffix('.cpio.gz'))
        state['state'] = 'accepted-rootfs-link-complete'
        print('Accepted-rootfs link complete; CPIO/config/banner/canonical inputs verified.', flush=True)
    except BaseException as error:
        state.update(state='failed', error=repr(error))
        raise
    finally:
        state['build_log'] = record(EVIDENCE / 'accepted-build.log')
        save(state)


def package():
    state = json.loads((EVIDENCE / 'manifest.json').read_text())
    if state['state'] != 'accepted-rootfs-link-complete' or OUT.exists():
        raise SystemExit('accepted link incomplete or package directory already exists')
    if preserved_diagnostics() != state['preserved_diagnostic_hashes']:
        raise SystemExit('original diagnostic evidence changed')
    if state['decompressed_cpio_sha256'] != EXPECTED_CPIO:
        raise SystemExit('accepted rootfs identity missing')
    spec = importlib.util.spec_from_file_location('reviewed_package', HERE / 'package_kernel27.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.HERE = EVIDENCE  # Isolate all disassembly/report output names.
    OUT.mkdir()
    linked = EVIDENCE / 'accepted-vmlinux'
    stripped, binary = OUT / 'vmlinux-stripped', OUT / 'vmlinux.bin'
    commands = [[PREFIX + 'strip', '-o', str(stripped), str(linked)],
                [PREFIX + 'objcopy', '-O', 'binary', str(stripped), str(binary)]]
    for command in commands:
        subprocess.run(command, check=True)
    if binary.stat().st_size != helper.SIZE:
        raise RuntimeError('new binary size differs; do not silently pad/change payload window')
    blob = (EVIDENCE / 'accepted-initramfs_inc_data').read_bytes()
    image = binary.read_bytes()
    if image.count(blob) != 1:
        raise RuntimeError('converted kernel does not contain the unique accepted initramfs blob')
    embedded_offset = image.find(blob)
    csr = helper.csr_gate(linked)
    section_text = subprocess.check_output([PREFIX + 'readelf', '-SW', str(linked)], text=True)
    match = re.search(r'\[\s*\d+\]\s+__ex_table\s+PROGBITS\s+([0-9a-fA-F]+)', section_text)
    if not match:
        raise RuntimeError('linked exception table missing')
    table = EVIDENCE / 'accepted-ex-table.bin'
    subprocess.run([PREFIX + 'objcopy', '--only-section=__ex_table', '-O', 'binary', str(linked), str(table)], check=True)
    data, section_base = table.read_bytes(), int(match[1], 16)
    probe = next(item for item in csr['matches'] if 'bp_icache_retention_probe' in item['functions'])
    probe_pc, entries = int(probe['address'], 16), []
    for offset in range(0, len(data), 12):
        relative, fix, kind, registers = struct.unpack_from('<iiHH', data, offset)
        if (section_base + offset + relative) & ((1 << 64) - 1) == probe_pc:
            entries.append({'fault_pc': hex(probe_pc), 'fixup_pc': hex((section_base + offset + 4 + fix) & ((1 << 64) - 1)),
                            'type': kind, 'data': hex(registers), 'error_register': registers & 31, 'zero_register': (registers >> 5) & 31})
    if len(entries) != 1 or entries[0]['fixup_pc'] != hex(probe_pc + 4) or entries[0]['type'] != 3 or entries[0]['data'] != '0x1cf':
        raise RuntimeError('linked safe-probe fixup changed')
    source = ARTIFACT_ROOT / 'linux-prefix32-futex-usersyscall-shell.nbf'
    if sha(source) != helper.EXPECTED_SOURCE:
        raise RuntimeError('accepted source NBF drift')
    old = ARTIFACT_ROOT / 'kernel27/old-kernel-from-ef50.bin'
    if sha(old) != 'bf0318e848701a99a58a27436861f88d43340245071c036788488e58dcf7be6d':
        raise RuntimeError('old accepted payload drift')
    candidate = OUT / 'linux-prefix32-retention27-accepted-rootfs-shell.nbf'
    forward = helper.splice(source, old, binary, candidate, helper.BASE)
    reverse = OUT / 'reverse-to-ef50.nbf'
    helper.splice(candidate, binary, old, reverse, helper.BASE)
    if reverse.read_bytes() != source.read_bytes():
        raise RuntimeError('reverse NBF is not byte-identical')
    extracted = OUT / 'candidate-extracted.bin'
    helper.extract(candidate, extracted, helper.SIZE, helper.BASE)
    if extracted.read_bytes() != binary.read_bytes():
        raise RuntimeError('candidate does not reconstruct exact new kernel')
    preserved = helper.nonkernel_digest(source)
    if helper.nonkernel_digest(candidate) != preserved:
        raise RuntimeError('firmware/collateral changed')
    result = {'state': 'accepted-rootfs-offline-package-verified',
              'scope': 'new helper-kernel baseline with accepted rootfs; no board boot or performance acceptance',
              'link_manifest': record(EVIDENCE / 'manifest.json'), 'conversion_commands': commands,
              'candidate': record(candidate), 'source_nbf': record(source), 'old_payload': record(old),
              'linked_elf': record(linked), 'stripped_elf': record(stripped), 'binary': record(binary),
              'candidate_reextracted': record(extracted), 'reverse_nbf': record(reverse),
              'source_config_preserved': True, 'accepted_rootfs_cpio_sha256': EXPECTED_CPIO,
              'rootfs_blob': record(EVIDENCE / 'accepted-initramfs_inc_data'),
              'rootfs_blob_offset_in_binary': hex(embedded_offset),
              'uts_banner_preserved': state['uts_before'] == state['uts_after'],
              'csr_review': csr, 'exception_probe': entries[0], 'exception_table': record(table),
              'forward_splice': forward, 'preserved_nonkernel_collateral': preserved,
              'original_diagnostics_preserved': preserved_diagnostics() == state['preserved_diagnostic_hashes'],
              'limits': 'Kernel helper code is new, so performance must use matched controls within this exact new image.'}
    rendered = json.dumps(result, indent=2) + '\n'
    (OUT / 'package-manifest.json').write_text(rendered)
    (EVIDENCE / 'package-manifest.json').write_text(rendered)
    print('Accepted-rootfs candidate: ' + str(candidate), flush=True)
    print('CANDIDATE_SHA256=' + sha(candidate), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('link', 'package'))
    args = parser.parse_args()
    link() if args.phase == 'link' else package()
