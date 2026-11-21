#!/usr/bin/env python3
"""Isolate the accepted 0027 kernel, add 0029 and build at most two jobs."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = Path('/dev/shm/zp-linux-resume-capacity-20261120/linux-retention-kernel')
SDK = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot')
CANONICAL = SDK / 'build/linux-6.6'
EXTERNAL = Path('/home/coyang/fpga-artifacts/context-resume/retained-control-kernel29-20261121')
TREE = EXTERNAL / 'build/linux-6.6'
INPUTS = EXTERNAL / 'inputs'
ACCEPTED = ROOT / 'research/retention-kernel-20261120/accepted-rootfs'
CPIO = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/kernel27/accepted-rootfs.cpio')
PREFIX = str(SDK / 'host/bin/riscv64-linux-')
PATCH = ROOT / 'linux-tests/kernel-patches/0029-blackparrot-retained-control.patch'
TRACK = ('kernel/sys.c', 'include/uapi/linux/prctl.h', 'fs/pipe.c', 'kernel/sched/core.c',
         'kernel/futex/syscalls.c', '.config', 'include/generated/autoconf.h',
         'include/generated/compile.h', 'include/generated/utsversion.h',
         'usr/initramfs_inc_data', 'arch/riscv/mm/extable.c',
         'arch/riscv/kernel/traps.c', 'arch/riscv/include/asm/asm-extable.h')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def record(path):
    path = Path(path)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))


def snapshot(tree):
    return {name: record(tree / name) for name in TRACK}


def save(value):
    (HERE / 'build-manifest.json').write_text(json.dumps(value, indent=2) + '\n')


def run(command, log, env=None):
    started = time.time()
    with (HERE / log).open('wb') as stream:
        result = subprocess.run(list(map(str, command)), cwd=ROOT, env=env,
                                stdout=stream, stderr=subprocess.STDOUT)
    value = dict(argv=list(map(str, command)), cwd=str(ROOT), exit_code=result.returncode,
                 elapsed_seconds=time.time() - started, log=record(HERE / log))
    if result.returncode:
        raise RuntimeError('command failed: ' + log)
    return value


def patch(path, reverse=False, dry=False):
    command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-d', str(TREE)]
    if reverse:
        command += ['--reverse']
    if dry:
        command += ['--dry-run']
    result = subprocess.run(command, input=path.read_bytes(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return command, result


def prepare():
    if EXTERNAL.exists() or (HERE / 'build-manifest.json').exists():
        raise RuntimeError('refusing to overwrite new29 build/evidence')
    accepted = json.loads((ACCEPTED / 'manifest.json').read_text())
    prior = json.loads((ACCEPTED.parent / 'manifest.json').read_text())
    before = snapshot(CANONICAL)
    old = snapshot(OLD)
    for name in ('kernel/sys.c', '.config', 'usr/initramfs_inc_data'):
        assert old[name]['sha256'] == accepted['artifacts'][name]['sha256'], name
    for name in ('fs/pipe.c', 'include/uapi/linux/prctl.h'):
        assert old[name]['sha256'] == prior['normalized_sources'][name], name
    assert old['kernel/sched/core.c']['sha256'] == before['kernel/sched/core.c']['sha256']
    core = (OLD / 'kernel/sched/core.c').read_text()
    assert '&& bp_preview_mode != 13) {' in core and '&& bp_preview_mode != 14) {' not in core
    assert sha(OLD / 'vmlinux') == accepted['artifacts']['vmlinux']['sha256']
    assert sha(CPIO) == accepted['decompressed_cpio_sha256']
    assert sha(PATCH) == 'e95007acf320f399c6d22cd844e826c2298dc32081a5a45dd8daab75c92069d3'
    reference = json.loads((ROOT / 'research/retained-control-abi-20261121/manifest.json').read_text())
    tools = {}
    for name in ('compiler_wrapper', 'compiler_real', 'readelf'):
        item = reference['tools'][name]
        tools[name] = record(Path(item['path']))
        assert tools[name]['sha256'] == item['sha256']
    # Compare actual regular source inputs to the accepted build's canonical
    # origin. Generated outputs and tools/host products are separately bound.
    inventory, changes = [], []
    for path in sorted(OLD.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        name = str(path.relative_to(OLD))
        if name in ('.tmp_vmlinux.kallsyms1.S', '.tmp_vmlinux.kallsyms2.S', 'init/utsversion-tmp.h'):
            continue
        if name.startswith(('include/generated/', 'include/config/', 'arch/riscv/include/generated/', 'tools/')):
            continue
        if path.suffix not in ('.c', '.h', '.S', '.lds', '.sh', '.py', '.pl', '.awk', '.tbl', '.rs') \
                and not path.name.startswith(('Makefile', 'Kconfig')):
            continue
        other = CANONICAL / name
        assert other.is_file(), name
        left, right = sha(path), sha(other)
        inventory.append(dict(name=name, accepted_tree_sha256=left, canonical_sha256=right))
        if left != right:
            changes.append(name)
    assert changes == ['fs/pipe.c', 'include/uapi/linux/prctl.h', 'kernel/sys.c'], changes
    EXTERNAL.mkdir()
    INPUTS.mkdir()
    (INPUTS / 'tmp').mkdir()
    inventory_path = EXTERNAL / 'source-inventory.json'
    inventory_path.write_text(json.dumps(inventory, indent=2) + '\n')
    state = dict(state='copy-running', scope='isolated actual 0027+0029 kernel build; no 0028 or target run',
                 source_tree=str(OLD), tree=str(TREE), canonical_before=before,
                 accepted_tree_before=old, accepted_link_manifest=record(ACCEPTED / 'manifest.json'),
                 prior_link_manifest=record(ACCEPTED.parent / 'manifest.json'),
                 source_inventory=record(inventory_path), compared_regular_sources=len(inventory),
                 accepted_normalization_difference_files=changes, patch=record(PATCH), tools=tools,
                 build_script=record(Path(__file__)))
    save(state)
    state['copy'] = run(['cp', '-a', OLD, TREE], 'copy.log') if TREE.parent.exists() else None
    if not TREE.exists():
        TREE.parent.mkdir(parents=True)
        state['copy'] = run(['cp', '-a', OLD, TREE], 'copy.log')
    # cp -a preserves in-tree hardlink groups, but none may share source inodes.
    for name in TRACK + ('vmlinux',):
        a, b = (OLD / name).stat(), (TREE / name).stat()
        assert (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino), name
    assert snapshot(OLD) == old and snapshot(CANONICAL) == before
    for dry in (True, False):
        command, result = patch(PATCH, dry=dry)
        path = HERE / ('0029-forward-dry-run.log' if dry else '0029-forward-applied.log')
        path.write_bytes(result.stdout)
        assert result.returncode == 0, result.stdout.decode()
    command, result = patch(PATCH, reverse=True, dry=True)
    (HERE / '0029-reverse-dry-run.log').write_bytes(result.stdout)
    assert result.returncode == 0, result.stdout.decode()
    shutil.copyfile(CPIO, INPUTS / 'rootfs.cpio')
    assert sha(INPUTS / 'rootfs.cpio') == accepted['decompressed_cpio_sha256']
    for name in ('kernel/sys.c', 'include/uapi/linux/prctl.h', '.config', 'include/generated/compile.h',
                 'include/generated/utsversion.h'):
        target = HERE / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TREE / name, target)
    state.update(state='prepared', prepared_tree=snapshot(TREE), rootfs=record(INPUTS / 'rootfs.cpio'),
                 excluded_0028=True, canonical_after=snapshot(CANONICAL))
    save(state)
    print('PREPARED isolated new29 kernel; accepted source/config/rootfs identities verified', flush=True)


def build():
    state = json.loads((HERE / 'build-manifest.json').read_text())
    assert state['state'] == 'prepared'
    assert snapshot(CANONICAL) == state['canonical_before']
    assert snapshot(OLD) == state['accepted_tree_before']
    assert snapshot(TREE) == state['prepared_tree']
    assert sha(INPUTS / 'rootfs.cpio') == state['rootfs']['sha256']
    env = os.environ.copy()
    for key in ('KBUILD_OUTPUT', 'KBUILD_SRC', 'MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES'):
        env.pop(key, None)
    chosen = dict(ARCH='riscv', CROSS_COMPILE=PREFIX, BR_BINARIES_DIR=str(INPUTS),
                  TMPDIR=str(INPUTS / 'tmp'), CCACHE_DISABLE='1', KBUILD_BUILD_VERSION='28',
                  KBUILD_BUILD_TIMESTAMP='Fri Nov 20 15:11:06 EST 2026',
                  KBUILD_BUILD_USER='coyang', KBUILD_BUILD_HOST='blackparrot1')
    env.update(chosen)
    state.update(state='build-running', environment=chosen)
    save(state)
    try:
        state['build'] = run(['make', '-C', TREE, '-j2', 'ARCH=riscv',
                              'CROSS_COMPILE=' + PREFIX, 'V=1', 'vmlinux'], 'build.log', env)
        assert snapshot(CANONICAL) == state['canonical_before']
        assert snapshot(OLD) == state['accepted_tree_before']
        for name in ('kernel/sys.c', 'include/uapi/linux/prctl.h', '.config', 'include/generated/compile.h',
                     'include/generated/utsversion.h'):
            assert sha(TREE / name) == state['prepared_tree'][name]['sha256'], name
        assert sha(TREE / 'usr/initramfs_inc_data') == state['accepted_tree_before']['usr/initramfs_inc_data']['sha256']
        plain = gzip.decompress((TREE / 'usr/initramfs_inc_data').read_bytes())
        assert hashlib.sha256(plain).hexdigest() == state['rootfs']['sha256']
        assert plain == (INPUTS / 'rootfs.cpio').read_bytes()
        state.update(state='build-complete', artifacts={name: record(TREE / name) for name in
                     ('vmlinux', 'System.map', 'kernel/sys.o', 'kernel/.sys.o.cmd', 'usr/initramfs_inc_data')},
                     canonical_after=snapshot(CANONICAL), accepted_tree_after=snapshot(OLD),
                     unchanged_compressed_rootfs=True, unchanged_decompressed_cpio=True)
        print('BUILD_COMPLETE new29; exact accepted config/banner/rootfs and input sources preserved', flush=True)
    except BaseException as error:
        state.update(state='failed', error=repr(error))
        raise
    finally:
        save(state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'build'))
    args = parser.parse_args()
    prepare() if args.phase == 'prepare' else build()
