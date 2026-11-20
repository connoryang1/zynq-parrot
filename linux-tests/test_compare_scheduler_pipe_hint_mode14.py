"""Exercise the fixed-image mode14 comparator with explicit parser fixtures.

Synthetic timings test accounting and direction only. The optional real-image
test reads reviewed local artifacts and performs no board operation.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest import mock

import compare_scheduler_pipe_hint_mode14 as module


class Mode14ComparatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mode14-comparator-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = [self.fixture('baseline' + str(i), module.BASELINE_SHA, 100, 100)
                         for i in range(2)]
        self.control = [self.fixture('control' + str(i), module.CONTROL_SHA, 50, 200)
                        for i in range(2)]
        gate = mock.patch.object(module, 'verify_reviewed_images', return_value={'fixture': True})
        self.image_gate = gate.start()
        self.addCleanup(gate.stop)

    def fixture(self, name, nbf, whole_saved, steady_saved):
        path = self.root / (name + '.log')
        lines = [f'[    0.000000] Linux version 6.6.0 PARSER_FIXTURE_{name}',
                 'PIPE_HINT_CONFIG loops=10 repeats=2 warmup=2 configured_entries=16 '
                 'policy=futex-early sync=futex profile=plain working_set_kib=32 '
                 'workload=lookup terminal_handshake=1']
        for repeat in range(2):
            for order in range(2):
                enabled = (repeat & 1) ^ order
                key = f'repeat={repeat} order={order} enabled={enabled}'
                lines += [f'PIPE_HINT_RESULT {key} cycles={1000 - enabled * steady_saved} loops=10',
                          f'PIPE_HINT_WHOLE {key} cycles={10000 - enabled * whole_saved} loops=10',
                          f'PIPE_HINT_RESOURCE {key} minor_faults=20 major_faults=0 '
                          'user_us=2 system_us=3 voluntary_switches=4 involuntary_switches=0']
        triggers = 52 if nbf == module.BASELINE_SHA else 26
        resident = min(511, triggers * 16 - 32)
        after = 1 | (16 << 4) | (16 << 13) | (32 << 22) | (triggers << 38) | (resident << 55)
        lines += [f'PIPE_HINT_STATUS before=0x0000000000000101 after=0x{after:016x} '
                  'configured_entries=16 dropped=0', 'PIPE_HINT_PASS', 'CORE PASS', 'BSG PASS']
        path.write_text('\n'.join(lines) + '\n')
        status = dict(status='PASS', runner_exit=0, loops=10, repeats=2, warmup=2,
                      policy='futex-early', sync='futex', profile='plain', working_set_kib=32,
                      workload='lookup', terminal_handshake=1, nbf_sha256=nbf,
                      transfer_sha256='a' * 64, elf_sha256='b' * 64,
                      control_program_sha256='c' * 64, bitstream_sha256='d' * 64)
        path.with_suffix('.log.status.json').write_text(json.dumps(status))
        return path

    def status(self, path, **changes):
        status = path.with_suffix('.log.status.json')
        data = json.loads(status.read_text())
        data.update(changes)
        status.write_text(json.dumps(data))

    def compare(self, samples=50):
        return module.compare(self.baseline, self.control, samples)

    def test_primary_whole_can_regress_while_secondary_steady_improves(self):
        result = self.compare()
        primary = result['primary_whole_cell_control_minus_baseline']
        secondary = result['secondary_steady_control_minus_baseline']
        self.assertEqual(primary['saved_cycles_per_cell'], -50)
        self.assertEqual(primary['hierarchical_95pct_ci_saved_cycles_per_cell'], [-50, -50])
        self.assertEqual(primary['saved_percentage_points'], -0.5)
        self.assertEqual(secondary['saved_cycles_per_roundtrip'], 10)
        self.assertEqual(secondary['hierarchical_95pct_ci_saved_cycles_per_roundtrip'], [10, 10])
        self.assertIn('Positive', result['effect_direction'])
        boot = result['baseline']['boots'][0]
        self.assertEqual(boot['enabled_order_by_repeat'], [1, 0])
        self.assertEqual(len(boot['resources']['rows']), 4)
        self.assertEqual(boot['identity']['nbf_sha256'], module.BASELINE_SHA)
        self.assertFalse(any('95pct' in key for key in boot['steady_metrics']))
        self.assertFalse(any('95pct' in key for key in boot['whole_cell']['metrics']))
        self.image_gate.assert_called_once_with()

    def test_boot_resampling_retains_between_boot_variation_and_is_repeatable(self):
        self.baseline[1] = self.fixture('baseline-varied', module.BASELINE_SHA, 300, 100)
        self.control[0] = self.fixture('control-varied0', module.CONTROL_SHA, 400, 200)
        self.control[1] = self.fixture('control-varied1', module.CONTROL_SHA, 600, 200)
        result = self.compare(300)
        effect = result['primary_whole_cell_control_minus_baseline']
        self.assertEqual(effect['saved_cycles_per_cell'], 300)
        low, high = effect['hierarchical_95pct_ci_saved_cycles_per_cell']
        self.assertLess(low, 300)
        self.assertGreater(high, 300)
        self.assertEqual(result, self.compare(300))

    def test_requires_two_boots_and_distinct_paths_inodes_and_content(self):
        with self.assertRaisesRegex(ValueError, 'two independent'):
            module.compare(self.baseline[:1], self.control)
        with self.assertRaisesRegex(ValueError, 'distinct transcript paths'):
            module.compare([self.baseline[0]] * 2, self.control)
        linked = self.root / 'hardlink.log'
        os.link(self.baseline[0], linked)
        with self.assertRaisesRegex(ValueError, 'distinct transcript inodes'):
            module.compare([self.baseline[0], linked], self.control)
        shutil.copyfile(self.baseline[0], self.baseline[1])
        with self.assertRaisesRegex(ValueError, 'distinct transcript content'):
            self.compare()

    def test_rejects_every_non_nbf_identity_change_and_wrong_fixed_image(self):
        target = self.control[-1]
        status = target.with_suffix('.log.status.json')
        original = status.read_text()
        for key in ('transfer_sha256', 'elf_sha256', 'control_program_sha256',
                    'bitstream_sha256', 'zlib_library_sha256', 'nbf_sha256'):
            with self.subTest(key=key):
                self.status(target, **{key: 'e' * 64})
                with self.assertRaisesRegex(ValueError, 'identity mismatch|fixed reviewed NBF'):
                    self.compare()
                status.write_text(original)

    def test_rejects_workload_or_other_config_changes(self):
        target = self.control[-1]
        original = target.read_text()
        status = target.with_suffix('.log.status.json')
        original_status = status.read_text()
        for text, changes in (('workload=parse', dict(workload='parse')),
                              ('working_set_kib=64', dict(working_set_kib=64))):
            with self.subTest(text=text):
                key = text.split('=')[0]
                target.write_text(original.replace(key + '=' + str(json.loads(original_status)[key]), text))
                self.status(target, **changes)
                with self.assertRaisesRegex(ValueError, 'configuration mismatch'):
                    self.compare()
                target.write_text(original)
                status.write_text(original_status)

    def test_rejects_missing_whole_resource_or_terminal_rows_and_nonpass(self):
        target = self.control[-1]
        original = target.read_text()
        for marker in ('PIPE_HINT_WHOLE', 'PIPE_HINT_RESOURCE', 'PIPE_HINT_PASS', 'CORE PASS', 'BSG PASS'):
            with self.subTest(marker=marker):
                target.write_text('\n'.join(line for line in original.splitlines()
                                            if not line.startswith(marker)) + '\n')
                with self.assertRaises(ValueError):
                    self.compare()
                target.write_text(original)
        self.status(target, status='FAIL')
        with self.assertRaisesRegex(ValueError, 'not PASS'):
            self.compare()
        self.status(target, status='PASS', runner_exit=1)
        with self.assertRaisesRegex(ValueError, 'runner_exit zero'):
            self.compare()

    def test_requires_one_boot_marker_and_reviewed_policy(self):
        target = self.control[-1]
        original = target.read_text()
        for content in (original.split('\n', 1)[1], original.split('\n', 1)[0] + '\n' + original):
            target.write_text(content)
            with self.assertRaisesRegex(ValueError, 'exactly one fresh'):
                self.compare()
        target.write_text(original)
        after = 1 | (16 << 4) | (16 << 13) | (32 << 22) | (52 << 38) | (511 << 55)
        for path in self.baseline + self.control:
            content = path.read_text().replace('policy=futex-early', 'policy=futex-early-both')
            path.write_text(re.sub(r'after=0x[0-9a-f]{16}', f'after=0x{after:016x}', content))
            self.status(path, policy='futex-early-both')
        with self.assertRaisesRegex(ValueError, 'requires futex-early'):
            self.compare()

    def test_rejects_nonpositive_bootstrap_count(self):
        with self.assertRaisesRegex(ValueError, 'positive'):
            self.compare(0)

    def test_cli_has_no_arbitrary_image_override_and_refuses_output_overwrite(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            module.main(['--baseline', 'a', 'b', '--control', 'c', 'd', '--baseline-nbf', 'other'])
        output = self.root / 'already.json'
        output.write_text('preserved')
        with self.assertRaisesRegex(SystemExit, 'refusing to overwrite'):
            module.main(['--baseline', 'a', 'b', '--control', 'c', 'd', '--output', str(output)])
        self.assertEqual(output.read_text(), 'preserved')


class Mode14ImageGateTests(unittest.TestCase):
    def test_actual_reviewed_pair_when_local_artifacts_are_available(self):
        if not (module.REVIEW / 'manifest.json').is_file():
            self.skipTest('reviewed local artifacts unavailable')
        manifest = json.loads((module.REVIEW / 'manifest.json').read_text())
        if any(not Path(manifest[key]['path']).is_file()
               for key in ('source_nbf', 'candidate_nbf', 'all_modes')):
            self.skipTest('reviewed external NBF/proof artifacts unavailable')
        result = module.verify_reviewed_images()
        self.assertEqual(result['baseline']['sha256'], module.BASELINE_SHA)
        self.assertEqual(result['control']['sha256'], module.CONTROL_SHA)
        self.assertEqual(result['changed_record_line'], 1075385)

    def test_rejects_another_change_or_unreviewed_actual_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, new = root / 'old.nbf', root / 'new.nbf'
            header = b'00_0000000080000000_0000000000000000\n'
            old.write_bytes(header + module.OLD_RECORD)
            new.write_bytes(header + module.NEW_RECORD)
            with mock.patch.object(module, 'RECORD_LINE', 2):
                with self.assertRaisesRegex(ValueError, 'actual NBF SHA256'):
                    module._verify_nbf_pair(old, new)
                new.write_bytes(header.replace(b'0000\n', b'0001\n') + module.NEW_RECORD)
                with self.assertRaisesRegex(ValueError, 'outside the sole'):
                    module._verify_nbf_pair(old, new)
                new.write_bytes(old.read_bytes())
                with self.assertRaisesRegex(ValueError, 'lacks the sole'):
                    module._verify_nbf_pair(old, new)

    def test_rejects_a_changed_review_manifest_before_using_its_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text('{"candidate_nbf": {"path": "unreviewed"}}\n')
            with mock.patch.object(module, 'REVIEW', root):
                with self.assertRaisesRegex(ValueError, 'manifest/proof identity'):
                    module.verify_reviewed_images()


if __name__ == '__main__':
    unittest.main()
