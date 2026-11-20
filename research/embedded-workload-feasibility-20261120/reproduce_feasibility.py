#!/usr/bin/env python3
"""Reproduce an offline size bound in memory; never create CPIO/gzip/NBF images.

The only existing member eligible for replacement is the exact staged project
smoke executable, and only for a new rdinit=/bin/sh baseline. This script does
not authorize packaging, deployment, runner changes, or target execution.
"""
import gzip
import hashlib
import json
from pathlib import Path
import stat
import sys
import zlib

ROOT = Path('/home/coyang/zynq-parrot-linux-research')
ARTIFACTS = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120')
SDK = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux')
LIMIT = 3303052
CANDIDATE = 'usr/bin/ctxtsw_user_smoke'
SMOKE_SHA = '1f8676bdc62331a7790f61aa0496f5ee76ff92fc411e803ec6184d9bab5160a5'
CPIO_SHA = 'e2f7dbc4d02d0ae99bb66832fe94b4882e19d7c95acd2cc0521299ff6aa73f50'
PAYLOADS = (
    ('plain', ROOT/'linux-tests/out/scheduler_pipe_hint_benchmark_dynamic',
     'e943befa9eed8b9a4258c88c5c822745017c42ef1d5af9f3bc07c56a0eade86a'),
    ('plain_resources', ARTIFACTS/'plain-resources/scheduler_pipe_hint_benchmark_plain_resources_dynamic',
     'ce0a21a67a36f522c46c590cf790b18bc535f09b85e8d8f20fd36e9a591cec70'),
    ('probe', ROOT/'linux-tests/out/icache_retention_probe_dynamic',
     '8f8887579c81e4633ebe445ada38ab7311aae58c21656f4b98a38bbc6ac0c9a2'),
    ('zlib', ROOT/'linux-tests/out/scheduler_pipe_hint_benchmark_zlib_dynamic',
     '407fd9ec2edb0e67cce2e3b7c7049cc3cfa85809189619d99d13dabc51574308'),
    ('libz.so.1', ARTIFACTS/'libz.so.1',
     'e2c082d208dc2c6041fdef01579e1e86a441bb0dbc930e13fe8e2eee9eedc63b'),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def entries(archive):
    offset = 0
    while offset < len(archive):
        if archive[offset] == 0:
            offset += 1
            continue
        if offset % 4 or archive[offset:offset+6] not in (b'070701', b'070702'):
            raise ValueError('unaligned or invalid newc header')
        fields = [int(archive[offset+6+i*8:offset+14+i*8], 16) for i in range(13)]
        name = archive[offset+110:offset+109+fields[11]].decode()
        body = (offset+110+fields[11]+3) & ~3
        end = (body+fields[6]+3) & ~3
        if end > len(archive):
            raise ValueError('truncated newc entry')
        yield name, fields, offset, body, end, archive[body:body+fields[6]]
        offset = end


def member(name, data, inode, mode):
    encoded = name.encode()+b'\0'
    fields = (inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0)
    result = b'070701'+b''.join(('%08x' % value).encode() for value in fields)+encoded
    result += b'\0' * (-len(result) % 4)
    result += data
    return result+b'\0' * (-len(result) % 4)


def measure(name, archive):
    compressed = gzip.compress(archive, compresslevel=9, mtime=0)
    result = dict(scenario=name, cpio_bytes=len(archive), cpio_sha256=digest(archive),
                  gzip_bytes=len(compressed), gzip_sha256=digest(compressed),
                  margin_to_fixed_span=LIMIT-len(compressed))
    assert gzip.decompress(compressed) == archive
    if len(compressed) <= LIMIT:
        padded = compressed+b'\0' * (LIMIT-len(compressed))
        assert len(padded) == LIMIT and gzip.decompress(padded) == archive
        check = zlib.decompressobj(31)
        assert check.decompress(padded) == archive and check.eof
        assert check.unused_data == b'\0' * (LIMIT-len(compressed))
        result.update(padded_bytes=len(padded), padded_sha256=digest(padded),
                      padding_bytes=LIMIT-len(compressed), crc_isize_and_roundtrip_verified=True)
    return result


def main():
    original = (ARTIFACTS/'kernel27/accepted-rootfs.cpio').read_bytes()
    compressed = (ARTIFACTS/'kernel27/accepted-rootfs.cpio.gz').read_bytes()
    assert len(compressed) == LIMIT and digest(original) == CPIO_SHA
    assert gzip.decompress(compressed) == original
    old_entries = list(entries(original))
    selected = [entry for entry in old_entries if entry[0] == CANDIDATE]
    assert len(selected) == 1
    name, fields, header, body, end, old_data = selected[0]
    assert digest(old_data) == SMOKE_SHA and len(old_data) == 676728
    assert stat.S_ISREG(fields[1]) and fields[4] == 1
    assert original[header:header+6] == b'070701'
    staged = SDK/'work/sysroot/usr/bin/ctxtsw_user_smoke'
    assert staged.read_bytes() == old_data
    assert (SDK/'work/buildroot/target/usr/bin/ctxtsw_user_smoke').read_bytes() == old_data

    appendix = member('opt/bp-resume', b'', 1, 0o040755)
    payload_records = []
    for inode, (destination, path, expected) in enumerate(PAYLOADS, 2):
        data = path.read_bytes()
        assert digest(data) == expected, str(path)
        appendix += member('opt/bp-resume/'+destination, data, inode, 0o100755)
        payload_records.append(dict(destination='opt/bp-resume/'+destination,
                                    source=str(path), bytes=len(data), sha256=expected))
    appendix += member('TRAILER!!!', b'', 20, 0)
    assert len(appendix) == 181976

    # Size feasibility only. This fail-closed placeholder is not authorized
    # as a deployed replacement; full /sbin/init still invokes legacy hooks.
    replacement = b'#!/bin/sh\nexit 1\n'
    changed_header = bytearray(original[header:body])
    changed_header[54:62] = ('%08x' % len(replacement)).encode()
    replaced = (original[:header]+changed_header+replacement+
                b'\0' * (-len(replacement) % 4)+original[end:])
    new_entries = list(entries(replaced))
    assert len(new_entries) == len(old_entries)
    for before, after in zip(old_entries, new_entries):
        assert before[0] == after[0]
        if before[0] == CANDIDATE:
            expected_fields = list(before[1])
            expected_fields[6] = len(replacement)
            assert after[1] == expected_fields and after[5] == replacement
        else:
            assert before[1] == after[1] and before[5] == after[5]
            assert original[before[2]:before[4]] == replaced[after[2]:after[4]]
    report = dict(scope='in-memory backup feasibility only; no images written',
                  python=sys.version, zlib_build=zlib.ZLIB_VERSION,
                  zlib_runtime=zlib.ZLIB_RUNTIME_VERSION, payloads=payload_records,
                  candidate=dict(path=name, bytes=len(old_data), sha256=SMOKE_SHA,
                                 cpio_header_offset=header, body_offset=body, end_offset=end),
                  replacement=dict(bytes=len(replacement), sha256=digest(replacement)),
                  measurements=[measure('append_all_five_unchanged', original+appendix),
                                measure('one_smoke_replacement_plus_all_five', replaced+appendix)])
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
