"""Exercise review-only copied runners; every console and board call is mocked."""
import json
from unittest import mock
import unittest

import pexpect
import run_scheduler_pipe_hint as runner
import run_resume_workload_session as session
import test_embedded_resume_transfer as old
import test_run_resume_workload_session as old_session
from emit_resume_transfer import commands as gzip_commands


class GzipConsole(old.GuestConsole):
    def sendline(self, command):
        if command == f'/bin/busybox gunzip -c {runner.GUEST_ELF}.gz > {runner.GUEST_ELF}':
            self.copied.add(runner.GUEST_ELF)
        if command == f'/bin/busybox gunzip -c {runner.GUEST_ZLIB}.gz > {runner.GUEST_ZLIB}':
            self.copied.add(runner.GUEST_ZLIB)
        super().sendline(command)


class EmbeddedLibraryTests(unittest.TestCase):
    setUp = old.EmbeddedResumeTransferTests.setUp
    write_transfer = old.EmbeddedResumeTransferTests.write_transfer
    argv = old.EmbeddedResumeTransferTests.argv

    def run_gzip(self, embedded=True, **options):
        self.write_transfer(gzip_commands(self.elf))
        argv = self.argv(library=True) + (['--embedded-zlib-library'] if embedded else [])
        args = runner.parse_args(argv)
        child = GzipConsole(args, **options)
        with mock.patch.object(runner.pexpect, 'spawn', return_value=child), mock.patch.object(
                runner, 'expect_shell_prompt', side_effect=child.prompt):
            try:
                result = runner.main(argv)
            except Exception as error:
                result = error
        status = json.loads(self.log.with_suffix('.log.status.json').read_text())
        return result, child, status

    def test_gzip_elf_and_embedded_library_verify_both_before_execution(self):
        result, child, status = self.run_gzip()
        self.assertEqual(result, 0)
        self.assertEqual(status['status'], 'PASS')
        self.assertEqual(status['zlib_transfer_encoding'], 'embedded-copy-v1')
        self.assertNotIn('embedded_elf_source', status)
        self.assertNotEqual(status.get('transfer_encoding'), 'embedded-copy-v1')
        self.assertEqual(status['zlib_library_sha256'], self.library_sha)
        self.assertEqual(child.sent.count(f'cp /opt/bp-resume/libz.so.1 {runner.GUEST_ZLIB}'), 1)
        self.assertFalse(any(runner.GUEST_ZLIB + '.b64' in command for command in child.sent))
        self.assertIn(f'/bin/busybox gunzip -c {runner.GUEST_ELF}.gz > {runner.GUEST_ELF}', child.sent)
        execute = next(i for i,e in enumerate(child.events) if e[0] == 'execute')
        for destination in (runner.GUEST_ZLIB, runner.GUEST_ELF):
            self.assertLess(child.events.index(('verified', destination)), execute)
        self.assertIn(('core_pass',), child.events)
        self.assertIn(('bsg_pass',), child.events)

    def test_wrong_library_hash_never_transfers_elf_or_executes(self):
        result, child, status = self.run_gzip(library_hash='0' * 64)
        self.assertIsInstance(result, pexpect.TIMEOUT)
        self.assertEqual(status['status'], 'FAIL')
        self.assertNotIn(child.app, child.sent)
        self.assertNotIn(runner.GUEST_ELF, child.copied)
        self.assertFalse(any(e[0] == 'execute' for e in child.events))

    def test_default_gzip_library_encoding_and_commands_are_unchanged(self):
        result, child, status = self.run_gzip(embedded=False)
        self.assertEqual(result, 0)
        self.assertEqual(status['status'], 'PASS')
        self.assertEqual(status['zlib_transfer_encoding'], 'gzip-base64-v1')
        self.assertTrue(any(runner.GUEST_ZLIB + '.b64' in command for command in child.sent))
        self.assertFalse(any(command.startswith('cp /opt/bp-resume/') for command in child.sent))
        self.assertEqual(child.verified, {runner.GUEST_ZLIB, runner.GUEST_ELF})

    def test_flag_does_not_bypass_embedded_elf_library_declaration(self):
        self.write_transfer(runner.embedded_commands(self.elf_sha, 'plain'))
        with mock.patch.object(runner.pexpect, 'spawn') as spawn:
            with self.assertRaisesRegex(SystemExit, 'exact --zlib-library'):
                runner.main(self.argv(library=True) + ['--embedded-zlib-library'])
        spawn.assert_not_called()

    def test_core_and_bsg_remain_mandatory(self):
        for options in ({'core': False}, {'bsg': False}):
            with self.subTest(options=options):
                result, child, status = self.run_gzip(**options)
                self.assertIsInstance(result, Exception)
                self.assertEqual(status['status'], 'FAIL')
                self.assertIn(('app_pass',), child.events)

    def test_flag_requires_host_library_before_spawn_and_default_stays_gzip(self):
        self.write_transfer(gzip_commands(self.elf))
        with mock.patch.object(runner.pexpect, 'spawn') as spawn:
            with self.assertRaisesRegex(SystemExit, 'requires exact --zlib-library'):
                runner.main(self.argv() + ['--embedded-zlib-library'])
        spawn.assert_not_called()
        args = runner.parse_args(self.argv(library=True))
        self.assertFalse(args.embedded_zlib_library)
        self.assertEqual(runner.library_commands(args, None), runner.library_transfer(self.library))
        args.embedded_zlib_library = True
        self.assertEqual(runner.library_commands(args, None), [f'cp /opt/bp-resume/libz.so.1 {runner.GUEST_ZLIB}'])


class EmbeddedLibrarySessionTests(old_session.ResumeWorkloadSessionTests):
    def test_optional_flag_is_forwarded_and_bound_in_session_plan(self):
        library = self.root / 'libz.so.1'
        library.write_bytes(b'exact host library fixture')
        self.assertEqual(session.main(self.argv + ['--zlib-library', str(library),
                                                  '--embedded-zlib-library']), 0)
        self.assertEqual(self.run_guest.call_count, 2)
        for call in self.run_guest.call_args_list:
            self.assertTrue(call[0][0].embedded_zlib_library)
            self.assertEqual(call[0][0].zlib_library, library)
        status = json.loads((self.output / 'session.json').read_text())
        self.assertTrue(all(e['embedded_zlib_library'] for e in status['plan']))
        self.assert_released_unchanged()

    def test_missing_host_library_rejected_before_reservation_or_commands(self):
        with self.assertRaises(SystemExit):
            session.main(self.argv + ['--embedded-zlib-library'])
        self.assertFalse(self.output.exists())
        self.command.assert_not_called()
        self.run_guest.assert_not_called()
        self.recovery.assert_not_called()
        self.assert_released_unchanged()


if __name__ == '__main__':
    unittest.main()
