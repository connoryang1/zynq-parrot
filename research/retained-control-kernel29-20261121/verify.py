#!/usr/bin/env python3
"""Independently reread new29 artifacts and bounded NBF; never contact a board."""
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

import build

HERE, ROOT = build.HERE, build.ROOT
sys.path.insert(0, str(ROOT / 'linux-tests'))
from extract_linux_kernel_nbf import extract
sys.path.insert(0, str(ROOT / 'research/embedded46-20261120'))
import build_pair as gate
from verify_pair import load_write_bound


def bindings(value):
    if isinstance(value, dict):
        if {'path', 'bytes', 'sha256'} <= set(value):
            assert build.record(value['path']) == {key: value[key] for key in ('path', 'bytes', 'sha256')}, value['path']
        for child in value.values():
            bindings(child)
    elif isinstance(value, list):
        for child in value:
            bindings(child)


def main():
    state = json.loads((HERE / 'build-manifest.json').read_text())
    package = json.loads((HERE / 'package-manifest.json').read_text())
    assert state['state'] == 'build-complete'
    assert package['state'] == 'offline-linked-0029-bounded46-NBF-verified; target pending'
    bindings(state)
    bindings(package)
    assert build.snapshot(build.CANONICAL) == state['canonical_before']
    assert build.snapshot(build.OLD) == state['accepted_tree_before']
    assert state['prepared_tree']['.config']['sha256'] == '0993bc8c2626df752520634f78a3826c952a269dfb09871541e4b1fbe0e53cd8'
    assert '&& bp_preview_mode != 13) {' in (build.TREE / 'kernel/sched/core.c').read_text()
    assert '&& bp_preview_mode != 14) {' not in (build.TREE / 'kernel/sched/core.c').read_text()
    candidate, source = Path(package['candidate']['path']), Path(package['source_nbf']['path'])
    assert Path(package['exact_reverse']['path']).read_bytes() == source.read_bytes()
    output = build.EXTERNAL / 'independent-readback.bin'
    if output.exists() or (HERE / 'verification.json').exists():
        raise RuntimeError('refusing to overwrite independent verification')
    summary = extract(candidate, output, package['binary']['bytes'], 0x80200000)
    assert output.read_bytes() == Path(package['binary']['path']).read_bytes()
    current, _ = gate.reconstruct(candidate)
    image = output.read_bytes()
    start = 0x80200000 - gate.BASE
    assert current[start:start + len(image)] == image
    rootfs = package['rootfs']
    offset = int(rootfs['kernel_offset'], 16)
    compressed = image[offset:offset + rootfs['compressed']['bytes']]
    assert hashlib.sha256(compressed).hexdigest() == rootfs['compressed']['sha256']
    assert gzip.decompress(compressed) == build.CPIO.read_bytes()
    _, trees = gate.inventory(current)
    assert len(trees) == 1 and trees[0][0] == gate.DTB_ADDRESS
    tree = trees[0][1]
    prop = next(p for p in tree['properties'] if p['node'] == '/chosen' and p['name'] == 'bootargs')
    assert prop['data'] == b'console=hvc0 loglevel=8 rdinit=/bin/sh mem=46M  \0'
    assert prop['bytes'] == 49 and tree['total'] == 1209
    rounded = (tree['total'] + 7) & ~7
    for base in (gate.DTB_ADDRESS, gate.NEXT_ARG1):
        assert gate.BASE <= base and base + rounded <= gate.BASE + gate.OWNED_BYTES
    extent = package['kernel_runtime_extent']
    assert int(extent['physical_end_exclusive'], 16) <= gate.NEXT_ARG1
    bound = load_write_bound(candidate)
    assert bound == package['load_bound'] and bound['allocation_bytes'] == 48234496
    review = json.loads((HERE / 'new29-csr-review.json').read_text())
    va = int(extent['virtual_start'], 16)
    for use in review['matches']:
        # Bind every reviewed linked instruction to the actual NBF memory,
        # including the legacy read at a halfword rather than word boundary.
        physical = 0x80200000 + int(use['address'], 16) - va
        word = struct.unpack_from('<I', current, physical - gate.BASE)[0]
        assert word == int(use['word'], 16)
    assert sorted(r['csr'] for r in review['matches']) == ['0x5c1', '0x5c1', '0x5c2', '0x5c2']
    exception = json.loads((HERE / 'linked-exception-review.json').read_text())
    assert len(exception['entries']) == 2
    for entry in exception['entries']:
        assert int(entry['fixup_pc'], 16) == int(entry['fault_pc'], 16) + 4
        assert entry['type'] == 3 and entry['error_register'] != entry['zero_register']
    repository_heads = {}
    sdk = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk')
    for name, path in (('SDK', sdk), ('SDK_linux', sdk / 'linux'), ('worktree', ROOT)):
        assert (path / '.git').exists(), path
        repository_heads[name] = dict(path=str(path), head=subprocess.check_output(
            ['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip(),
            qualification='repository HEAD only; actual patched/build inputs are hash-bound separately')
    result = dict(state='PASS offline actual-linked-kernel and bounded-NBF verification; runtime pending',
        verifier=build.record(Path(__file__)), build_manifest=build.record(HERE / 'build-manifest.json'),
        package_manifest=build.record(HERE / 'package-manifest.json'),
        readback=build.record(output), extraction=summary, load_bound=bound,
        optional_csr_instructions_match_actual_nbf=True, both_linked_extable_entries_checked=True,
        accepted_rootfs_compressed_and_uncompressed_exact=True, optional0028_absent=True,
        old_accepted_and_canonical_input_snapshots_unchanged=True,
        all_package_build_bindings_verified=True, repositories=repository_heads,
        packaging_host_tests=build.record(HERE / 'packaging-host-tests.log'),
        limits='No board run, actual boot bounds, illegal-CSR trap execution or performance acceptance.')
    (HERE / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('INDEPENDENT_NEW29_OFFLINE_VERIFICATION_PASS', flush=True)


if __name__ == '__main__':
    main()
