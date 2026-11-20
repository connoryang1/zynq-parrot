"""Test retention telemetry identity and separate complete-cell paired results.

All transcripts are explicit parser fixtures, not FPGA or performance evidence.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from analyze_scheduler_pipe_hint import analyze


def fixture(policy='retention-first', profile='plain', sync='futex', configured=32,
            consumed=0):
    mode = {'retention-rr': 1, 'retention-first': 2}[policy]
    lines = [f'PIPE_HINT_CONFIG loops=10 repeats=4 warmup=2 configured_entries={configured} '
             f'policy={policy} sync={sync} profile={profile} working_set_kib=32 '
             'workload=lookup terminal_handshake=1']
    for repeat in range(4):
        for order in range(2):
            enabled = (repeat & 1) ^ order
            key = f'repeat={repeat} order={order} enabled={enabled}'
            steady = 1000 + repeat * 100 - 100 * enabled
            # Steady work wins while complete execution loses: setup/reset
            # cost must not disappear into the steady paired calculation.
            whole = 10000 + repeat * 100 + 500 * enabled
            raw = (1 << 63) | ((mode | (4 if consumed else 0) | consumed << 16) if enabled else 0)
            lines.append(f'PIPE_HINT_RESULT {key} cycles={steady} loops=10')
            if profile == 'legs':
                lines.append(f'PIPE_HINT_LEGS {key} child_resume=100 parent_resume=200 loops=10')
            lines.append(f'PIPE_HINT_WHOLE {key} cycles={whole} loops=10')
            lines.append(f'PIPE_HINT_RETENTION {key} raw=0x{raw:016x} capability=1 '
                         f'mode={mode if enabled else 0} completed={int(bool(consumed) and enabled)} '
                         f'consumed_fetches={consumed if enabled else 0}')
    prefix = 1 | configured << 4
    lines += [f'PIPE_HINT_STATUS before=0x{prefix:016x} after=0x{prefix:016x} '
              f'configured_entries={configured} dropped=0',
              'PIPE_HINT_PASS', 'CORE PASS', 'BSG PASS']
    identity = 'a' * 64
    runner = dict(status='PASS', loops=10, repeats=4, warmup=2, policy=policy,
                  sync=sync, profile=profile, working_set_kib=32, workload='lookup',
                  terminal_handshake=1, nbf_sha256=identity, transfer_sha256=identity,
                  elf_sha256=identity, control_program_sha256=identity, bitstream_sha256=identity)
    return '\n'.join(lines) + '\n', runner


class SchedulerRetentionAnalyzerTests(unittest.TestCase):
    def parse(self, text, runner):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'run.log'
            p.write_text(text)
            p.with_suffix('.log.status.json').write_text(json.dumps(runner))
            return analyze(p, bootstrap_samples=200)

    def test_modes_transports_profiles_and_zero_use_are_valid_controls(self):
        for policy in ('retention-rr', 'retention-first'):
            for sync, profile in (('pipe', 'plain'), ('futex', 'plain'), ('futex', 'legs')):
                with self.subTest(policy=policy, sync=sync, profile=profile):
                    text, runner = fixture(policy, profile, sync)
                    r = self.parse(text, runner)
                    self.assertEqual(r['metrics']['paired_median_saved_cycles_per_roundtrip'], 10)
                    self.assertEqual(r['whole_cell']['metrics']['paired_median_saved_cycles_per_cell'], -500)
                    self.assertEqual(r['whole_cell']['metrics']['paired_95pct_ci_saved_cycles_per_cell'], [-500, -500])
                    self.assertEqual(len(r['whole_cell']['pairs']), 4)
                    self.assertEqual(len(r['retention_status']['rows']), 8)
                    self.assertTrue(all(x['consumed_fetches'] == 0 for x in r['retention_status']['rows']))
                    self.assertIn('without additional prefetch traffic', r['retention_status']['mechanism'])
                    self.assertIn('not steady-only', r['retention_status']['scope'])

    def test_exact_raw_counts_including_saturation_are_preserved(self):
        for consumed in (1, 17, 65535):
            text, runner = fixture(consumed=consumed)
            result = self.parse(text, runner)
            for row in result['retention_status']['rows']:
                self.assertEqual(row['consumed_fetches'], consumed if row['enabled'] else 0)
                self.assertEqual(row['completed'], row['enabled'])
                self.assertEqual(row['raw'], f"0x{int(row['raw'], 16):016x}")

    def test_whole_cell_has_independent_paired_bootstrap(self):
        text, runner = fixture()
        original = self.parse(text, runner)
        changed = text.replace('PIPE_HINT_WHOLE repeat=0 order=1 enabled=1 cycles=10500',
                               'PIPE_HINT_WHOLE repeat=0 order=1 enabled=1 cycles=20000')
        r = self.parse(changed, runner)
        self.assertEqual(original['metrics'], r['metrics'])
        self.assertEqual(r['whole_cell']['pairs'][0]['saved_cycles_per_cell'], -10000)
        self.assertLess(r['whole_cell']['metrics']['paired_95pct_ci_saved_cycles_per_cell'][0], -500)
        self.assertEqual(r['whole_cell']['metrics']['saved_cycles_by_enabled_order']['1'], -5250)

    def test_missing_duplicate_unmatched_and_out_of_order_rows_rejected(self):
        text, runner = fixture()
        lines = text.splitlines()
        whole = next(x for x in lines if x.startswith('PIPE_HINT_WHOLE'))
        retention = next(x for x in lines if x.startswith('PIPE_HINT_RETENTION'))
        variants = [text.replace(whole + '\n', '', 1), text.replace(retention + '\n', '', 1),
                    text.replace(whole + '\n', whole + '\n' + whole + '\n', 1),
                    text.replace(retention + '\n', retention + '\n' + retention + '\n', 1),
                    text.replace(whole + '\n' + retention, retention + '\n' + whole, 1),
                    text.replace('PIPE_HINT_WHOLE repeat=0 order=0 enabled=0',
                                 'PIPE_HINT_WHOLE repeat=4 order=0 enabled=0'),
                    text.replace('PIPE_HINT_RETENTION repeat=0 order=0 enabled=0',
                                 'PIPE_HINT_RETENTION repeat=0 order=1 enabled=0'),
                    text.replace('PIPE_HINT_RESULT repeat=0 order=0 enabled=0',
                                 'PIPE_HINT_RESULT repeat=0 order=1 enabled=0'),
                    text.replace('PIPE_HINT_PASS', 'PIPE_HINT_HINT enabled=1\nPIPE_HINT_PASS')]
        for bad in variants:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): self.parse(bad, runner)

    def test_raw_fields_policy_capability_and_forbidden_bits_rejected(self):
        text, runner = fixture(consumed=17)
        original = 'raw=0x8000000000110006 capability=1 mode=2 completed=1 consumed_fetches=17'
        self.assertIn(original, text)
        replacements = [
            'raw=0x8000000000110006 capability=1 mode=1 completed=1 consumed_fetches=17',
            'raw=0x8000000000110006 capability=1 mode=2 completed=0 consumed_fetches=17',
            'raw=0x8000000000110006 capability=1 mode=2 completed=1 consumed_fetches=18',
            'raw=0x0000000000110006 capability=0 mode=2 completed=1 consumed_fetches=17',
            'raw=0x8000000000110007 capability=1 mode=3 completed=1 consumed_fetches=17',
            'raw=0x8000000000110005 capability=1 mode=1 completed=1 consumed_fetches=17',
            'raw=0x08000000000110006 capability=1 mode=2 completed=1 consumed_fetches=17',
            'raw=0x8000000000110006 capability=2 mode=2 completed=1 consumed_fetches=17']
        for bit in (3, 15, 32, 62):
            replacements.append(f'raw=0x{0x8000000000110006 | 1 << bit:016x} capability=1 mode=2 completed=1 consumed_fetches=17')
        for replacement in replacements:
            with self.subTest(replacement=replacement):
                with self.assertRaises(ValueError): self.parse(text.replace(original, replacement, 1), runner)
        disabled = 'raw=0x8000000000000000 capability=1 mode=0 completed=0 consumed_fetches=0'
        for stale in ('raw=0x8000000000000004 capability=1 mode=0 completed=1 consumed_fetches=0',
                      'raw=0x8000000000010000 capability=1 mode=0 completed=0 consumed_fetches=1'):
            with self.assertRaises(ValueError): self.parse(text.replace(disabled, stale, 1), runner)

    def test_whole_cycle_containment_and_loop_identity(self):
        text, runner = fixture()
        for replacement in ('cycles=999 loops=10', 'cycles=10000 loops=11'):
            bad = text.replace('PIPE_HINT_WHOLE repeat=0 order=0 enabled=0 cycles=10000 loops=10',
                               'PIPE_HINT_WHOLE repeat=0 order=0 enabled=0 ' + replacement)
            with self.assertRaisesRegex(ValueError, 'whole cell'): self.parse(bad, runner)
        equal = text.replace('PIPE_HINT_WHOLE repeat=0 order=0 enabled=0 cycles=10000 loops=10',
                             'PIPE_HINT_WHOLE repeat=0 order=0 enabled=0 cycles=1000 loops=10')
        self.parse(equal, runner)

    def test_configured_table_is_allowed_but_explicit_activity_is_not(self):
        for configured in (0, 32):
            text, runner = fixture(configured=configured)
            self.parse(text, runner)
        text, runner = fixture()
        for bit in (1, 2, 3, 13, 22, 38, 46, 54, 55):
            status = 0x201 | 1 << bit
            bad = text.replace('after=0x0000000000000201', f'after=0x{status:016x}')
            with self.subTest(bit=bit):
                with self.assertRaises(ValueError): self.parse(bad, runner)
        with self.assertRaises(ValueError): self.parse(text.replace('dropped=0', 'dropped=1'), runner)

    def test_policy_bindings_markers_and_optional_library_identity(self):
        text, runner = fixture()
        for change in ('retention-rr', 'continuous'):
            bad = copy.deepcopy(runner); bad['policy'] = change
            with self.assertRaisesRegex(ValueError, 'policy differ'): self.parse(text, bad)
        legacy_text = text.replace('policy=retention-first', 'policy=continuous')
        bad = copy.deepcopy(runner); bad['policy'] = 'continuous'
        with self.assertRaisesRegex(ValueError, 'retention markers require'): self.parse(legacy_text, bad)
        good = copy.deepcopy(runner); good['zlib_library_sha256'] = 'b' * 64
        self.assertEqual(self.parse(text, good)['identity']['zlib_library_sha256'], 'b' * 64)
        deflate = ('PIPE_HINT_LIBRARY name=zlib version=1.2.13 block_bytes=4096 input_corpus_kib=32\n'
                   + text.replace('workload=lookup', 'workload=deflate'))
        good['workload'] = 'deflate'
        self.assertEqual(self.parse(deflate, good)['identity']['zlib_library_sha256'], 'b' * 64)
        self.assertNotIn('zlib_library_sha256', self.parse(text, runner)['identity'])
        for value in ('b' * 63, 'Z' * 64, None, 42):
            bad = copy.deepcopy(runner); bad['zlib_library_sha256'] = value
            with self.assertRaisesRegex(ValueError, 'zlib_library_sha256'): self.parse(text, bad)
        host = text.replace('PIPE_HINT_', 'PIPE_HINT_HOST_VERIFY_')
        with self.assertRaises(ValueError): self.parse(host, runner)


if __name__ == '__main__': unittest.main()
