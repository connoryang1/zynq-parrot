#!/usr/bin/env python3
"""Prepare one bounded retention-kernel NBF using existing reviewed helpers.

No kernel/rootfs build, target execution, runner change or reverse-image copy.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'research/embedded46-20261120'))
import build_pair as gate
from verify_pair import load_write_bound

ART = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120')
OUT = ART/'retention-kernel46-20261120'
SOURCE = ART/'kernel27-accepted-rootfs/linux-prefix32-retention27-accepted-rootfs-shell.nbf'
TARGET = OUT/'linux-prefix32-retention27-accepted-rootfs-mem46-shell.nbf'
SOURCE_SHA = 'c7c1e214796644b1dbe728cc274ca3d776c1cd24d4eb7ff570e109f44b53e3ff'


def record(path):
    return gate.record(Path(path))


def main():
    if OUT.exists() or (HERE/'manifest.json').exists():
        raise SystemExit('refusing to overwrite retention-kernel46 evidence')
    package_path = ROOT/'research/retention-kernel-20261120/accepted-rootfs/package-manifest.json'
    package = json.loads(package_path.read_text())
    source_binding = record(SOURCE)
    assert source_binding['sha256'] == package['candidate']['sha256'] == SOURCE_SHA
    prior_proof = ROOT/'research/embedded46-20261120/manifest.json'
    proofs = json.loads(prior_proof.read_text())
    boot_log = ART/'session12/0-retention-probe-absent.log'
    assert 'Domain0 Next Arg1         : 0x0000000082200000' in boot_log.read_text()
    source_guard = load_write_bound(SOURCE)
    old, _ = gate.reconstruct(SOURCE)
    inventory, trees = gate.inventory(old)
    assert len(trees) == 1 and trees[0][0] == gate.DTB_ADDRESS
    tree = trees[0][1]
    assert tree['total'] == 1209
    prop, old_value, new_value = gate.bootarg_edit(tree)
    assert prop['bytes'] == 49 and len(old_value) == len(new_value) == 48
    begin = gate.DTB_ADDRESS-gate.BASE
    original_dtb = bytes(old[begin:begin+tree['total']])
    arg_address = gate.DTB_ADDRESS+prop['offset']
    assert arg_address == 0x800163a0
    expected_dtb = bytearray(original_dtb)
    expected_dtb[prop['offset']:prop['offset']+48] = new_value
    start, end = arg_address & ~7, (arg_address+len(old_value)+7) & ~7
    block = bytearray(old[start-gate.BASE:end-gate.BASE])
    block[arg_address-start:arg_address-start+len(new_value)] = new_value
    expected_records = [f'03_{start+i:016x}_{int.from_bytes(block[i:i+8], "little"):016x}\n'.encode()
                        for i in range(0, len(block), 8)]
    assert len(expected_records) == 6
    payload = slice(gate.PAYLOAD_BASE-gate.BASE, gate.PAYLOAD_BASE-gate.BASE+gate.PAYLOAD_BYTES)
    kernel_sha = hashlib.sha256(old[payload]).hexdigest()
    assert kernel_sha == package['binary']['sha256']
    rootfs_offset = int(package['rootfs_blob_offset_in_binary'], 16)
    rootfs = slice(payload.start+rootfs_offset, payload.start+rootfs_offset+package['rootfs_blob']['bytes'])
    rootfs_sha = hashlib.sha256(old[rootfs]).hexdigest()
    assert rootfs_sha == package['rootfs_blob']['sha256']
    OUT.mkdir()
    (OUT/'original.dtb').write_bytes(original_dtb)
    (OUT/'mem46.dtb').write_bytes(expected_dtb)
    command = [sys.executable, str(gate.HELPER), str(SOURCE), str(TARGET),
               '--old', old_value.decode(), '--new', new_value.decode()]
    with (OUT/'helper.log').open('wb') as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    target_guard = load_write_bound(TARGET)
    # Streaming reversal: discard the six exact inserted records only; hash all
    # surviving bytes and compare every original record without a reverse file.
    reverse, original = hashlib.sha256(), hashlib.sha256()
    inserted, source_records, target_records = False, 0, 0
    with SOURCE.open('rb') as left, TARGET.open('rb') as right:
        for a in left:
            source_records += 1
            original.update(a)
            b = right.readline()
            target_records += 1
            if a != b:
                assert not inserted and a.strip() == b'02_0000000000200008_0000000000000000'
                inserted = True
                patch = [b]+[right.readline() for _ in range(5)]
                assert patch == expected_records
                b = right.readline()
                target_records += 6
            assert b == a
            reverse.update(b)
        assert not right.read(1)
    assert inserted and reverse.hexdigest() == original.hexdigest() == SOURCE_SHA
    new, _ = gate.reconstruct(TARGET)
    differences = [i for i, (a, b) in enumerate(zip(old, new)) if a != b]
    expected = [arg_address-gate.BASE+i for i, (a, b) in enumerate(zip(old_value, new_value)) if a != b]
    assert differences == expected and len(differences) == 7
    assert bytes(new[begin:begin+tree['total']]) == expected_dtb
    assert old[payload] == new[payload] and old[rootfs] == new[rootfs]
    capped_tree = gate.parse_fdt(bytes(expected_dtb))
    assert capped_tree['total'] == tree['total'] and capped_tree['nodes'] == tree['nodes']
    assert capped_tree['reservations'] == tree['reservations']
    for a, b in zip(tree['properties'], capped_tree['properties']):
        if a['name'] == 'bootargs' and a['node'] == '/chosen':
            assert b['bytes'] == 49 and b['data'] == new_value+b'\0'
        else:
            assert a == b
    rounded = (tree['total']+7) & ~7
    assert gate.DTB_ADDRESS+rounded <= gate.BASE+gate.OWNED_BYTES
    assert gate.NEXT_ARG1+rounded <= gate.BASE+gate.OWNED_BYTES
    assert source_binding == record(SOURCE)
    result = dict(state='retention-kernel46-offline-verified-no-target-execution',
        purpose='Bounded46MiB copy of exact c7 retention kernel27 with accepted rootfs; future capability-present probe only',
        source_nbf=source_binding, nbf=record(TARGET), package_manifest=record(package_path),
        helper=record(gate.HELPER), helper_command=command, helper_log=record(OUT/'helper.log'),
        helper_tests=dict(command='python3 -B -m unittest discover -s research/embedded46-20261120 -p test_build_pair.py -v', passed=7),
        reused_parser=record(ROOT/'research/embedded46-20261120/build_pair.py'),
        reused_load_guard=record(ROOT/'research/embedded46-20261120/verify_pair.py'),
        prepare_source=record(Path(__file__)), source_inventory=inventory,
        original_dtb=record(OUT/'original.dtb'), capped_dtb=record(OUT/'mem46.dtb'),
        bootargs=dict(address=hex(arg_address), property_bytes=49, old=old_value.decode(), new=new_value.decode(),
                      only_nominal_changed_addresses=[hex(gate.BASE+i) for i in differences]),
        record_proof=dict(source_records=source_records, target_records=target_records,
            inserted_records=6, every_original_record_byte_identical=True,
            inserted_block=[b.decode().rstrip('\n') for b in expected_records],
            streamed_exact_reverse_sha256=reverse.hexdigest(), reverse_image_written=False),
        kernel=dict(base=hex(gate.PAYLOAD_BASE), bytes=gate.PAYLOAD_BYTES, sha256=kernel_sha, preserved=True),
        rootfs=dict(kernel_offset=hex(rootfs_offset), bytes=package['rootfs_blob']['bytes'],
            sha256=rootfs_sha, cpio_sha256=package['accepted_rootfs_cpio_sha256'], preserved=True),
        source_load_guard=source_guard, capped_load_guard=target_guard,
        dtb_bounds=dict(declared_bytes=tree['total'], rounded_copy_bytes=rounded,
            source_begin=hex(gate.DTB_ADDRESS), source_end_exclusive=hex(gate.DTB_ADDRESS+rounded),
            runtime_begin=hex(gate.NEXT_ARG1), runtime_end_exclusive=hex(gate.NEXT_ARG1+rounded),
            owned_end_exclusive=hex(gate.BASE+gate.OWNED_BYTES), all_initial_copy_bytes_within_owned_buffer=True),
        runtime_destination_evidence=record(boot_log), prior_memory_enforcement_proof=record(prior_proof),
        expected_runtime_bounds=dict(allocation_bytes=gate.OWNED_BYTES, memory_kib=47104,
            notice='Memory limited to 46MB', dma32_last_byte='0x82dfffff', next_arg1='0x82200000'),
        limits=['No board execution, kernel/rootfs build, runner change or performance claim.',
            'New capped-image runtime bound and capability-present retention ABI remain unverified until a complete fresh probe boot.',
            'Kernel/rootfs/code addresses and all original NBF records are preserved; memory-node reg still advertises64MiB, constrained by Linux mem=46M.',
            'Initial DTB copy bounds are source/log-derived, not observation of the new image runtime or a proof of earlier fault causation.'])
    text = json.dumps(result, indent=2)+'\n'
    (HERE/'manifest.json').write_text(text)
    (OUT/'manifest.json').write_text(text)
    print(json.dumps({key: result[key] for key in ('state', 'source_nbf', 'nbf', 'record_proof', 'capped_load_guard')}, indent=2))


if __name__ == '__main__':
    main()
