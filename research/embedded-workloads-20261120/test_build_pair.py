"""Test archive preservation and fixed-span boundaries without target execution.

Fixtures use small synthetic file bodies. Actual workload and image identities
are checked separately by the offline builder and independent verifier.
"""
import gzip
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import zlib

import build_pair as builder

spec = importlib.util.spec_from_file_location('feasibility', builder.FEASIBILITY)
feasibility = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feasibility)


class EmbeddedArchiveTests(unittest.TestCase):
    def setUp(self):
        self.old_body = b'obsolete fixture smoke executable'
        self.payloads = [(name, ('exact fixture ' + name).encode()) for name in
                         ('plain', 'plain_resources', 'probe', 'zlib', 'libz.so.1')]
        patch = mock.patch.object(builder, 'SMOKE_SHA', builder.digest(self.old_body))
        patch.start()
        self.addCleanup(patch.stop)

    def archive(self, opt=True, extra=None, smoke_mode=0o100755):
        members = [('.', b'', 0o040755), ('untouched', b'unchanged original member', 0o100640)]
        if opt:
            members.append(('opt', b'', 0o040755))
        members.append((builder.SMOKE, self.old_body, smoke_mode))
        if extra:
            members.append(extra)
        raw = b''.join(feasibility.member(name, data, i + 100, mode)
                       for i, (name, data, mode) in enumerate(members))
        raw += feasibility.member('TRAILER!!!', b'', 999, 0)
        return raw + b'\0' * (-len(raw) % 512)

    def test_only_smoke_body_and_size_change_and_payloads_are_exact(self):
        original = self.archive()
        archive, appendix, proof = builder.build_archive(original, self.payloads, feasibility.member)
        self.assertEqual([row['name'] for row in proof if row['changed']], [builder.SMOKE])
        for row in proof:
            if not row['changed']:
                self.assertEqual(row['original_raw_sha256'], row['resulting_raw_sha256'])
                self.assertEqual(row['original_fields'], row['resulting_fields'])
        entries = list(builder.entries(archive))
        smoke = next(row for row in entries if row['name'] == builder.SMOKE)
        self.assertEqual(smoke['data'], b'#!/bin/sh\nexit 1\n')
        expected = dict(self.payloads)
        appended = list(builder.entries(appendix))
        self.assertEqual([row['name'] for row in appended],
                         ['opt/bp-resume'] + ['opt/bp-resume/' + name for name in expected] + ['TRAILER!!!'])
        for row in appended:
            if row['name'].startswith('opt/bp-resume/'):
                self.assertEqual(row['data'], expected[row['name'].split('/')[-1]])

    def test_missing_parent_is_created_and_encoding_is_deterministic(self):
        original = self.archive(opt=False)
        first = builder.build_archive(original, self.payloads, feasibility.member)
        second = builder.build_archive(original, self.payloads, feasibility.member)
        self.assertEqual(first, second)
        directories = {row['name'] for row in builder.entries(first[1]) if row['fields'][1] == 0o040755}
        self.assertEqual(directories, {'opt', 'opt/bp-resume'})

    def test_refuses_existing_destination_and_non_directory_parent(self):
        for extra in (('opt/bp-resume/plain', b'old', 0o100755),
                      ('opt/bp-resume', b'wrong', 0o100755)):
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):
                    builder.build_archive(self.archive(extra=extra), self.payloads, feasibility.member)

    def test_rejects_wrong_smoke_identity_type_and_payload_set(self):
        with mock.patch.object(builder, 'SMOKE_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'identity/type/link'):
                builder.build_archive(self.archive(), self.payloads, feasibility.member)
        with self.assertRaisesRegex(ValueError, 'identity/type/link'):
            builder.build_archive(self.archive(smoke_mode=0o120777), self.payloads, feasibility.member)
        with self.assertRaisesRegex(ValueError, 'set/order'):
            builder.build_archive(self.archive(), self.payloads[:-1], feasibility.member)

    def test_gzip_crc_isize_and_nul_padding(self):
        archive = self.archive() * 4
        padded, result = builder.compress_fixed(archive)
        self.assertEqual(len(padded), 3303052)
        stream = zlib.decompressobj(31)
        self.assertEqual(stream.decompress(padded), archive)
        self.assertTrue(stream.eof)
        self.assertEqual(stream.unused_data, b'\0' * result['padding_bytes'])
        crc, size = struct.unpack('<II', padded[result['gzip_bytes'] - 8:result['gzip_bytes']])
        self.assertEqual(crc, zlib.crc32(archive) & 0xffffffff)
        self.assertEqual(size, len(archive))
        self.assertEqual(gzip.decompress(padded), archive)
        with mock.patch.object(builder, 'SPAN', 8):
            with self.assertRaisesRegex(ValueError, 'exceeds'):
                builder.compress_fixed(archive)

    def test_replacement_preserves_partial_word_outside_bytes_and_rejects_wrong_old(self):
        with tempfile.TemporaryDirectory() as directory:
            old_gzip = Path(directory) / 'old.gz'
            old_gzip.write_bytes(b'old-gzip-123')
            old = b'PREFIX00' + old_gzip.read_bytes() + b'KEEP-OUTSIDE'
            with mock.patch.object(builder, 'SPAN', 12), mock.patch.object(builder, 'GZIP', old_gzip):
                new = builder.replace_span(old, b'NEW-gzip-123', 8)
                self.assertEqual(new[:8], old[:8])
                self.assertEqual(new[20:], old[20:])
                with self.assertRaisesRegex(ValueError, 'original rootfs'):
                    builder.replace_span(b'wrong' + old[5:], b'NEW-gzip-123', 7)

    def test_rejects_truncated_archive(self):
        archive = self.archive()
        body = next(row for row in builder.entries(archive) if row['name'] == builder.SMOKE)['body']
        with self.assertRaisesRegex(ValueError, 'truncated'):
            list(builder.entries(archive[:body + 3]))


if __name__ == '__main__':
    unittest.main()
