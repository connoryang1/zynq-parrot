"""Test admitted analysis using synthetic acquisitions only, never primary data."""
import json
from pathlib import Path
import random
import re
import unittest
from unittest import mock

import analyze_admitted_matrix as module
import compare_scheduler_pipe_hint_mode14 as comparator
import test_audit_admitted_matrix as fixtures


class AdmittedAnalysisTests(unittest.TestCase):
    write = staticmethod(fixtures.MatrixAdmissionTests.write)
    guest_fixture = fixtures.MatrixAdmissionTests.guest_fixture
    first_log = fixtures.MatrixAdmissionTests.first_log
    modify_session = fixtures.MatrixAdmissionTests.modify_session

    def setUp(self):
        fixtures.MatrixAdmissionTests.setUp(self)
        self.accepted = self.root / 'accepted-audit.json'
        mock.patch.object(module, 'BOOTSTRAP_SAMPLES', 100).start()
        mock.patch.object(comparator, 'EMBEDDED46_BASELINE_SHA', self.admission['baseline_nbf_sha256']).start()
        mock.patch.object(comparator, 'EMBEDDED46_CONTROL_SHA', self.admission['control_nbf_sha256']).start()
        mock.patch.object(comparator, 'verify_reviewed_images', return_value={'parser_fixture': True}).start()

    def costs(self, enabled, disabled):
        for index, session_path in enumerate(self.sessions):
            image = self.admission['reservation_plan'][index]['image']
            for cell in json.loads(session_path.read_text())['plan']:
                log = Path(cell['log'])
                def substitute(match):
                    repeat, on = int(match[2]), int(match[4])
                    value = (enabled if on else disabled)(image, index, repeat)
                    return match[1] + str(value)
                log.write_text(re.sub(r'(PIPE_HINT_WHOLE repeat=(\d+) order=(\d+) enabled=([01]) cycles=)\d+',
                                      substitute, log.read_text()))

    def create_audit(self):
        self.write(self.accepted, module.admission_audit.audit(self.acquisition_path))

    def analyze(self):
        return module.analyze_admitted(self.accepted)

    def test_four_fixed_calls_preserve_primary_and_every_boot_absolute_cells(self):
        self.costs(lambda image,i,r: 10000 if image=='A' else 11000,
                   lambda image,i,r: 10000 if image=='A' else 13000)
        self.create_audit()
        with mock.patch.object(module, 'compare', wraps=module.compare) as compare:
            result = self.analyze()
        self.assertEqual(compare.call_count, 4)
        self.assertEqual(result['workload_order'], list(module.WORKLOADS))
        self.assertEqual(set(result['workloads']), set(module.WORKLOADS))
        for call in compare.call_args_list:
            self.assertEqual(call.kwargs, dict(bootstrap_samples=100, image_pair='embedded46'))
            self.assertEqual([len(paths) for paths in call.args], [2, 2])
        for workload, report in result['workloads'].items():
            primary = report['unchanged_primary_comparison']
            self.assertEqual(primary['primary_whole_cell_control_minus_baseline']['saved_cycles_per_cell'], 2000)
            crosscheck = report['absolute_whole_crosschecks']
            cost = crosscheck['absolute_cost_control_minus_baseline']['absolute_enabled_cycles_per_cell']
            self.assertEqual(cost, dict(control_minus_baseline=1000, hierarchical_95pct_ci=[1000, 1000]))
            decisions = crosscheck['decision_crosschecks']
            self.assertTrue(decisions['primary_paired_benefit_ci_above_zero'])
            self.assertTrue(decisions['positive_primary_with_absolute_enabled_regression_or_uncertainty'])
            self.assertFalse(decisions['eligible_for_carryover_and_drift_review'])
            self.assertFalse(decisions['kernel_optimization_claim_established'])
            self.assertTrue(decisions['carryover_and_drift_review_required'])
            for arm in ('baseline_boots', 'control_boots'):
                for boot in crosscheck[arm]:
                    self.assertEqual(len(boot['whole_cells_in_acquisition_order']), 8)
                    self.assertEqual(len(boot['enabled_cycles']), 4)
                    self.assertEqual(len(boot['disabled_cycles']), 4)
                    self.assertEqual(boot['eight_cell_sum_cycles'],
                                     boot['enabled_sum_cycles'] + boot['disabled_sum_cycles'])
                    self.assertEqual(boot['eight_cell_sum_cycles'], sum(row['cycles'] for row in boot['whole_cells_in_acquisition_order']))
                    self.assertEqual(boot['enabled_order_by_repeat'], [1,0,1,0])
                    self.assertEqual(len(boot['resources']['rows']), 8)
                    self.assertEqual(boot['trigger_accounting']['early_wake_opportunities'], 388)
            self.assertEqual([b['eight_cell_sum_cycles'] for b in crosscheck['baseline_boots']], [80000,80000])
            self.assertEqual([b['eight_cell_sum_cycles'] for b in crosscheck['control_boots']], [96000,96000])
        self.assertFalse(any('pooled' in key for key in result))

    def test_absolute_improvement_still_requires_carryover_review(self):
        self.costs(lambda image,i,r: 10000 if image=='A' else 9000,
                   lambda image,i,r: 12000)
        self.create_audit()
        result = self.analyze()
        for report in result['workloads'].values():
            check = report['absolute_whole_crosschecks']['decision_crosschecks']
            self.assertTrue(check['eligible_for_carryover_and_drift_review'])
            self.assertTrue(check['carryover_and_drift_review_required'])
            self.assertFalse(check['kernel_optimization_claim_established'])

    def test_disabled_cost_increase_alone_cannot_support_an_enabled_cost_claim(self):
        self.costs(lambda image,i,r: 10000,
                   lambda image,i,r: 10000 if image=='A' else 12000)
        self.create_audit()
        for report in self.analyze()['workloads'].values():
            check = report['absolute_whole_crosschecks']['decision_crosschecks']
            self.assertTrue(check['primary_paired_benefit_ci_above_zero'])
            self.assertEqual(check['absolute_enabled_check'], 'no-absolute-enabled-reduction')
            self.assertTrue(check['positive_primary_without_supported_absolute_enabled_reduction'])
            self.assertFalse(check['eligible_for_carryover_and_drift_review'])
            self.assertFalse(check['kernel_optimization_claim_established'])

    def test_between_boot_uncertainty_survives_constant_within_boot_costs(self):
        self.costs(lambda image,i,r: (10000 if i<4 else 16000) if image=='A' else 13000,
                   lambda image,i,r: (12000 if i<4 else 18000) if image=='A' else 16000)
        self.create_audit()
        result = self.analyze()
        for report in result['workloads'].values():
            crosscheck = report['absolute_whole_crosschecks']
            absolute = crosscheck['absolute_cost_control_minus_baseline']['absolute_enabled_cycles_per_cell']
            self.assertEqual(absolute['control_minus_baseline'], 0)
            self.assertEqual(absolute['hierarchical_95pct_ci'], [-3000,3000])
            self.assertEqual(crosscheck['decision_crosschecks']['absolute_enabled_check'], 'absolute-enabled-uncertain')
            self.assertTrue(crosscheck['decision_crosschecks']['primary_paired_benefit_ci_above_zero'])
            self.assertTrue(crosscheck['decision_crosschecks']['positive_primary_with_absolute_enabled_regression_or_uncertainty'])
            self.assertFalse(crosscheck['decision_crosschecks']['eligible_for_carryover_and_drift_review'])

    def test_paired_resampling_keeps_enabled_disabled_and_total_jointly_linked(self):
        self.costs(lambda image,i,r: 10000 + 1000*r + (200 if image=='B' else 0),
                   lambda image,i,r: 20000 - 1000*r - (200 if image=='B' else 0))
        self.create_audit()
        report = self.analyze()['workloads']['lookup']
        primary = report['unchanged_primary_comparison']
        strata = module.absolute_strata(primary['baseline']['boots'])
        rng, enabled_samples = random.Random(12345), set()
        for _ in range(100):
            draw = module._draw(rng, strata)
            enabled_samples.add(draw['absolute_enabled_cycles_per_cell'])
            self.assertEqual(draw['absolute_enabled_cycles_per_cell'] + draw['absolute_disabled_cycles_per_cell'],
                             draw['absolute_total_cycles_per_pair'])
            self.assertEqual(draw['absolute_disabled_cycles_per_cell'] - draw['absolute_enabled_cycles_per_cell'],
                             draw['whole_cycles'])
        self.assertGreater(len(enabled_samples), 1)  # Within-boot pairs are sampled.
        total = report['absolute_whole_crosschecks']['absolute_cost_control_minus_baseline']['absolute_total_cycles_per_pair']
        self.assertEqual(total, dict(control_minus_baseline=0, hierarchical_95pct_ci=[0,0]))

    def test_audit_state_extra_workload_or_mutated_audit_is_rejected_before_contrasts(self):
        self.create_audit()
        original = self.accepted.read_text()
        cases = (
            lambda data: data.update(state='not admitted'),
            lambda data: data['comparator_inputs'].update(deflate=data['comparator_inputs']['scan']),
            lambda data: data['comparator_inputs'].pop('chase'),
            lambda data: data.update(unaudited_extra='not present in regenerated gate'),
            lambda data: data['comparator_inputs']['scan']['baseline'].pop(),
        )
        for change in cases:
            with self.subTest(change=change):
                data = json.loads(original)
                change(data)
                self.write(self.accepted, data)
                with mock.patch.object(module, 'compare') as compare, self.assertRaises(ValueError):
                    self.analyze()
                compare.assert_not_called()
        self.accepted.write_text(original)

    def test_mutated_log_and_source_binding_are_rejected(self):
        self.create_audit()
        original = self.accepted.read_text()
        data = json.loads(original)
        source = next(iter(data['validator_sources'].values()))
        source['sha256'] = '0' * 64
        self.write(self.accepted, data)
        with mock.patch.object(module, 'compare') as compare, self.assertRaisesRegex(ValueError, 'binding changed'):
            self.analyze()
        compare.assert_not_called()
        self.accepted.write_text(original)
        log = self.first_log()
        log.write_text(log.read_text() + 'changed after audit\n')
        with mock.patch.object(module, 'compare') as compare, self.assertRaisesRegex(ValueError, 'binding changed'):
            self.analyze()
        compare.assert_not_called()

    def test_mutation_during_analysis_cannot_write_accepted_output(self):
        self.create_audit()
        output = self.root / 'analysis.json'
        original_compare = module.compare
        calls = []
        def change_input(*args, **kwargs):
            result = original_compare(*args, **kwargs)
            calls.append(1)
            if len(calls) == 4:
                self.acquisition_path.write_text(self.acquisition_path.read_text() + ' ')
            return result
        with mock.patch.object(module, 'compare', side_effect=change_input), self.assertRaisesRegex(SystemExit, 'binding changed'):
            module.main(['--audit', str(self.accepted), '--output', str(output)])
        self.assertFalse(output.exists())

    def test_cli_has_no_protocol_workload_or_bootstrap_overrides_and_never_overwrites(self):
        self.create_audit()
        output = self.root / 'analysis.json'
        output.write_text('existing evidence')
        with self.assertRaisesRegex(SystemExit, 'replace analysis'):
            module.main(['--audit', str(self.accepted), '--output', str(output)])
        self.assertEqual(output.read_text(), 'existing evidence')
        with self.assertRaises(SystemExit):
            module.main(['--audit', str(self.accepted), '--output', str(output), '--bootstrap-samples', '1'])


if __name__ == '__main__':
    unittest.main()
