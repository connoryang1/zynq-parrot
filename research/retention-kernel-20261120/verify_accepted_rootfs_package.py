#!/usr/bin/env python3
"""Recheck durable accepted-rootfs package identities without RAM or board access."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('accepted_gate', HERE / 'accepted_rootfs_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def verify_records(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            path = Path(value['path'])
            assert gate.sha(path) == value['sha256'], str(path)
            if 'bytes' in value:
                assert path.stat().st_size == value['bytes'], str(path)
        for child in value.values():
            verify_records(child)
    elif isinstance(value, list):
        for child in value:
            verify_records(child)


def main():
    link = json.loads((gate.EVIDENCE / 'manifest.json').read_text())
    package_path = gate.EVIDENCE / 'package-manifest.json'
    package = json.loads(package_path.read_text())
    original = json.loads((HERE / 'manifest.json').read_text())
    assert link['state'] == 'accepted-rootfs-link-complete'
    assert package['state'] == 'accepted-rootfs-offline-package-verified'
    verify_records(link)
    verify_records(package)
    assert package_path.read_bytes() == (gate.OUT / 'package-manifest.json').read_bytes()
    assert gate.canonical_hashes(original) == original['canonical_before']
    assert gate.preserved_diagnostics() == link['preserved_diagnostic_hashes']
    patch = gate.ROOT / 'linux-tests/kernel-patches/0027-blackparrot-icache-retention-control.patch'
    assert gate.sha(patch) == original['patch_sha256']
    assert link['artifacts']['.config']['sha256'] == original['canonical_before']['.config']
    assert link['artifacts']['kernel/sys.c']['sha256'] == original['normalized_sources']['kernel/sys.c']
    assert link['artifacts']['kernel/sys.o']['sha256'] == original['object']['artifacts']['kernel/sys.o']['sha256']
    assert link['uts_before'] == link['uts_after']
    blob = (gate.EVIDENCE / 'accepted-initramfs_inc_data').read_bytes()
    assert blob == gate.CPIO.with_suffix('.cpio.gz').read_bytes()
    assert gzip.decompress(blob) == gate.CPIO.read_bytes()
    assert hashlib.sha256(gzip.decompress(blob)).hexdigest() == gate.EXPECTED_CPIO
    image = Path(package['binary']['path']).read_bytes()
    offset = int(package['rootfs_blob_offset_in_binary'], 16)
    assert offset == 0xc126b0 and image[offset:offset + len(blob)] == blob
    assert image == Path(package['candidate_reextracted']['path']).read_bytes()
    assert Path(package['reverse_nbf']['path']).read_bytes() == Path(package['source_nbf']['path']).read_bytes()
    assert package['exception_probe'] == {
        'fault_pc': '0xffffffff80020e9e', 'fixup_pc': '0xffffffff80020ea2',
        'type': 3, 'data': '0x1cf', 'error_register': 15, 'zero_register': 14}
    command = [gate.PREFIX + 'objdump', '-d', '--disassemble=bp_icache_retention_probe',
               package['linked_elf']['path']]
    disassembly = subprocess.check_output(command, text=True)
    (gate.EVIDENCE / 'accepted-probe.disassembly.txt').write_text(disassembly)
    assert 'li\ta5,0' in disassembly and 'mv\ta4,a5' in disassembly
    assert '5c102773' in disassembly and 'bnez\ta5' in disassembly
    result = {
        'state': 'PASS', 'scope': 'durable offline identities; no boot or performance acceptance',
        'package_manifest': gate.record(package_path),
        'link_manifest': gate.record(gate.EVIDENCE / 'manifest.json'),
        'driver': gate.record(HERE / 'accepted_rootfs_gate.py'),
        'source_patch': gate.record(patch),
        'baseline_collision_review': gate.record(HERE / 'baseline-csr5c1-review.json'),
        'probe_disassembly': gate.record(gate.EVIDENCE / 'accepted-probe.disassembly.txt'),
        'probe_disassembly_command': command,
        'canonical_inputs_unchanged': True, 'original_diagnostics_unchanged': True,
        'kernel_sys_object_unchanged_from_reviewed_gate': True,
        'accepted_rootfs_compressed_and_uncompressed_exact': True,
        'reverse_splice_byte_exact': True, 'candidate_payload_byte_exact': True}
    rendered = json.dumps(result, indent=2) + '\n'
    (gate.EVIDENCE / 'verification.json').write_text(rendered)
    (gate.OUT / 'verification.json').write_text(rendered)
    print('PASS: durable accepted-rootfs package, probe, patch and preserved-input identities')


if __name__ == '__main__':
    main()
