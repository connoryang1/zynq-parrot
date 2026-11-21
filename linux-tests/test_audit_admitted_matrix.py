"""Audit a synthetic complete acquisition without board calls or primary data.

Fixture-only hashes stand in for large immutable delivery artifacts. The
actual fixed admission pin is separately checked; no override is exposed by
the audit CLI.
"""
import base64
import copy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import audit_admitted_matrix as module


def digest(data):
    return hashlib.sha256(data).hexdigest()


class MatrixAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='matrix-audit-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.admission = copy.deepcopy(json.loads(module.ADMISSION.read_text()))
        self.elf = b'parser fixture only; never executed'
        self.admission['elf_sha256'] = digest(self.elf)
        encoded = base64.b64encode(gzip.compress(self.elf, mtime=0)).decode()
        guest = module.GUEST_ELF
        self.transfer = self.root / 'fixture.transfer'
        self.transfer.write_text(f": > {guest}.b64\necho '{encoded}' >> {guest}.b64\n"
                                 f'base64 -d {guest}.b64 > {guest}.gz\n'
                                 f'/bin/busybox gunzip -c {guest}.gz > {guest}\nchmod +x {guest}\n')
        self.admission['transfer_sha256'] = module.sha(self.transfer)
        self.images = {}
        for image, key in (('A', 'baseline_nbf_sha256'), ('B', 'control_nbf_sha256')):
            path = self.root / ('fixture-' + image + '.nbf')
            path.write_text('nonexecuted NBF fixture ' + image)
            self.images[image] = path
            self.admission[key] = module.sha(path)
        self.admission_path = self.root / 'admission.json'
        self.write(self.admission_path, self.admission)
        self.sources = {key: ('fixture frozen bytes: ' + key).encode() for key in module.HOST_SOURCES}
        self.source_hashes = {key: digest(data) for key, data in self.sources.items()}
        self.acquisition_path = self.root / 'acquisition.json'
        self.acquisition = dict(created_utc='2026-11-20T00:00:00+00:00',
                                admission_sha256=module.sha(self.admission_path),
                                host_sources=self.source_hashes, visits=[])
        self.sessions = []
        for i, scheduled in enumerate(self.admission['reservation_plan']):
            directory = self.root / scheduled['label']
            directory.mkdir()
            for relative, data in self.sources.items():
                path = directory / 'host-sources' / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            start = datetime(2026, 11, 20, 1, i, tzinfo=timezone.utc)
            session = dict(state='complete', reservation=module.LOCK, all_three_acknowledged=True,
                           host='mock-host-never-contacted', started_utc=start.isoformat(),
                           released_utc=(start + timedelta(seconds=30)).isoformat(),
                           host_source_sha256=self.source_hashes, plan=[])
            for index, workload in enumerate(scheduled['workloads']):
                log = directory / f'{index}-{workload}32-futex-early.log'
                cell = dict(nbf=str(self.images[scheduled['image']]), transfer=str(self.transfer),
                            elf_sha256=self.admission['elf_sha256'], log=str(log),
                            host=session['host'], control_sha256=self.admission['control_program_sha256'],
                            bitstream_sha256=self.admission['bitstream_sha256'],
                            loops=64, repeats=4, warmup=32, policy='futex-early', sync='futex',
                            profile='plain', working_set_kib=32, workload=workload,
                            zlib_library=None, embedded_zlib_library=False, retention_probe=None,
                            legacy_no_terminal_handshake=False, legacy_four_arg_cli=False, runtime_ms=3600000)
                session['plan'].append(cell)
                self.guest_fixture(log, cell, scheduled['label'])
                if i >= 3:
                    log.write_text(log.read_text() + 'BOARD_RUNNER_SOURCE_SHA256=' + module.HELPER_NEW_SHA + '\n')
            path = directory / 'session.json'
            self.write(path, session)
            self.sessions.append(path)
            self.acquisition['visits'].append(dict(label=scheduled['label'], session_manifest=str(path)))
        self.write(self.acquisition_path, self.acquisition)
        installation = self.root / 'helper-installation.json'
        self.write(installation, dict(verified_utc='2026-11-20T01:02:45+00:00',
                                     before_sha256=module.HELPER_OLD_SHA, after_sha256=module.HELPER_NEW_SHA,
                                     active_programs=[], reservation=module.LOCK, atomic_replace=True,
                                     remote_helper_path=module.REMOTE_HELPER))
        self.acquisition['board_helper_protocol'] = dict(
            review_sha256=module.HELPER_REVIEW_SHA, installation=module.artifact(installation),
            visit_versions={visit['label']: module.HELPER_OLD_SHA if i<3 else module.HELPER_NEW_SHA
                            for i,visit in enumerate(self.admission['reservation_plan'])})
        self.write(self.acquisition_path, self.acquisition)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(module, 'ADMISSION', self.admission_path).start()
        mock.patch.object(module, 'ADMISSION_SHA', module.sha(self.admission_path)).start()
        mock.patch.object(module, 'HOST_SOURCES', self.source_hashes).start()
        self.image_gate = mock.patch.object(module, 'verify_reviewed_images',
                                            return_value={'parser_fixture': True}).start()

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data, indent=2) + '\n')

    def modify_session(self, index, change):
        data = json.loads(self.sessions[index].read_text())
        change(data)
        self.write(self.sessions[index], data)

    def first_log(self, index=0):
        return Path(json.loads(self.sessions[index].read_text())['plan'][0]['log'])

    def guest_fixture(self, path, cell, label):
        lines = ['INFO: ps.cpp: allocating owned DRAM buffer with size 48234496',
                 'bsg_zynq_pl: allocate_dram() called with size 48234496 bytes --> fixture',
                 'Domain0 Next Arg1 : 0x0000000082200000',
                 f'[    0.000000] Linux version 6.6.0 PARSER_FIXTURE_{label}_{cell["workload"]}',
                 '[    0.000000] Memory limited to 46MB',
                 '[    0.000000] DMA32 [mem 0x80000000-0x82dfffff]',
                 '[    0.000000] Kernel command line: console=hvc0 loglevel=8 rdinit=/bin/sh mem=46M',
                 '[    0.000000] Memory: 20000K/47104K available (parser fixture)',
                 self.admission['elf_sha256'] + '  ' + module.GUEST_ELF,
                 'PIPE_HINT_CONFIG loops=64 repeats=4 warmup=32 configured_entries=32 '
                 'policy=futex-early sync=futex profile=plain working_set_kib=32 '
                 f'workload={cell["workload"]} terminal_handshake=1',
                 self.admission['scope_marker']]
        for repeat in range(4):
            for order in range(2):
                enabled = (repeat & 1) ^ order
                key = f'repeat={repeat} order={order} enabled={enabled}'
                lines += [f'PIPE_HINT_RESULT {key} cycles=5000 loops=64',
                          f'PIPE_HINT_WHOLE {key} cycles=10000 loops=64',
                          f'PIPE_HINT_RESOURCE {key} minor_faults=20 major_faults=0 '
                          'user_us=2 system_us=3 voluntary_switches=4 involuntary_switches=0']
        after = 1 | (32 << 4) | (32 << 13) | (128 << 22) | (255 << 38) | (511 << 55)
        lines += [f'PIPE_HINT_STATUS before=0x0000000000000201 after=0x{after:016x} '
                  'configured_entries=32 dropped=0', 'PIPE_HINT_PASS', 'CORE PASS', 'BSG PASS']
        path.write_text('\n'.join(lines) + '\n')
        command = f'{module.GUEST_ELF} 64 4 futex-early 32 futex plain 32'
        if cell['workload'] != 'scan':
            command += ' ' + cell['workload']
        self.write(path.with_suffix('.log.status.json'), dict(
            status='PASS', runner_exit=0, loops=64, repeats=4, warmup=32,
            policy='futex-early', sync='futex', profile='plain', working_set_kib=32,
            workload=cell['workload'], terminal_handshake=1, legacy_four_arg_cli=False,
            command=command, nbf_sha256=module.sha(Path(cell['nbf'])),
            transfer_sha256=self.admission['transfer_sha256'], elf_sha256=self.admission['elf_sha256'],
            control_program_sha256=self.admission['control_program_sha256'],
            bitstream_sha256=self.admission['bitstream_sha256']))

    def audit(self):
        return module.audit(self.acquisition_path)

    def test_complete_matrix_is_hash_bound_without_effects_and_status_bytes_may_repeat(self):
        result = self.audit()
        self.assertEqual(len(result['logs']), 16)
        self.assertEqual(len(result['sessions']), 8)
        self.assertEqual(result['state'], 'protocol-accepted; image contrasts not calculated')
        for workload, paths in result['comparator_inputs'].items():
            self.assertEqual(len(paths['baseline']), 2)
            self.assertEqual(len(paths['control']), 2)
        # Identical statuses across repeated same-image/workload boots are
        # legitimate; they contain no run timestamps or timing rows.
        a = self.first_log(0).with_suffix('.log.status.json')
        b = Path(json.loads(self.sessions[7].read_text())['plan'][1]['log']).with_suffix('.log.status.json')
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertNotEqual(a.stat().st_ino, b.stat().st_ino)
        self.assertNotIn('primary_whole_cell_control_minus_baseline', result)
        self.assertIn('not all UCE', result['limitations'][0])
        self.assertEqual(result['acquisition']['sha256'], module.sha(self.acquisition_path))
        self.assertEqual(result['sessions'][2]['board_helper_sha256'], module.HELPER_OLD_SHA)
        self.assertEqual(result['sessions'][3]['board_helper_sha256'], module.HELPER_NEW_SHA)
        self.image_gate.assert_called_once_with('embedded46')

    def test_incomplete_or_noncomplete_sessions_fail_before_guest_logs_are_parsed(self):
        original = self.acquisition_path.read_text()
        self.acquisition['visits'].pop()
        self.write(self.acquisition_path, self.acquisition)
        with mock.patch.object(module, '_load') as load, self.assertRaisesRegex(ValueError, 'eight visits'):
            self.audit()
        load.assert_not_called()
        self.acquisition_path.write_text(original)
        self.modify_session(7, lambda s: s.update(state='failed'))
        with mock.patch.object(module, '_load') as load, self.assertRaisesRegex(ValueError, 'must be complete'):
            self.audit()
        load.assert_not_called()

    def test_changed_admission_or_freeze_map_is_rejected(self):
        original = self.acquisition_path.read_text()
        for change, error in ((dict(admission_sha256='0' * 64), 'admission mismatch'),
                              (dict(host_sources={}), 'host-eight mismatch')):
            data = json.loads(original)
            data.update(change)
            self.write(self.acquisition_path, data)
            with self.assertRaisesRegex(ValueError, error):
                self.audit()
        self.acquisition_path.write_text(original)
        self.admission_path.write_text(self.admission_path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'fixed admission hash'):
            self.audit()

    def test_order_labels_wrapper_workloads_and_extra_cells_are_rejected(self):
        self.acquisition['visits'][4], self.acquisition['visits'][5] = self.acquisition['visits'][5], self.acquisition['visits'][4]
        self.write(self.acquisition_path, self.acquisition)
        with self.assertRaisesRegex(ValueError, 'label/order'):
            self.audit()
        self.acquisition['visits'][4], self.acquisition['visits'][5] = self.acquisition['visits'][5], self.acquisition['visits'][4]
        self.write(self.acquisition_path, self.acquisition)
        original = self.sessions[4].read_text()
        self.modify_session(4, lambda s: s['plan'].reverse())
        with self.assertRaisesRegex(ValueError, 'workload/boot order'):
            self.audit()
        self.sessions[4].write_text(original)
        self.modify_session(4, lambda s: s['plan'].append(s['plan'][0]))
        with self.assertRaisesRegex(ValueError, 'exactly two'):
            self.audit()

    def test_overlap_reversed_time_and_naive_timezone_fail(self):
        original = self.sessions[1].read_text()
        for changes in (dict(started_utc='2026-11-20T01:00:15+00:00'),
                        dict(released_utc='2026-11-20T00:00:00+00:00'),
                        dict(started_utc='2026-11-20T01:01:00')):
            self.modify_session(1, lambda s: s.update(changes))
            with self.assertRaisesRegex(ValueError, 'chronology|timezone'):
                self.audit()
            self.sessions[1].write_text(original)

    def test_acknowledgments_lock_and_host_changes_fail(self):
        original = self.sessions[2].read_text()
        for changes in (dict(all_three_acknowledged=False), dict(reservation='/tmp/other.lock'), dict(host='other')):
            self.modify_session(2, lambda s: s.update(changes))
            with self.assertRaisesRegex(ValueError, 'reservation|host mismatch'):
                self.audit()
            self.sessions[2].write_text(original)

    def test_frozen_metadata_and_actual_snapshot_bytes_are_both_required(self):
        self.modify_session(0, lambda s: s.update(host_source_sha256={}))
        with self.assertRaisesRegex(ValueError, 'host-eight mismatch'):
            self.audit()
        self.modify_session(0, lambda s: s.update(host_source_sha256=self.source_hashes))
        target = self.sessions[0].parent / 'host-sources' / next(iter(self.sources))
        target.write_bytes(b'different source with unchanged manifest hash')
        with self.assertRaisesRegex(ValueError, 'snapshot bytes'):
            self.audit()

    def test_helper_transition_requires_explicit_review_and_exact_visit_versions(self):
        original = self.acquisition_path.read_text()
        for change in (
                lambda a: a.pop('board_helper_protocol'),
                lambda a: a['board_helper_protocol'].update(review_sha256='0' * 64),
                lambda a: a['board_helper_protocol']['visit_versions'].update({'B1-first': module.HELPER_NEW_SHA}),
                lambda a: a['board_helper_protocol']['visit_versions'].update({'B1-second': module.HELPER_OLD_SHA})):
            data = json.loads(original)
            change(data)
            self.write(self.acquisition_path, data)
            with self.assertRaisesRegex(ValueError, 'board helper'):
                self.audit()
            self.acquisition_path.write_text(original)

    def test_helper_installation_binding_identity_and_boundary_are_checked(self):
        original = self.acquisition_path.read_text()
        record = json.loads(original)['board_helper_protocol']['installation']
        path = Path(record['path'])
        installation = json.loads(path.read_text())
        for changes, error in ((dict(after_sha256=module.HELPER_OLD_SHA), 'identity/reservation'),
                               (dict(active_programs=[123]), 'identity/reservation'),
                               (dict(atomic_replace=False), 'identity/reservation'),
                               (dict(remote_helper_path='/tmp/other'), 'identity/reservation'),
                               (dict(verified_utc='2026-11-20T01:00:00+00:00'), 'transition'),
                               (dict(verified_utc='2026-11-20T01:04:00+00:00'), 'transition')):
            data = dict(installation, **changes)
            self.write(path, data)
            acquisition = json.loads(original)
            acquisition['board_helper_protocol']['installation'] = module.artifact(path)
            self.write(self.acquisition_path, acquisition)
            with self.assertRaisesRegex(ValueError, error):
                self.audit()
        self.write(path, installation)
        self.acquisition_path.write_text(original)
        path.write_text(path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'installation binding'):
            self.audit()

    def test_new_phase_requires_actual_source_marker_after_all_terminals(self):
        log = self.first_log(3)
        original = log.read_text()
        marker = 'BOARD_RUNNER_SOURCE_SHA256=' + module.HELPER_NEW_SHA + '\n'
        for changed in (original.replace(marker, ''), original + marker,
                        original + 'BOARD_RUNNER_SOURCE_SHA256=malformed\n',
                        original.replace(module.HELPER_NEW_SHA, module.HELPER_OLD_SHA),
                        marker + original.replace(marker, '')):
            log.write_text(changed)
            with self.assertRaisesRegex(ValueError, 'helper.*marker'):
                self.audit()
        log.write_text(original)
        legacy = self.first_log(0)
        legacy.write_text(legacy.read_text() + marker)
        with self.assertRaisesRegex(ValueError, 'legacy board helper'):
            self.audit()

    def test_all_wrapper_parameters_identities_and_delivery_are_fixed(self):
        original = self.sessions[0].read_text()
        cases = (('loops', 8), ('repeats', 2), ('warmup', 4), ('working_set_kib', 64),
                 ('profile', 'legs'), ('policy', 'preseed'), ('sync', 'pipe'),
                 ('elf_sha256', 'e' * 64), ('bitstream_sha256', 'f' * 64),
                 ('control_sha256', 'a' * 64), ('legacy_no_terminal_handshake', True),
                 ('embedded_zlib_library', True), ('zlib_library', '/tmp/libz'), ('runtime_ms', 12))
        for key, value in cases:
            with self.subTest(key=key):
                self.modify_session(0, lambda s: s['plan'][0].update({key: value}))
                with self.assertRaisesRegex(ValueError, 'wrapper plan'):
                    self.audit()
                self.sessions[0].write_text(original)

    def test_actual_nbf_and_transfer_bytes_are_required(self):
        self.images['A'].write_text('changed NBF')
        with self.assertRaisesRegex(ValueError, 'actual wrapper nbf hash'):
            self.audit()
        self.images['A'].write_text('nonexecuted NBF fixture A')
        self.transfer.write_text('changed transfer')
        with self.assertRaisesRegex(ValueError, 'actual wrapper transfer hash'):
            self.audit()

    def test_distinct_log_status_and_session_inodes_are_required(self):
        a = self.first_log(0).with_suffix('.log.status.json')
        b = self.first_log(1).with_suffix('.log.status.json')
        b.unlink()
        os.link(a, b)
        with self.assertRaisesRegex(ValueError, 'duplicate status inode'):
            self.audit()

    def test_duplicate_session_inode_and_duplicate_log_content_are_rejected(self):
        first, second = self.sessions[:2]
        original = second.read_bytes()
        second.unlink()
        os.link(first, second)
        with self.assertRaisesRegex(ValueError, 'duplicate session inode'):
            self.audit()
        second.unlink()
        second.write_bytes(original)
        self.first_log(1).write_bytes(self.first_log(0).read_bytes())
        with self.assertRaisesRegex(ValueError, 'duplicate transcript content'):
            self.audit()

    def test_log_location_is_bound_to_its_wrapper_session_and_order(self):
        self.modify_session(0, lambda s: s['plan'][0].update(log=str(self.first_log(1))))
        with self.assertRaisesRegex(ValueError, 'log path/order'):
            self.audit()

    def test_guest_config_identity_command_and_actual_elf_hash_are_required(self):
        log = self.first_log()
        status = log.with_suffix('.log.status.json')
        original_status = status.read_text()
        for changes, error in ((dict(elf_sha256='0' * 64), 'identity'),
                               (dict(command='arbitrary command'), 'guest command'),
                               (dict(zlib_transfer_encoding='embedded-copy-v1'), 'delivery/terminal')):
            data = json.loads(original_status)
            data.update(changes)
            self.write(status, data)
            with self.assertRaisesRegex(ValueError, error):
                self.audit()
            status.write_text(original_status)
        log.write_text(log.read_text().replace(self.admission['elf_sha256'], '0' * 64))
        with self.assertRaisesRegex(ValueError, 'actual guest ELF hash'):
            self.audit()

    def test_internally_consistent_guest_working_set_still_must_match_admission(self):
        log = self.first_log()
        status = log.with_suffix('.log.status.json')
        data = json.loads(status.read_text())
        data['working_set_kib'] = 64
        self.write(status, data)
        log.write_text(log.read_text().replace('working_set_kib=32', 'working_set_kib=64'))
        with self.assertRaisesRegex(ValueError, 'guest configuration differs'):
            self.audit()

    def test_boot_bounds_scope_resources_and_terminal_completion_fail_closed(self):
        log = self.first_log()
        original = log.read_text()
        for before, after in (('/47104K available', '/65536K available'),
                              ('max_polls=4096', 'max_polls=4095'),
                              ('PIPE_HINT_RESOURCE repeat=0 order=0', 'REMOVED_RESOURCE repeat=0 order=0'),
                              ('CORE PASS', 'CORE missing'), ('BSG PASS', 'BSG missing'),
                              ('Linux version 6.6.0', 'Linux version unknown')):
            with self.subTest(before=before):
                log.write_text(original.replace(before, after))
                with self.assertRaises(ValueError):
                    self.audit()
                log.write_text(original)

    def test_runner_failure_and_controller_drop_cannot_be_admitted(self):
        log = self.first_log()
        status = log.with_suffix('.log.status.json')
        original_status = status.read_text()
        for changes in (dict(status='FAIL'), dict(runner_exit=1)):
            data = json.loads(original_status)
            data.update(changes)
            self.write(status, data)
            with self.assertRaises(ValueError):
                self.audit()
            status.write_text(original_status)
        log.write_text(log.read_text().replace('configured_entries=32 dropped=0', 'configured_entries=32 dropped=1'))
        with self.assertRaisesRegex(ValueError, 'drain cleanly'):
            self.audit()

    def test_optional_future_acquisition_fields_are_hash_bound_not_hardcoded(self):
        self.acquisition['future_provenance'] = {'change': 'metadata only'}
        self.acquisition['visits'][0]['session_sha256'] = module.sha(self.sessions[0])
        self.write(self.acquisition_path, self.acquisition)
        self.assertEqual(self.audit()['acquisition']['sha256'], module.sha(self.acquisition_path))
        self.acquisition['visits'][0]['session_sha256'] = '0' * 64
        self.write(self.acquisition_path, self.acquisition)
        with self.assertRaisesRegex(ValueError, 'session hash'):
            self.audit()

    def test_inputs_cannot_change_between_validation_and_manifest_binding(self):
        def change_acquisition(_):
            self.acquisition_path.write_text(self.acquisition_path.read_text() + ' ')
            return {'parser_fixture': True}
        self.image_gate.side_effect = change_acquisition
        with self.assertRaisesRegex(ValueError, 'input changed during audit'):
            self.audit()

    def test_cli_refuses_overwrite_and_failure_produces_no_accepted_manifest(self):
        output = self.root / 'accepted.json'
        self.assertEqual(module.main(['--acquisition', str(self.acquisition_path), '--output', str(output)]), 0)
        with self.assertRaisesRegex(SystemExit, 'replace audit'):
            module.main(['--acquisition', str(self.acquisition_path), '--output', str(output)])
        output.unlink()
        self.acquisition['visits'].pop()
        self.write(self.acquisition_path, self.acquisition)
        with self.assertRaises(SystemExit):
            module.main(['--acquisition', str(self.acquisition_path), '--output', str(output)])
        self.assertFalse(output.exists())


class FixedAdmissionPinTests(unittest.TestCase):
    def test_production_admission_digest_is_the_reviewed_fixed_plan(self):
        self.assertEqual(module.sha(module.ADMISSION), module.ADMISSION_SHA)
        self.assertEqual(len(module.HOST_SOURCES), 8)


if __name__ == '__main__':
    unittest.main()
