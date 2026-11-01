"""Test strict late-versus-earlier one-line fixed-arm effect comparison."""

import copy
import unittest

from compare_scheduler_physical_preview_timing_fixed_ab import compare


def analysis(timing, mode, enabled_value, disabled_value):
    """Build a minimal complete strict-analysis-shaped fixture."""
    metrics = (
        "wake_to_entry", "load_cycles", "wake_to_load", "roundtrip",
        "child_post_load", "return_handoff",
    )
    replicates = []
    for order in ("enabled-disabled", "disabled-enabled"):
        values = {
            "enabled": {metric: [enabled_value] * 512 for metric in metrics},
            "disabled": {metric: [disabled_value] * 512 for metric in metrics},
        }
        replicates.append({
            "order": order,
            "enabled": {"trials": 512, "values": values["enabled"]},
            "disabled": {"trials": 512, "values": values["disabled"]},
            "median_difference_enabled_minus_disabled": {
                metric: enabled_value - disabled_value for metric in metrics
            },
        })
    return {
        "timing": timing,
        "mode": mode,
        "footprint": "target",
        "lines": 1,
        "group": 7,
        "identity": {
            "bitstream_sha256": "1" * 64,
            "control_program_sha256": "2" * 64,
        },
        "replicates": replicates,
    }


class TimingComparisonTest(unittest.TestCase):
    def test_known_early_minus_late_effect(self):
        late = analysis("wake-data", 6, 90, 100)
        early = analysis("wake-early-data", 1, 80, 100)
        result = compare(late, early, 10, 10)
        metric = result["metrics"]["wake_to_load"]
        self.assertEqual(metric["late_enabled_minus_disabled"], -10)
        self.assertEqual(metric["early_enabled_minus_disabled"], -20)
        self.assertEqual(metric["early_minus_late"], -10)
        self.assertEqual(metric["circular_block_bootstrap"]["difference_ci95"],
                         [-10, -10])

    def test_rejects_wrong_shape_and_identity(self):
        late = analysis("wake-data", 6, 90, 100)
        early = analysis("wake-early-data", 1, 80, 100)
        wrong = copy.deepcopy(early)
        wrong["lines"] = 2
        with self.assertRaisesRegex(ValueError, "one-line"):
            compare(late, wrong, 10, 10)
        wrong = copy.deepcopy(early)
        wrong["identity"]["bitstream_sha256"] = "3" * 64
        with self.assertRaisesRegex(ValueError, "bitstream_sha256"):
            compare(late, wrong, 10, 10)


if __name__ == "__main__":
    unittest.main()
