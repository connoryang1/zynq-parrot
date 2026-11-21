"""Reject common plan/estimand drift without any target operation."""
import copy
import json
from pathlib import Path
import unittest
from validate import validate


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.d = json.loads((Path(__file__).parent / 'cohort-draft.json').read_text())

    def rejected(self, change):
        value = copy.deepcopy(self.d)
        change(value)
        with self.assertRaises(ValueError):
            validate(value, verify_files=False)

    def test_declared_plan_and_real_bindings(self):
        self.assertEqual(validate(self.d)['performance_boots'], 15)

    def test_reordered_boot_or_dropped_boot(self):
        self.rejected(lambda d: d['visits'].reverse())
        self.rejected(lambda d: d['visits'].pop())

    def test_changed_rotation_or_intensity(self):
        self.rejected(lambda d: d['visits'][6]['plan'].update(rotation=0))
        self.rejected(lambda d: d['visits'][1]['plan'].update(loops=128))

    def test_invented_hardware_or_launch(self):
        self.rejected(lambda d: d.update(launchable=True))
        self.rejected(lambda d: d.update(hardware={'i_lines': 1280}))
        self.rejected(lambda d: d['physical_prerequisites'].update(observer_capacity='PASS'))

    def test_secondary_or_passing_subset_cannot_be_primary(self):
        self.rejected(lambda d: d['primary'].update(endpoint='steady'))
        self.rejected(lambda d: d['primary'].update(incomplete_cohort_aggregate='passing-subset'))

    def test_no_retry_or_invented_use_counts(self):
        self.rejected(lambda d: d['rules'].update(attempts_per_slot=2))
        self.rejected(lambda d: d['rules'].update(per_application_retained_hit_occupancy='observed'))

    def test_geometry_changes_cannot_pass_as_canonical_case(self):
        self.rejected(lambda d: d['visits'][1]['plan']['cases'][0].update(kib=64))


if __name__ == '__main__':
    unittest.main()
