#!/usr/bin/env python3
"""Compile the retention ABI in an independent RAM copy of prepared Linux.

The canonical SDK and rootfs are read-only inputs. Phases stop before NBF
packaging; build output, normalized-source diffs, and hashes remain durable.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[1]
SOURCE = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/build/linux-6.6')
TREE = Path('/dev/shm/zp-linux-resume-capacity-20261120/linux-retention-kernel')
INPUTS = TREE.parent / 'linux-retention-inputs'
PREFIX = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux-')
ROOTFS = SOURCE.parents[1] / 'images/rootfs.cpio'
TRACK = ['kernel/sys.c', 'fs/pipe.c', 'kernel/futex/syscalls.c', 'include/uapi/linux/prctl.h',
         '.config', 'include/generated/autoconf.h', 'include/config/auto.conf',
         'kernel/.sys.o.cmd', 'usr/initramfs_inc_data', 'usr/.initramfs_inc_data.cmd',
         'arch/riscv/kernel/traps.c', 'arch/riscv/mm/extable.c', 'arch/riscv/include/asm/asm-extable.h']


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def snapshot():
    return {name: sha(SOURCE / name) for name in TRACK}


def save(state):
    (EVIDENCE / 'manifest.json').write_text(json.dumps(state, indent=2) + '\n')


def command(argv, log, cwd=TREE, env=None):
    (EVIDENCE / (log + '.command.json')).write_text(json.dumps(argv, indent=2) + '\n')
    started = time.time()
    with (EVIDENCE / log).open('w') as output:
        result = subprocess.run(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('{} failed with status {}; see {}'.format(argv[0], result.returncode, log))
    return {'command': argv, 'log_sha256': sha(EVIDENCE / log), 'seconds': time.time() - started,
            'exit_code': result.returncode}


def patch(path, reverse=False, dry_run=False):
    args = ['patch', '--batch', '--fuzz=0', '-p1', '-d', str(TREE), '--reverse' if reverse else '--forward']
    if dry_run:
        args.append('--dry-run')
    with path.open('rb') as source:
        result = subprocess.run(args, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result


def build_env():
    env = os.environ.copy()
    for key in ('KBUILD_OUTPUT', 'KBUILD_SRC', 'MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES'):
        env.pop(key, None)
    env.update(ARCH='riscv', CROSS_COMPILE=str(PREFIX), BR_BINARIES_DIR=str(INPUTS),
               CCACHE_DISABLE='1', TMPDIR=str(INPUTS / 'tmp'))
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'object', 'link'))
    args = parser.parse_args()
    manifest = EVIDENCE / 'manifest.json'
    if args.phase == 'prepare':
        if TREE.exists() or manifest.exists():
            raise SystemExit('refusing to replace existing RAM tree or evidence manifest')
        if shutil.disk_usage('/dev/shm').free < 3 * 1024 ** 3:
            raise SystemExit('insufficient free RAM filesystem capacity')
        before = snapshot()
        state = {'state': 'preparing', 'source': str(SOURCE), 'tree': str(TREE),
                 'canonical_before': before, 'rootfs_source': str(ROOTFS), 'rootfs_sha256': sha(ROOTFS)}
        save(state)
        TREE.parent.mkdir(parents=True, exist_ok=True)
        state['copy'] = command(['cp', '-a', str(SOURCE), str(TREE)], 'copy.log', cwd=EVIDENCE)
        INPUTS.mkdir()
        (INPUTS / 'tmp').mkdir()
        shutil.copyfile(ROOTFS, INPUTS / 'rootfs.cpio')
        if sha(INPUTS / 'rootfs.cpio') != state['rootfs_sha256']:
            raise RuntimeError('rootfs copy mismatch')
        external = []
        for parent, dirs, files in os.walk(TREE, followlinks=False):
            for name in dirs + files:
                path = Path(parent) / name
                if path.is_symlink() and TREE not in path.resolve().parents:
                    external.append(str(path))
        if external:
            raise RuntimeError('RAM copy has external symlinks: ' + repr(external))
        for name in TRACK:
            old, new = (SOURCE / name).stat(), (TREE / name).stat()
            if (old.st_dev, old.st_ino) == (new.st_dev, new.st_ino):
                raise RuntimeError('copy shares an SDK inode: ' + name)
        changes = []
        for name in ('kernel/sys.c', 'include/uapi/linux/prctl.h', 'fs/pipe.c'):
            path = TREE / name
            old = path.read_text()
            if name == 'kernel/sys.c':
                new = old.replace('if (arg2 > 15 || arg3 || arg4 || arg5)',
                                  'if (arg2 > 14 || arg3 || arg4 || arg5)').replace(
                                      'arg2 && arg2 != 14 && arg2 != 15', 'arg2 && arg2 != 14')
            elif name.endswith('prctl.h'):
                new = old.replace(' * 14 instruction replay at futex-wake entry;\n * 15 instruction replay at pipe-write entry. */',
                                  ' * 14 instruction replay at futex-wake entry. */')
            else:
                block = ('#ifdef CONFIG_RISCV\n\t/* Mode fifteen is inherited by an opted-in pipe workload. Launch the\n'
                         '\t * machine-owned shared prefix before pipe locking and reader wakeup.\n\t */\n'
                         '\tif (READ_ONCE(current->thread.bp_preview_phys_mode) == 15)\n'
                         '\t\tasm volatile("csrw 0x5c0, zero" ::: "memory");\n#endif\n\n')
                if old.count(block) != 1:
                    raise RuntimeError('orphan pipe hook does not match inspected source')
                new = old.replace(block, '')
                new = new.replace('#ifdef CONFIG_RISCV\n#include <asm/processor.h>\n#endif\n', '')
            path.write_text(new)
            changes.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                               fromfile='a/' + name, tofile='b/' + name))
        (EVIDENCE / 'removed-orphan-mode15.diff').write_text(''.join(changes))
        previous = ROOT / 'linux-tests/kernel-patches/0026-blackparrot-early-futex-instruction-replay.patch'
        tested = patch(previous, reverse=True, dry_run=True)
        (EVIDENCE / '0026-reverse-dry-run.log').write_bytes(tested.stdout)
        if tested.returncode:
            raise RuntimeError('normalized copy does not bind accepted 0026 tail')
        current = ROOT / 'linux-tests/kernel-patches/0027-blackparrot-icache-retention-control.patch'
        for dry in (True, False):
            tested = patch(current, dry_run=dry)
            (EVIDENCE / ('0027-forward-' + ('dry-run' if dry else 'applied') + '.log')).write_bytes(tested.stdout)
            if tested.returncode:
                raise RuntimeError('retention patch failed')
        tested = patch(current, reverse=True, dry_run=True)
        (EVIDENCE / '0027-reverse-dry-run.log').write_bytes(tested.stdout)
        if tested.returncode:
            raise RuntimeError('retention patch reverse verification failed')
        for name in ('kernel/sys.c', 'include/uapi/linux/prctl.h', 'fs/pipe.c', '.config', 'kernel/.sys.o.cmd'):
            target = EVIDENCE / ('input-' + name.replace('/', '_'))
            shutil.copyfile(TREE / name, target)
        state.update(state='prepared', normalized_sources={name: sha(TREE / name) for name in TRACK},
                     removed_orphan_diff_sha256=sha(EVIDENCE / 'removed-orphan-mode15.diff'),
                     patch_sha256=sha(current), canonical_after=snapshot())
        if state['canonical_after'] != before:
            raise RuntimeError('canonical source changed during isolated preparation')
        save(state)
        print('Prepared independent kernel and rootfs; canonical source hashes unchanged.', flush=True)
        return
    state = json.loads(manifest.read_text())
    if snapshot() != state['canonical_before']:
        raise SystemExit('canonical SDK input drift; audit before continuing')
    if sha(INPUTS / 'rootfs.cpio') != state['rootfs_sha256'] or sha(TREE / '.config') != state['canonical_before']['.config']:
        raise SystemExit('copied rootfs/config drift')
    target = 'kernel/sys.o' if args.phase == 'object' else 'vmlinux'
    state[args.phase] = command(['make', '-C', str(TREE), '-j8', 'ARCH=riscv',
                                'CROSS_COMPILE=' + str(PREFIX), 'V=1', target], args.phase + '-build.log',
                               cwd=EVIDENCE, env=build_env())
    state['canonical_after'] = snapshot()
    if state['canonical_after'] != state['canonical_before']:
        raise RuntimeError('canonical SDK input changed during isolated build')
    if sha(TREE / '.config') != state['canonical_before']['.config']:
        raise RuntimeError('kernel config changed during build')
    names = ['kernel/sys.o', 'kernel/.sys.o.cmd'] if args.phase == 'object' else ['vmlinux', 'System.map', 'usr/initramfs_inc_data']
    state[args.phase]['artifacts'] = {}
    for name in names:
        target = EVIDENCE / (args.phase + '-' + name.replace('/', '_'))
        shutil.copyfile(TREE / name, target)
        state[args.phase]['artifacts'][name] = {'path': str(target), 'sha256': sha(target)}
    state['state'] = args.phase + '-complete'
    save(state)
    print('Completed {} gate, canonical SDK/config preserved.'.format(args.phase), flush=True)


if __name__ == '__main__':
    main()
